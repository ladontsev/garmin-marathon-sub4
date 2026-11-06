#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Garmin Workout & Calendar Synchronizer
Парсит тренировки из CALENDAR.md, создает структурированные беговые тренировки 
в Garmin Connect и планирует их в календаре Garmin с поддержкой умного обновления и очистки.
"""

import os
import sys
import re
import argparse
import getpass
import datetime
from pathlib import Path

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

try:
    from garminconnect import Garmin
    from garminconnect.workout import (
        RunningWorkout, WorkoutSegment, create_warmup_step, 
        create_targeted_distance_interval_step, create_cooldown_step,
        create_repeat_group, create_interval_step,
        CustomHeartRateTarget, PaceTarget, pace_to_mps
    )
except ImportError:
    print("Ошибка: Требуется библиотека garminconnect.")
    print("Установите: pip install garminconnect pydantic")
    sys.exit(1)

DEFAULT_TOKEN_DIR = Path.home() / ".config" / "garmin" / "tokens"


def parse_calendar(calendar_path: str = "CALENDAR.md") -> list[dict]:
    """Парсит тренировки из CALENDAR.md"""
    if not os.path.exists(calendar_path):
        raise FileNotFoundError(f"Файл {calendar_path} не найден.")

    with open(calendar_path, "r", encoding="utf-8") as f:
        text = f.read()

    pattern = re.compile(
        r'\|\s*(?:\*\*)?(\d{2}\.\d{2}\.\d{4})(?:\*\*)?\s*\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|\s*([^|]+)\|'
    )
    days_set = {'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'}
    workouts = []

    for m in pattern.findall(text):
        date_str, day, loc, wtype, dist_str, desc = [re.sub(r'\*+', '', x).strip() for x in m]
        if day in days_set:
            dt = datetime.datetime.strptime(date_str, "%d.%m.%Y").date()
            dist_match = re.search(r'([\d\.]+)', dist_str)
            dist_km = float(dist_match.group(1)) if dist_match and dist_str != '—' else 0.0

            workouts.append({
                "date": dt,
                "date_str": dt.strftime("%Y-%m-%d"),
                "day": day,
                "location": loc,
                "type": wtype,
                "dist_km": dist_km,
                "raw_dist": dist_str,
                "description": desc
            })

    return workouts


def build_running_workout(w: dict) -> RunningWorkout | None:
    """Создает структурированную тренировку для Garmin Connect"""
    dist_km = w["dist_km"]
    wtype = w["type"]
    desc = w["description"]

    if dist_km <= 0 or "ОТДЫХ" in wtype or "—" in w["raw_dist"]:
        return None

    title = f"{w['day']} - {wtype[:20]} ({dist_km}k)"
    clean_title = re.sub(r'[^\w\s\-\.\(\)\/]', '', title).strip()

    steps = []
    step_order = 1

    # 1. Intervals check
    interval_match = re.search(r'(\d+)\s*(?:повтор[а-я]*|раз[а-я]*|по)\s*([\d\.]+)\s*км.*темп[е\s]*(\d+):(\d+)', desc, re.IGNORECASE)
    
    if interval_match and ("Интервалы" in wtype or "Аэробно-силовой" in wtype or "Крейсерские" in wtype):
        reps = int(interval_match.group(1))
        rep_dist_km = float(interval_match.group(2))
        pace_min = int(interval_match.group(3))
        pace_sec = int(interval_match.group(4))
        
        warmup_dist = min(2000.0, max(1000.0, (dist_km - reps * rep_dist_km) * 500))
        steps.append(create_targeted_distance_interval_step(
            distance_meters=warmup_dist,
            step_order=step_order,
            target=CustomHeartRateTarget(lower_limit=110, upper_limit=128)
        ))
        step_order += 1

        lower_speed = pace_to_mps(pace_min, min(59, pace_sec + 6), 'km')
        upper_speed = pace_to_mps(pace_min, max(0, pace_sec - 6), 'km')
        
        rep_step = create_targeted_distance_interval_step(
            distance_meters=rep_dist_km * 1000.0,
            step_order=1,
            target=PaceTarget(lower_limit=lower_speed, upper_limit=upper_speed)
        )
        recovery_step = create_interval_step(
            duration_seconds=120.0,
            step_order=2,
            target_type={"workoutTargetTypeId": 4, "workoutTargetTypeKey": "heart.rate.zone"},
            zone_number=1
        )
        
        repeat_group = create_repeat_group(
            iterations=reps,
            workout_steps=[rep_step, recovery_step],
            step_order=step_order
        )
        steps.append(repeat_group)
        step_order += 1

        cooldown_dist = max(1000.0, dist_km * 1000.0 - warmup_dist - (reps * rep_dist_km * 1000.0))
        steps.append(create_targeted_distance_interval_step(
            distance_meters=cooldown_dist,
            step_order=step_order,
            target=CustomHeartRateTarget(lower_limit=105, upper_limit=125)
        ))

    # 2. Long Run (ЛОНГ)
    elif "ЛОНГ" in wtype or "Long Run" in wtype:
        steps.append(create_warmup_step(duration_seconds=300.0, step_order=step_order))
        step_order += 1
        
        main_dist_m = max(1000.0, dist_km * 1000.0 - 500.0)
        steps.append(create_targeted_distance_interval_step(
            distance_meters=main_dist_m,
            step_order=step_order,
            target=CustomHeartRateTarget(lower_limit=118, upper_limit=132)
        ))
        step_order += 1
        
        steps.append(create_cooldown_step(duration_seconds=300.0, step_order=step_order))

    # 3. Easy / Recovery / Base Z2
    else:
        steps.append(create_warmup_step(duration_seconds=300.0, step_order=step_order))
        step_order += 1
        
        main_dist_m = max(1000.0, dist_km * 1000.0 - 400.0)
        steps.append(create_targeted_distance_interval_step(
            distance_meters=main_dist_m,
            step_order=step_order,
            target=CustomHeartRateTarget(lower_limit=115, upper_limit=126)
        ))
        step_order += 1
        
        steps.append(create_cooldown_step(duration_seconds=300.0, step_order=step_order))

    estimated_secs = int(dist_km * 390 + 600)

    workout = RunningWorkout(
        workoutName=clean_title,
        estimatedDurationInSecs=estimated_secs,
        description=f"{w['type']}. {desc[:180]}",
        workoutSegments=[
            WorkoutSegment(
                segmentOrder=1,
                sportType={"sportTypeId": 1, "sportTypeKey": "running"},
                workoutSteps=steps
            )
        ]
    )
    return workout


def get_garmin_client(token_dir: Path, email: str | None = None, password: str | None = None) -> Garmin:
    """Авторизует клиента Garmin Connect с сохранением сессионных токенов"""
    token_dir.mkdir(parents=True, exist_ok=True)
    client = Garmin(email, password)

    token_file = token_dir / "oauth2_tokens.json"
    if token_file.exists():
        print(f"🔄 Вход по сохраненным сессионным токенам из {token_dir}...")
        try:
            client.login(str(token_dir))
            print("✅ Успешный вход в Garmin Connect!")
            return client
        except Exception as e:
            print(f"⚠️ Токены устарели ({e}). Требуется повторный вход.")

    if not email:
        email = input("Введите Email от Garmin Connect: ").strip()
    if not password:
        password = getpass.getpass("Введите пароль от Garmin Connect (ввод скрыт): ").strip()

    client = Garmin(email, password)
    print("⏳ Авторизация в Garmin SSO...")
    client.login(str(token_dir))
    print(f"✅ Успешный вход! Токены сохранены в {token_dir}.")
    return client


def fetch_existing_scheduled(client: Garmin, start_str: str, end_str: str) -> dict[str, list[dict]]:
    """Получает словарь уже запланированных тренировок по датам { 'YYYY-MM-DD': [items...] }"""
    try:
        items = client.get_scheduled_workouts_by_period(start_str, end_str)
        by_date = {}
        for item in items or []:
            d = item.get("calendarDate") or item.get("date")
            if d:
                # Format to YYYY-MM-DD
                d_clean = d[:10]
                by_date.setdefault(d_clean, []).append(item)
        return by_date
    except Exception as e:
        print(f"⚠️ Не удалось запросить существующий календарь ({e}). Будет выполнена прямая запись.")
        return {}


def main():
    parser = argparse.ArgumentParser(description="Синхронизация тренировок плана с календарем Garmin Connect")
    parser.add_argument("--dry-run", action="store_true", help="Только показать тренировки без отправки в Garmin")
    parser.add_argument("--weeks", type=int, default=4, help="Количество недель для синхронизации вперед (по умолчанию 4)")
    parser.add_argument("--all", action="store_true", help="Синхронизировать весь план до сентября 2027 г.")
    parser.add_argument("--clear", action="store_true", help="Очистить запланированные тренировки в Garmin за указанный период")
    parser.add_argument("--start-date", type=str, help="Начальная дата (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="Конечная дата (YYYY-MM-DD)")
    parser.add_argument("--token-dir", type=str, default=str(DEFAULT_TOKEN_DIR), help="Папка хранения токенов")
    args = parser.parse_args()

    workouts = parse_calendar("CALENDAR.md")
    today = datetime.date.today()

    if args.start_date:
        start_dt = datetime.datetime.strptime(args.start_date, "%Y-%m-%d").date()
    else:
        start_dt = today

    if args.all:
        end_dt = datetime.date(2027, 9, 30)
    elif args.end_date:
        end_dt = datetime.datetime.strptime(args.end_date, "%Y-%m-%d").date()
    else:
        end_dt = start_dt + datetime.timedelta(weeks=args.weeks)

    start_str = start_dt.strftime("%Y-%m-%d")
    end_str = end_dt.strftime("%Y-%m-%d")

    filtered = [w for w in workouts if start_dt <= w["date"] <= end_dt]

    print(f"\n🏃‍♂️ Тренировочный план Sub-4: умная синхронизация с Garmin Connect")
    print(f"📅 Период: с {start_str} по {end_str} | Найдено в плане: {len(filtered)} записей\n")

    if args.dry_run:
        print("[DRY RUN] Режим симуляции. Проверка сопоставления плана:")
        for w in filtered:
            workout_obj = build_running_workout(w)
            status = "🏃 Бег" if workout_obj else "🧘 Отдых/Старт"
            print(f"  • {w['date_str']} ({w['day']}) | {status} | {w['type']} ({w['raw_dist']})")
        print("\n[DRY RUN] Готово. Никаких изменений в Garmin не внесено.")
        return

    # Real execution
    token_path = Path(args.token_dir)
    client = get_garmin_client(token_path)

    # 1. Получаем текущее расписание из Garmin
    print(f"🔎 Запрос существующих записей календаря Garmin с {start_str} по {end_str}...")
    existing_by_date = fetch_existing_scheduled(client, start_str, end_str)

    # Режим очистки (если вызван с --clear)
    if args.clear:
        print("\n🧹 Режим очистки (--clear): удаление тренировок из календаря...")
        cleared_count = 0
        for d, items in existing_by_date.items():
            for item in items:
                sched_id = item.get("workoutScheduleId") or item.get("scheduleId")
                name = item.get("workoutName") or "Workout"
                if sched_id:
                    print(f"  🗑 Удаление из {d}: {name} (ID: {sched_id})...", end=" ")
                    client.unschedule_workout(sched_id)
                    print("✅ Снято.")
                    cleared_count += 1
        print(f"\n🎉 Очистка завершена! Снято тренировок: {cleared_count}.")
        return

    # Умная синхронизация: удаление устаревших и загрузка обновленных
    print("\n⚡ Синхронизация календаря (умная замена устаревших тренировок)...")
    updated_count = 0

    for w in filtered:
        date_str = w["date_str"]
        workout_obj = build_running_workout(w)
        existing_items = existing_by_date.get(date_str, [])

        # Если день отдыха/соревнований, но в Garmin висит старая тренировка — снимаем её
        if not workout_obj:
            for item in existing_items:
                sched_id = item.get("workoutScheduleId") or item.get("scheduleId")
                if sched_id:
                    print(f"  🧹 {date_str}: День отдыха. Снятие старой тренировки ({sched_id})...", end=" ")
                    client.unschedule_workout(sched_id)
                    print("✅")
            continue

        workout_dict = workout_obj.to_dict()
        new_name = workout_dict["workoutName"]

        # Если на этот день уже стоит тренировка:
        # Проверяем, совпадает ли она. Если нет или если план изменился — снимаем старую!
        need_reschedule = True
        for item in existing_items:
            old_name = item.get("workoutName") or ""
            sched_id = item.get("workoutScheduleId") or item.get("scheduleId")
            
            # Если имя совпадает в точности, тренировка уже актуальна
            if old_name == new_name:
                print(f"  ⏭ {date_str}: {new_name} уже в календаре Garmin (без изменений).")
                need_reschedule = False
                break
            else:
                # План изменился! Снимаем старую версию
                if sched_id:
                    print(f"  🔄 {date_str}: План изменился! Снятие старой версии '{old_name}'...", end=" ")
                    client.unschedule_workout(sched_id)
                    print("✅")

        # Загружаем и назначаем обновленную тренировку
        if need_reschedule:
            try:
                print(f"  ⏳ Загрузка: {date_str} - {new_name}...", end=" ", flush=True)
                resp = client.upload_workout(workout_dict)
                workout_id = resp.get("workoutId")
                if workout_id:
                    client.schedule_workout(workout_id, date_str)
                    print(f"✅ Успешно! (ID: {workout_id})")
                    updated_count += 1
                else:
                    print(f"⚠️ Ошибка получения workoutId: {resp}")
            except Exception as e:
                print(f"❌ Ошибка: {e}")

    print(f"\n🎉 Синхронизация завершена! Внесено/обновлено тренировок: {updated_count}.")
    print("Откройте часы или приложение Garmin Connect для обновления.")


if __name__ == "__main__":
    main()

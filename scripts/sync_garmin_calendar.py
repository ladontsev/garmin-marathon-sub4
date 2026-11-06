#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Garmin Workout & Calendar Synchronizer
Парсит тренировки из CALENDAR.md, создает структурированные беговые тренировки 
в Garmin Connect и планирует их в календаре Garmin.
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
            # Parse date DD.MM.YYYY -> YYYY-MM-DD
            dt = datetime.datetime.strptime(date_str, "%d.%m.%Y").date()
            
            # Parse distance in km
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
    date_str = w["date_str"]

    if dist_km <= 0 or "ОТДЫХ" in wtype or "—" in w["raw_dist"]:
        return None

    title = f"{w['day']} - {wtype[:22]} ({dist_km}k)"
    # Cleanup title from emojis for Garmin device compatibility
    clean_title = re.sub(r'[^\w\s\-\.\(\)\/]', '', title).strip()

    # Determine workout type and target zones
    steps = []
    step_order = 1

    # 1. Intervals check (e.g., "4 повтора по 1 км в темпе 5:45" or "4 по 1 км в темпе 4:55")
    interval_match = re.search(r'(\d+)\s*(?:повтор[а-я]*|раз[а-я]*|по)\s*([\d\.]+)\s*км.*темп[е\s]*(\d+):(\d+)', desc, re.IGNORECASE)
    
    if interval_match and ("Интервалы" in wtype or "Аэробно-силовой" in wtype or "Крейсерские" in wtype):
        reps = int(interval_match.group(1))
        rep_dist_km = float(interval_match.group(2))
        pace_min = int(interval_match.group(3))
        pace_sec = int(interval_match.group(4))
        
        # Warmup (1.5-2.0 km)
        warmup_dist = min(2000.0, max(1000.0, (dist_km - reps * rep_dist_km) * 500))
        steps.append(create_targeted_distance_interval_step(
            distance_meters=warmup_dist,
            step_order=step_order,
            target=CustomHeartRateTarget(lower_limit=110, upper_limit=128)
        ))
        step_order += 1

        # Target Pace (e.g. 5:15/km +/- 5 sec)
        # Note: speed in m/s (faster pace = higher m/s)
        lower_speed = pace_to_mps(pace_min, min(59, pace_sec + 6), 'km')
        upper_speed = pace_to_mps(pace_min, max(0, pace_sec - 6), 'km')
        
        rep_step = create_targeted_distance_interval_step(
            distance_meters=rep_dist_km * 1000.0,
            step_order=1,
            target=PaceTarget(lower_limit=lower_speed, upper_limit=upper_speed)
        )
        # Recovery step (e.g. 2 min easy jog)
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

        # Cooldown
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
        # Target Zone 2 (118-132 bpm)
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
        # Target Zone 2 (115-126 bpm)
        steps.append(create_targeted_distance_interval_step(
            distance_meters=main_dist_m,
            step_order=step_order,
            target=CustomHeartRateTarget(lower_limit=115, upper_limit=126)
        ))
        step_order += 1
        
        steps.append(create_cooldown_step(duration_seconds=300.0, step_order=step_order))

    # Estimated duration in seconds (based on ~6:30 min/km + 10 min warm/cool)
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

    # Пробуем войти по сохраненным токенам (без ввода пароля)
    token_file = token_dir / "oauth2_tokens.json"
    if token_file.exists():
        print(f"🔄 Вход по сохраненным токенам из {token_dir}...")
        try:
            client.login(str(token_dir))
            print("✅ Успешный вход в Garmin Connect!")
            return client
        except Exception as e:
            print(f"⚠️ Токены устарели или недействительны ({e}). Требуется вход по логину.")

    # Если токенов нет или устарели — запрашиваем логин и пароль
    if not email:
        email = input("Введите Email от Garmin Connect: ").strip()
    if not password:
        password = getpass.getpass("Введите пароль от Garmin Connect (ввод скрыт): ").strip()

    client = Garmin(email, password)
    print("⏳ Авторизация в Garmin SSO...")
    client.login(str(token_dir))
    print(f"✅ Успешный вход! Сессионные токены сохранены в {token_dir}.")
    return client


def main():
    parser = argparse.ArgumentParser(description="Синхронизация тренировок плана с календарем Garmin Connect")
    parser.add_argument("--dry-run", action="store_true", help="Только показать тренировки без отправки в Garmin")
    parser.add_argument("--weeks", type=int, default=4, help="Количество недель для синхронизации вперед (по умолчанию 4)")
    parser.add_argument("--all", action="store_true", help="Синхронизировать весь план до сентября 2027 г.")
    parser.add_argument("--start-date", type=str, help="Начальная дата (YYYY-MM-DD)")
    parser.add_argument("--end-date", type=str, help="Конечная дата (YYYY-MM-DD)")
    parser.add_argument("--token-dir", type=str, default=str(DEFAULT_TOKEN_DIR), help="Папка хранения токенов")
    args = parser.parse_args()

    workouts = parse_calendar("CALENDAR.md")
    today = datetime.date.today()

    # Filter by date range
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

    filtered = [w for w in workouts if start_dt <= w["date"] <= end_dt]

    print(f"\n🏃‍♂️ Тренировочный план Sub-4: синхронизация с Garmin Connect")
    print(f"📅 Период: с {start_dt} по {end_dt} | Найдено тренировок: {len(filtered)}\n")

    if not filtered:
        print("В указанном диапазоне нет запланированных тренировок.")
        return

    # Print summary
    for w in filtered:
        workout_obj = build_running_workout(w)
        status = "🏃 Бег" if workout_obj else "🧘 Отдых/Старт"
        print(f"  • {w['date_str']} ({w['day']}) | {status} | {w['type']} ({w['raw_dist']})")

    if args.dry_run:
        print("\n[DRY RUN] Режим симуляции. Никаких данных в Garmin не отправлено.")
        return

    # Real upload
    print("\nПодключение к Garmin Connect...")
    token_path = Path(args.token_dir)
    client = get_garmin_client(token_path)

    uploaded_count = 0
    print("\nНачинаем загрузку тренировок в календарь Garmin...")

    for w in filtered:
        workout_obj = build_running_workout(w)
        if not workout_obj:
            continue

        workout_dict = workout_obj.to_dict()
        date_str = w["date_str"]

        try:
            print(f"  ⏳ Загрузка: {date_str} - {workout_dict['workoutName']}...", end=" ", flush=True)
            # 1. Upload workout
            resp = client.upload_workout(workout_dict)
            workout_id = resp.get("workoutId")
            
            # 2. Schedule to calendar date
            if workout_id:
                client.schedule_workout(workout_id, date_str)
                print(f"✅ В календаре! (ID: {workout_id})")
                uploaded_count += 1
            else:
                print(f"⚠️ Загружено, но не получен workoutId: {resp}")
        except Exception as e:
            print(f"❌ Ошибка: {e}")

    print(f"\n🎉 Готово! Успешно внесено тренировок в календарь Garmin: {uploaded_count}.")
    print("Откройте приложение Garmin Connect на смартфоне или часы для синхронизации!")


if __name__ == "__main__":
    main()

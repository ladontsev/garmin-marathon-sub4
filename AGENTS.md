# Правила и интеграции проекта (Antigravity Context Rules)

## 🏃 Garmin Connect & MCP Интеграция

Данный проект отслеживает подготовку к марафону Sub-4 и анализирует физиологическое состояние атлета через официальный **Garmin Connect Personal API**.

### 1. Используемый MCP-сервер
В проекте настроен открытый сервер **`garmin-personal-mcp`** (в файле `.agents/mcp_config.json`):
* **Команда запуска:** `uvx garmin-personal-mcp` (требует установленного инструмента `uv` / `uvx` или `npx`).
* **Навык анализа:** `.agents/skills/garmin-workout-analyzer/SKILL.md`.

### 2. Авторизация и API-ключ
Для работы с данными Garmin требуется **Garmin Connect Personal API Key** формата `GCDC_...` (получается в Garmin Connect Web: *Настройки → Personal API* или через [Garmin Developer Program](https://developer.garmin.com/gc-developer-program/personal/swagger-docs/)).

Ключ считывается сервером из одного из двух мест:
1. Защищенный файл пользователя: `~/.config/garmin/connect-personal-api-key`
2. Переменная окружения: `GARMIN_PERSONAL_API_KEY`

### 3. Инструкция для агента при открытии проекта на новом компьютере:
* При первом обращении пользователя к тренировкам или статусу восстановления проверь, доступен ли MCP-сервер и авторизован ли ключ:
  ```bash
  uvx garmin-personal-mcp auth --check
  ```
* Если сервер не авторизован или ключ не найден:
  1. Сразу предупреди пользователя:  
     *«Для автоматического анализа тренировок и восстановления на этом компьютере требуется подключить Garmin Personal API. Пожалуйста, пришлите мне ваш ключ (начинается на GCDC_...) либо выполните команду: `uvx garmin-personal-mcp auth`».*
  2. Если пользователь присылает ключ, сохрани его в `~/.config/garmin/connect-personal-api-key`, выполни верификацию `uvx garmin-personal-mcp auth --check` и обнови статус.
* Ни в коем случае не коммитьте реальный API-ключ в репозиторий Git!

# LeadRadar AI MVP

Рабочий вертикальный MVP SaaS-платформы поиска заявок и тендеров.\n\n**Базовое ТЗ проекта:** [docs/TECHNICAL_SPEC.md](docs/TECHNICAL_SPEC.md)

## Что реализовано

- регистрация компании и пользователя;
- анализ сайта компании и автосоздание Search Profile;
- ручное редактирование поискового профиля;
- генератор поисковых запросов;
- Yandex Search API connector;
- SerpAPI-compatible connector;
- web crawler / нормализация результата;
- heuristics + optional OpenAI AI-анализ;
- relevance score 0-100;
- антидубли;
- проверка актуальности;
- Opportunity database;
- dashboard и список возможностей;
- статусы Opportunity;
- email delivery;
- Telegram delivery + кнопки статусов;
- partner webhook API с HMAC подписью;
- retry delivery queue;
- delivery log;
- REST API + API key;
- XLSX export;
- scheduler;
- минимальная admin view;
- demo mode без внешних ключей.

## Быстрый запуск

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env   # Windows
# cp .env.example .env   # macOS/Linux
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Открыть: http://localhost:8000

## Реальный поиск

Добавьте в `.env`:

```env
YANDEX_API_KEY=...
YANDEX_FOLDER_ID=...
DEMO_MODE=0
```

Yandex connector использует `POST https://searchapi.api.cloud.yandex.net/v2/web/search`.

## Telegram

1. Создайте бота у BotFather.
2. Укажите `TELEGRAM_BOT_TOKEN`.
3. Разверните приложение на публичном HTTPS URL и задайте `BASE_URL`.
4. Зарегистрируйте webhook Telegram на:

`{BASE_URL}/api/telegram/webhook/{TELEGRAM_WEBHOOK_SECRET}`

5. В кабинете скопируйте код привязки и отправьте боту `/start КОД`.

## Partner webhook

В разделе «Интеграции» задайте endpoint и secret. Payload подписывается HMAC SHA-256 и передается с заголовком `X-LeadRadar-Signature`.

## REST API

API key отображается в настройках аккаунта. Передавайте:

`X-API-Key: <key>`

Основные endpoints:

- `GET /api/v1/opportunities`
- `GET /api/v1/opportunities/{id}`
- `GET /api/v1/search-profiles`
- `POST /api/v1/search-profiles`
- `PUT /api/v1/search-profiles/{id}`
- `POST /api/v1/search-profiles/{id}/run`
- `GET /api/v1/deliveries`
- `POST /api/v1/opportunities/{id}/status`
- `GET /api/v1/analytics`
- `GET /api/v1/export.xlsx`

## Важно для production

Этот MVP специально запускается без Redis/Celery и без обязательного PostgreSQL, чтобы проверить продуктовый цикл одной командой. Перед промышленной нагрузкой delivery/search workers следует вынести в Celery/RQ/Temporal, БД переключить на PostgreSQL, секреты хранить в secret manager, а миграции вести Alembic.

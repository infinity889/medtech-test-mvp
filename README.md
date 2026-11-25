# MedServicePrice.kz — MVP

Агрегатор и сравнение цен на медицинские услуги в Казахстане (анализы, приёмы врачей, диагностика, процедуры).

## Архитектура (Capability Map)

Проект разрабатывается строго по Spec-Driven Development — см. [CAPABILITY-MAP.md](./CAPABILITY-MAP.md):

1. **`ingestion`** ([SPEC-ingestion.md](./SPEC-ingestion.md)) — сбор прайс-листов из публичных источников, соблюдение `robots.txt` и rate-limit, raw-слой PostgreSQL (ретеншн ≥ 90 дней), экстракторы HTML/PDF/DOCX/Excel, дедупликация, журнал ошибок, CLI и планировщик.
2. **`normalization`** ([SPEC-normalization.md](./SPEC-normalization.md)) — справочник из 88 канонических услуг по 4 категориям, детерминированный матчер (`exact` → `synonym` → категорийно-изолированный `RapidFuzz`), конвертация `USD → KZT` (`Decimal`), дедуплицированные клиники и предложения, история цен (`price_history`), очередь ручной разметки (`unmatched_services`) и правило актуальности ≤ 30 дней.
3. **`search-api`** ([SPEC-search-api.md](./SPEC-search-api.md)) — FastAPI REST API (`/api/v1`) поиска и сравнения цен: автодополнение, фильтры (город, категория, цена, рейтинг, онлайн-запись), сортировка (цена, расстояние Haversine, свежесть, рейтинг), жёсткое правило актуальности ≤ 30 дней, карточка клиники со ссылками 2GIS / Google Maps, сравнение 2–5 клиник в таблице (`/compare`), история цен и защищённая `X-Admin-Token` админка с блокировкой дублей парсинга (`409`).
4. **`web-ui`** *(следующий этап)* — адаптивный интерфейс (React + TypeScript + Vite + Leaflet).

## Подключённые открытые источники (`ingestion`)

Все источники проверены на разрешающий `robots.txt` и валидный TLS:

| `source_id` | Источник | Данные | Города |
|---|---|---|---|
| `kdlolymp` | [kdlolymp.kz](https://kdlolymp.kz) (КДЛ Олимп) | Лабораторные анализы, цены в KZT, сроки, графики, GPS | Алматы, Астана, Шымкент, Караганда, Актобе, Павлодар |
| `invivo` | [invivo.kz](https://invivo.kz) (Лаборатория INVIVO) | Лабораторные анализы, цены в KZT, сроки, адреса, графики, GPS | Алматы, Астана, Шымкент |
| `doq` | [doq.kz](https://doq.kz) (DOQ.kz) | Приёмы врачей, диагностика, адреса, GPS, рейтинги, онлайн-запись | Алматы, Астана, Шымкент |

## Основные эндпоинты REST API (`search-api`)

Документация OpenAPI доступна после запуска API по адресу `http://127.0.0.1:8000/docs`:

- `GET /api/v1/health` — проверка состояния API и PostgreSQL.
- `GET /api/v1/meta/filters` — города, категории, диапазон цен и время обновления.
- `GET /api/v1/services/autocomplete?q=ОАК` — ранжированные подсказки по справочнику услуг и синонимам.
- `GET /api/v1/offers` — поиск и сравнение цен (фильтры, Haversine-расстояние, сортировка, правило свежести ≤ 30 дней).
- `GET /api/v1/clinics` и `GET /api/v1/clinics/{clinic_id}` — список клиник (вкл. `has_geo=true` для карты) и карточка клиники со ссылками 2GIS / Google Maps.
- `GET /api/v1/compare?clinic_ids=...` — табличное сравнение 2–5 клиник с выделением минимальной цены.
- `GET /api/v1/services/{service_id}/price-history` — история изменения цен по услуге.
- `/api/v1/admin/*` (заголовок `X-Admin-Token`) — источники, история/ошибки парсинга, ручной запуск (`POST /scrape-runs`), статистика и разбор очереди `unmatched`.

## Быстрый старт (`podman` + Python 3.12 + PostgreSQL 16)

Требования на хосте: `podman`, `make`.

```bash
# 1. Собрать Python 3.12 образ backend
make backend-build

# 2. Поднять PostgreSQL 16 и применить миграции Alembic
make db-up
make migrate

# 3. Запустить все тесты backend (ingestion + normalization + search-api) + проверки качества
make test-all
make lint
make typecheck

# 4. Запустить сбор реальных данных по всем 3 источникам (опционально --limit N)
make ingest SOURCE=all EXTRA_ARGS="--limit 600"

# 5. Загрузить справочник услуг (88 позиций) и выполнить нормализацию raw → normalized
make seed-catalog
make normalize

# 6. Запустить REST API на http://127.0.0.1:8000 (OpenAPI Swagger: /docs)
make api-up
curl -sS "http://127.0.0.1:8000/api/v1/services/autocomplete?q=%D0%9E%D0%90%D0%9A"

# Остановить API-контейнер
make api-down
```

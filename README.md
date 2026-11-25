# MedServicePrice.kz — MVP

Агрегатор и сравнение цен на медицинские услуги в Казахстане (анализы, приёмы врачей, диагностика, процедуры).

## Архитектура (Capability Map)

Проект разработан строго по Spec-Driven Development — см. [CAPABILITY-MAP.md](./CAPABILITY-MAP.md):

1. **`ingestion`** ([SPEC-ingestion.md](./SPEC-ingestion.md)) — сбор прайс-листов из публичных источников, соблюдение `robots.txt` и rate-limit, raw-слой PostgreSQL (ретеншн ≥ 90 дней), экстракторы HTML/PDF/DOCX/Excel, дедупликация, журнал ошибок, CLI и планировщик.
2. **`normalization`** ([SPEC-normalization.md](./SPEC-normalization.md)) — справочник из 88 канонических услуг по 4 категориям, детерминированный матчер (`exact` → `synonym` → категорийно-изолированный `RapidFuzz`), конвертация `USD → KZT` (`Decimal`), дедуплицированные клиники и предложения, история цен (`price_history`), очередь ручной разметки (`unmatched_services`) и правило актуальности ≤ 30 дней.
3. **`search-api`** ([SPEC-search-api.md](./SPEC-search-api.md)) — FastAPI REST API (`/api/v1`) поиска и сравнения цен: автодополнение, фильтры (город, категория, цена, рейтинг, онлайн-запись), сортировка (цена, расстояние Haversine, свежесть, рейтинг), жёсткое правило актуальности ≤ 30 дней, карточка клиники со ссылками 2GIS / Google Maps, сравнение 2–5 клиник в таблице (`/compare`), история цен и защищённая `X-Admin-Token` админка с блокировкой дублей парсинга (`409`).
4. **`web-ui`** ([SPEC-web-ui.md](./SPEC-web-ui.md)) — адаптивный веб-интерфейс (React 19 + TypeScript + Vite 6 + Tailwind CSS v4 + Leaflet) в контейнере Node 22: поиск в стиле Aviasales с WAI-ARIA автодополнением, фильтрами в URL и геолокацией, карта клиник OpenStreetMap со ссылками 2GIS / Google Maps, карточка клиники, таблица сравнения 2–5 клиник, SVG-график истории цен в `<dialog>` и панель оператора `/admin`.

## Подключённые открытые источники (`ingestion`)

Все источники проверены на разрешающий `robots.txt` и валидный TLS:

| `source_id` | Источник | Данные | Города |
|---|---|---|---|
| `kdlolymp` | [kdlolymp.kz](https://kdlolymp.kz) (КДЛ Олимп) | Лабораторные анализы, цены в KZT, сроки, графики, GPS | Алматы, Астана, Шымкент, Караганда, Актобе, Павлодар |
| `invivo` | [invivo.kz](https://invivo.kz) (Лаборатория INVIVO) | Лабораторные анализы, цены в KZT, сроки, адреса, графики, GPS | Алматы, Астана, Шымкент |
| `doq` | [doq.kz](https://doq.kz) (DOQ.kz) | Приёмы врачей, диагностика, адреса, GPS, рейтинги, онлайн-запись | Алматы, Астана, Шымкент |

## Быстрый старт (`podman` + PostgreSQL 16 + Python 3.12 + Node 22)

Требования на хосте: `podman`, `make` (Python и Node на хосте не требуются).

```bash
# 1. Собрать образы backend (Python 3.12) и frontend (Node 22)
make backend-build
make web-build

# 2. Поднять PostgreSQL 16 и применить миграции Alembic
make db-up
make migrate

# 3. Загрузить справочник услуг (88 позиций), собрать данные и нормализовать
make seed-catalog
make ingest SOURCE=all EXTRA_ARGS="--limit 600"
make normalize

# 4. Запустить REST API (:8000, Swagger /docs) и веб-интерфейс (:5173)
make api-up
make web-up
# Веб-приложение: http://localhost:5173
# Swagger OpenAPI: http://localhost:8000/docs

# Остановить контейнеры
make web-down
make api-down
```

## Проверки качества и тесты

```bash
# Backend: 109 тестов (ingestion + normalization + search-api), ruff, mypy --strict
make test-all
make lint
make typecheck

# Frontend: Vitest + Testing Library, ESLint, TypeScript strict, Vite production build
make test-web
make lint-web
make typecheck-web
make build-web
```

# Spec: Search & Comparison API (`search-api`) — V1

> Часть карты модулей [CAPABILITY-MAP.md](./CAPABILITY-MAP.md). Модуль `search-api` зависит от [`normalization`](./SPEC-normalization.md) и [`ingestion`](./SPEC-ingestion.md) и предоставляет стабильный HTTP REST API (OpenAPI 3.1) для клиентского интерфейса `web-ui` и административных операций.

## Objective

Реализовать быстрый, строго типизированный FastAPI REST API для платформы MedServicePrice.kz:

- **Поиск и сравнение (Aviasales-поток)**: автодополнение по справочнику услуг, поиск предложений с фильтрами (город, категория, ценовой диапазон, рейтинг клиники, наличие онлайн-записи), сортировкой (цена ↑/↓, расстояние по геолокации, дата обновления, рейтинг) и пагинацией.
- **Прозрачность и актуальность**: каждая выдача содержит `parsed_at` и `source_url`; предложения старше **30 дней** или с `is_active = false` **никогда не возвращаются** в публичном поиске (ТЗ разд. 4).
- **Карточка клиники и дополнительные функции V1**:
  - Карточка клиники со всеми активными услугами, контактами, графиком работы, координатами и ссылками маршрута в **2GIS** и **Google Maps**.
  - Режим сравнения **2–5 клиник в таблице** (матрица «услуга × клиники» с отметкой минимальной цены).
  - **История изменения цен** по услуге (с фильтром по клинике и периоду) для графика в `web-ui`.
  - Список клиник с GPS-координатами для карты Leaflet.
- **Админ-операции**: защищённые заголовком `X-Admin-Token` эндпоинты для ручного запуска парсинга + нормализации (с защитой от параллельного дублирующего запуска `409 Conflict`), просмотра истории запусков/ошибок и разбора `unmatched queue` (`resolve` / `ignore`).

### Пользовательские истории и критерии производительности
- Как **пациент**, я получаю подсказки автодополнения за `< 150 мс` и поисковую выдачу сравнения цен за **`< 500 мс`** (запас в 6× относительно требования ТЗ `≤ 3 сек`).
- Как **разработчик `web-ui`**, я работаю со стабильным OpenAPI-контрактом `/api/v1/*`, единым форматом ошибок и предсказуемой пагинацией на всех списочных эндпоинтах.
- Как **оператор**, я могу запустить парсер вручную через API и разметить нераспознанные услуги без доступа к консоли сервера.

## Tech Stack

- **Фреймворк**: `fastapi>=0.115,<1.0`, `uvicorn[standard]>=0.32,<1.0` (добавляются в `backend/pyproject.toml`, пересборка `medprice-backend:dev` в `podman`)
- **БД и сервисы**: PostgreSQL 16 (`medprice-pg`), `SQLAlchemy 2.0`, фасады `NormalizationService` и `IngestionService` (новых миграций БД в `search-api` не требуется)
- **Валидация и конфиг**: `pydantic` v2, `pydantic-settings` (добавляются `ADMIN_API_TOKEN`, `CORS_ORIGINS`, `API_HOST`, `API_PORT`)
- **Тесты и качество**: `pytest`, `httpx.AsyncClient` (`ASGITransport`), `pytest-cov`, `ruff`, `mypy --strict`

## Commands

```bash
# Пересобрать backend-образ после добавления fastapi + uvicorn
make backend-build

# Запустить API-сервер в контейнере podman (порт 8000, подключается к medprice-pg)
make api-up
make api-down

# Локальный dev-запуск API в foreground с autoreload
make api-dev

# Запустить тесты модуля search-api с покрытием
make test-api

# Запустить все тесты backend (ingestion + normalization + search-api)
make test-all

# Линтинг и проверка типов
make lint
make typecheck
```

## Project Structure

```text
backend/
├── app/
│   ├── main.py                       → Точка входа FastAPI (lifespan, CORS, error handlers, /api/v1 router)
│   └── api/
│       ├── __init__.py
│       ├── deps.py                   → DI: DB session, IngestionService, NormalizationService, проверка X-Admin-Token
│       ├── errors.py                 → Единый формат ошибок APIError + exception handlers (400/401/404/409/422/500)
│       ├── schemas.py                → Pydantic v2 контракты запросов и ответов (PaginationMeta, OfferSearchItem, ClinicDetail, CompareMatrix, Admin*)
│       ├── query_service.py          → SQL-запросы поиска/автодополнения/сравнения/Haversine-расстояния/ссылок 2GIS+Google Maps
│       └── routes/
│           ├── __init__.py
│           ├── health.py             → GET /api/v1/health, GET /api/v1/meta/filters
│           ├── services.py           → GET /api/v1/services/autocomplete, GET /api/v1/services/{service_id}/price-history
│           ├── offers.py             → GET /api/v1/offers
│           ├── clinics.py            → GET /api/v1/clinics, GET /api/v1/clinics/{clinic_id}, GET /api/v1/compare
│           └── admin.py              → /api/v1/admin/{sources,scrape-runs,scrape-errors,unmatched,stats}
└── tests/
    └── api/
        ├── conftest.py               → Тестовое FastAPI-приложение и seeded test fixtures в medprice_test
        ├── test_health_and_meta.py   → Тесты /health, /meta/filters, CORS, error envelope
        ├── test_search_and_offers.py → Автодополнение, фильтры, сортировка (цена/расстояние/свежесть/рейтинг), правило ≤ 30 дней, пагинация
        ├── test_clinics_and_compare.py → Карточка клиники, список для карты, таблица сравнения 2–5 клиник, история цен
        └── test_admin_endpoints.py   → Проверка X-Admin-Token (401), unmatched resolve/ignore, ручной запуск парсинга + 409 lock
```

## REST API Contract (Provider Interface for `web-ui`)

Все эндпоинты имеют префикс `/api/v1` и возвращают `application/json`.

### Единый формат ошибок (`APIError`)
Любая ошибка (`400`, `401`, `404`, `409`, `422`, `500`) возвращается в единой структуре без утечки стектрейсов:
```json
{
  "error": {
    "code": "NOT_FOUND",
    "message": "Clinic not found",
    "details": null
  }
}
```

### Единый формат пагинации
```json
{
  "items": [...],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_items": 64,
    "total_pages": 4
  }
}
```

### 1. Публичные пациентские эндпоинты (без авторизации)

| Метод и путь | Назначение | Ключевые параметры / ответ |
|---|---|---|
| `GET /api/v1/health` | Проверка работоспособности и доступности PostgreSQL | `{"status": "ok", "database": "ok"}` (`503` при сбое БД) |
| `GET /api/v1/meta/filters` | Метаданные для фильтров UI | `cities` (с количеством клиник/предложений), `categories` (`code`, `label_ru`, `offers_count`), `price_min_kzt`, `price_max_kzt`, `last_updated_at` |
| `GET /api/v1/services/autocomplete` | Автодополнение услуг по справочнику | Query: `q` (1..100 симв.), `category?`, `city?`, `limit` (1..20, default `10`). Ответ: `[{service_id, code, canonical_name, category, matched_synonym, offers_count, min_price_kzt}]` (приоритет: точный → префикс → вхождение) |
| `GET /api/v1/offers` | **Основной поиск и сравнение цен** | Query: `service_id?`, `q?`, `city?`, `category?`, `min_price?`, `max_price?`, `min_rating?`, `online_booking?`, `lat?`, `lng?`, `sort_by` (`price_asc` \| `price_desc` \| `distance_asc` \| `updated_desc` \| `rating_desc`), `page`, `page_size` (1..100). Всегда фильтрует `is_active = true AND parsed_at >= now - 30d`. Ответ: пагинированный список `OfferSearchItem` с вложенным `clinic` + `distance_km` + `route_2gis_url` + `route_google_maps_url` + агрегаты `summary: {min_price_kzt, max_price_kzt, avg_price_kzt}` |
| `GET /api/v1/clinics` | Список клиник (в т.ч. для карты Leaflet) | Query: `city?`, `q?`, `min_rating?`, `online_booking?`, `has_geo?`, `page`, `page_size` (1..200). Ответ: пагинированный `ClinicListItem` (с `offers_count`, `min_price_kzt`, `route_2gis_url`, `route_google_maps_url`) |
| `GET /api/v1/clinics/{clinic_id}` | **Карточка клиники** | Ответ: `ClinicDetail` — все контакты, адрес, график работы, рейтинг, GPS, сайт, ссылки маршрута 2GIS/Google Maps + список всех активных услуг клиники (≤ 30 дней) с ценами, сроками и `parsed_at` (`404` если не найдена) |
| `GET /api/v1/compare` | **Сравнение 2–5 клиник в таблице** | Query: `clinic_ids` (повторяемый или CSV, строго 2..5 UUID), `service_ids?`, `category?`. Ответ: `CompareMatrix { clinics: [...], rows: [{ service_id, canonical_name, category, cheapest_clinic_id, cells: { <clinic_id>: { price_kzt, duration_days, parsed_at, source_url } | null } }] }` |
| `GET /api/v1/services/{service_id}/price-history` | **История цен по услуге** | Query: `clinic_id?`, `city?`, `days` (1..365, default `90`). Ответ: `{ service_id, canonical_name, points: [{ recorded_at, price_kzt, clinic_id, clinic_name, city }] }` |

### 2. Админ-эндпоинты (требуют заголовок `X-Admin-Token`)

| Метод и путь | Назначение | Поведение |
|---|---|---|
| `GET /api/v1/admin/sources` | Список зарегистрированных адаптеров | Делегирует `IngestionService.list_sources()` |
| `GET /api/v1/admin/scrape-runs` | История запусков парсинга | Query: `source_id?`, `limit` (1..100). Делегирует `IngestionService.list_runs()` |
| `GET /api/v1/admin/scrape-errors` | Журнал ошибок парсинга | Query: `run_id?`, `source_id?`, `limit` (1..200). Делегирует `IngestionService.list_errors()` |
| `POST /api/v1/admin/scrape-runs` | Ручной запуск парсинга (+ опционально нормализация) | Body: `{source_ids?: list[str], limit?: int, normalize: bool = true}`. Защита `asyncio.Lock`: при уже запущенном сборе возвращает `409 SCRAPE_IN_PROGRESS`. Возвращает `{runs, normalization_summary}` |
| `GET /api/v1/admin/unmatched` | Очередь нераспознанных услуг | Query: `status` (`pending`\|`mapped`\|`ignored`), `page`, `page_size`. Обогащает `suggested_service_name` для 1-клик разметки |
| `POST /api/v1/admin/unmatched/{unmatched_id}/resolve` | Привязать к услуге справочника | Body: `{service_id: UUID, add_as_synonym: bool = true}`. Делегирует `NormalizationService.resolve_unmatched(...)` |
| `POST /api/v1/admin/unmatched/{unmatched_id}/ignore` | Пометить позицию как игнорируемую | Делегирует `NormalizationService.ignore_unmatched(...)` |
| `GET /api/v1/admin/stats` | Сводка по нормализованному слою | Делегирует `NormalizationService.get_stats()` |

## Code Style

```python
from fastapi import APIRouter, Depends, Query

from app.api.deps import get_query_service
from app.api.query_service import SearchQueryService
from app.api.schemas import OfferSearchResponse, OfferSortBy
from app.normalization.models import ServiceCategory

router = APIRouter(prefix="/offers", tags=["offers"])


@router.get("", response_model=OfferSearchResponse)
def search_offers(
    service_id: UUID | None = None,
    q: str | None = Query(default=None, max_length=120),
    city: str | None = Query(default=None, max_length=100),
    category: ServiceCategory | None = None,
    sort_by: OfferSortBy = OfferSortBy.PRICE_ASC,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    query_service: SearchQueryService = Depends(get_query_service),
) -> OfferSearchResponse:
    return query_service.search_offers(
        service_id=service_id,
        q=q,
        city=city,
        category=category,
        sort_by=sort_by,
        page=page,
        page_size=page_size,
    )
```

### Ключевые соглашения
- Валидация всех входных параметров (диапазоны цен, широта `[-90, 90]`, долгота `[-180, 180]`, `min_price <= max_price`, `2 <= len(clinic_ids) <= 5`, `lat` и `lng` передаются парой) выполняется **строго на границе API** с единым ответом `422 VALIDATION_ERROR`.
- Проверка `X-Admin-Token` — через `hmac.compare_digest` (устойчиво к timing-атакам).
- Денежные суммы в JSON отдаются как числа/строки через `Decimal` (единый формат, без потерь точности; в Pydantic сериализация `float` или `Decimal` — фиксируем `float` с 2 знаками / `Decimal` → в OpenAPI JSON числа `price_kzt: float` либо строка; в API для удобства графиков/фильтров JS-фронтенда отдаём `Decimal` с сериализацией числа `round(..., 2)` или `float` — см. Open Question).
- Все маршруты генерируют детерминированные URL для 2GIS (`https://2gis.kz/geo/{lng},{lat}` / поисковый fallback по адресу) и Google Maps (`https://www.google.com/maps/dir/?api=1&destination={lat},{lng}` или адрес).

## Testing Strategy

- **Фреймворк**: `pytest` + `pytest-asyncio` + `httpx.AsyncClient(transport=ASGITransport(app=app))` против реальной PostgreSQL 16 (`medprice_test`) — без моков БД.
- **Покрываемые сценарии**:
  1. **Health & Meta** (`test_health_and_meta.py`): `/health`, `/meta/filters`, CORS preflight headers, единый формат ошибок `404`/`422`.
  2. **Search, Autocomplete & Freshness** (`test_search_and_offers.py`):
     - Автодополнение по `ОАК` и `CBC` находит `Общий анализ крови (ОАК)`.
     - Фильтры по `city`, `category`, `min_price`/`max_price`, `min_rating`, `online_booking`.
     - Сортировка `price_asc`, `price_desc`, `distance_asc` (проверка расчёта Haversine по реальным координатам Алматы), `updated_desc`, `rating_desc`.
     - **Жёсткая проверка правила 30 дней**: предложение с `parsed_at = now - 31d` (даже если `is_active = True` в БД) НЕ попадает в `/offers` и в `/clinics/{id}`!
     - Пагинация (`page`, `page_size`, `total_items`, `total_pages`).
  3. **Clinics, Compare & Price History** (`test_clinics_and_compare.py`):
     - Карточка клиники возвращает все её активные услуги и ссылки маршрута 2GIS/Google Maps; неизвестный UUID → `404 NOT_FOUND`.
     - `/compare` сравнивает 2–5 клиник, помечает `cheapest_clinic_id`, и возвращает `422` при `< 2` или `> 5` клиниках.
     - `/services/{id}/price-history` возвращает хронологический ряд точек с именами клиник.
  4. **Admin Endpoints** (`test_admin_endpoints.py`):
     - Без `X-Admin-Token` или с неверным токеном → `401 UNAUTHORIZED`.
     - `unmatched` list → `resolve` → предложение появляется в публичном `/offers`!
     - `unmatched` → `ignore` → исчезает из `pending`.
     - `POST /admin/scrape-runs` возвращает результат и отдаёт `409 SCRAPE_IN_PROGRESS` при конкурентном вызове.
- **Живая проверка**: поднять API через `make api-up`, проверить `/docs`, `/api/v1/meta/filters`, `/api/v1/services/autocomplete?q=ОАК`, `/api/v1/offers?q=ОАК`, `/api/v1/compare` на реальных 499 предложениях в `medprice` и замерить время ответа (`< 500 мс`).
- **Целевое покрытие**: ≥ 85% по `app/api/` и `app/main.py`.

## Boundaries

- **Always**:
  - Соблюдать правило свежести `parsed_at >= now - 30 days` во всех публичных запросах выдачи (не полагаясь только на периодический джоб `refresh_stale_offers`).
  - Использовать единый формат ошибок `APIError` и единый формат пагинации на всех эндпоинтах.
  - Защищать все `/api/v1/admin/*` маршруты проверкой `X-Admin-Token`.
  - Проверять `make test-all`, `make lint`, `make typecheck` после каждой задачи.
- **Ask first**:
  - Добавление новых таблиц БД или изменение контрактов `ingestion` / `normalization`.
  - Введение полноценной пользовательской аутентификации (JWT/OAuth) — в V1 не требуется по ТЗ.
- **Never**:
  - Писать напрямую в `raw_service_records` или обходить `IngestionService` / `NormalizationService` при мутациях.
  - Утекать внутренние стектрейсы, SQL-запросы или `DATABASE_URL` в HTTP-ответы.
  - Возвращать просроченные (> 30 дней) цены как актуальные.

## Success Criteria

1. Все публичные и админ-эндпоинты из контракта реализованы, документированы в OpenAPI (`/docs`, `/openapi.json`) и возвращают единый формат ошибок и пагинации.
2. Поиск `/api/v1/offers` поддерживает все фильтры и сортировки из ТЗ 3.3 (город, категория, цена, рейтинг, онлайн-запись; сортировка по цене, расстоянию с геолокацией и дате обновления) и гарантированно скрывает предложения старше 30 дней.
3. Реализованы дополнительные API-возможности V1: клиники с GPS для карты Leaflet, ссылки маршрута 2GIS/Google Maps, сравнение 2–5 клиник в таблице (`/compare`) и история цен (`/services/{id}/price-history`).
4. Админ-эндпоинты защищены `X-Admin-Token`, позволяют вручную запустить парсинг + нормализацию (с блокировкой `409` от дублей) и разобрать `unmatched queue`.
5. Время ответа `/api/v1/offers` и `/api/v1/services/autocomplete` на реальной БД (`medprice`) `< 500 мс` (при требовании ТЗ `≤ 3 сек`).
6. `make test-all` (покрытие `app/api` ≥ 85%), `make lint` и `make typecheck` проходят без ошибок.

## Out of Scope (Deferred)

- **Elasticsearch / MeiliSearch** — V2; на объёмах MVP (сотни–тысячи услуг) PostgreSQL с индексами обеспечивает ответ `< 50–100 мс` без отдельного поискового кластера.
- **Подписки на изменение цены (`/api/v1/alerts`)** — V2 (кандидат на 5-й модуль `price-alerts`).
- **Rate-limiting публичного API через Redis** — V2; для MVP достаточно базовой защиты и блокировки параллельных запусков парсинга.
- **Прод-авторизация админов через OAuth2/RBAC** — V2; в V1 используется настраиваемый `ADMIN_API_TOKEN` в заголовке `X-Admin-Token`.

## Resolved Decisions

- **Формат цен в JSON-ответах**: внутри Python/PostgreSQL используется `Decimal`, при сериализации в JSON — число (`float`, округлённое до 2 знаков) для прямой работы с графиками, слайдерами и форматированием на фронтенде React.
- **Токен админки (`ADMIN_API_TOKEN`)**: конфигурируется через `.env` (`Settings`), с явным dev-значением по умолчанию `dev-admin-token` (с предупреждением в логе при старте) и проверкой через `hmac.compare_digest`.
- **Спецификация утверждена**: переходим к Phase 2 (Plan), Phase 3 (Tasks) и Phase 4 (Implement) для модуля `search-api`.

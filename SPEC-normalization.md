# Spec: Normalization (`normalization`) — V1

> Часть карты модулей [CAPABILITY-MAP.md](./CAPABILITY-MAP.md). Модуль `normalization` зависит только от [`ingestion`](./SPEC-ingestion.md) (читает raw-слой через `IngestionService.iter_raw_records`) и выступает поставщиком нормализованного каталога услуг, клиник, актуальных предложений, истории цен и очереди `unmatched` для `search-api`.

## Objective

Превратить разнородные сырые прайс-строки из `raw_service_records` в единую нормализованную витрину медицинских услуг Казахстана:

- Сформировать и загрузить **справочник услуг** (≥ 50 нормализованных позиций, целевой объём V1 — **60–80 позиций** по 4 категориям ТЗ: `лаборатория`, `приём врача`, `диагностика`, `процедура`), основанный на анализе реально собранных данных `kdlolymp.kz`, `invivo.kz`, `doq.kz`.
- Реализовать **детерминированный пайплайн нормализации** (`exact` → `synonym` → category-aware `RapidFuzz`), приводящий варианты вроде `«ОАК»`, `«Общий анализ крови (ОАК без СОЭ)»`, `«CBC»`, `«Клинический анализ крови»` к единой услуге справочника.
- Направлять нераспознанные услуги в **`unmatched queue`** с автоподсказкой ближайшего кандидата и возможностью ручной привязки (с автоматическим пополнением синонимов для будущих прогонов).
- Конвертировать цены в **KZT** (включая поддержку `USD → KZT`), дедуплицировать клиники и актуальные предложения (`service_offers`), отслеживать **историю изменения цен** (`price_history`) и отмечать устаревшие записи (> 30 дней) как `is_active = false`.

### Пользовательские и системные истории
- Как **поисковый API** (`search-api`), я получаю чистые нормализованные предложения по `(service_id, clinic_id)` с ценой в KZT, флагом актуальности (`is_active`), датой `parsed_at` и историей цен для графиков.
- Как **администратор**, я вижу очередь нераспознанных услуг (`unmatched_services`) с предложенным кандидатом и могу одним действием привязать позицию к услуге справочника (либо пометить как `ignored`), причём выбранное название добавляется в синонимы и больше не попадает в очередь.
- Как **система сбора** (`ingestion`), я остаюсь полностью независимой: `normalization` только читает мой контракт `IngestionService.iter_raw_records` и никогда не изменяет таблицы raw-слоя.

## Tech Stack

- **Рантайм**: Python 3.12 в контейнере `podman` (`medprice-backend:dev`, пересборка после добавления `rapidfuzz`)
- **Нормализация и матчинг**: `rapidfuzz>=3.10,<4.0` (добавляется в `backend/pyproject.toml`), стандартный `re`, `unicodedata`
- **БД и миграции**: PostgreSQL 16 (`medprice-pg`), `SQLAlchemy 2.0`, `alembic` (миграция `0002_normalization_layer.py`)
- **Валидация и конфиг**: `pydantic` v2, `pydantic-settings` (добавляем `USD_TO_KZT_RATE`, `FUZZY_MATCH_THRESHOLD`, `FUZZY_SUGGESTION_THRESHOLD`, `OFFER_MAX_AGE_DAYS`)
- **Тесты и качество**: `pytest`, `pytest-cov`, `ruff`, `mypy --strict`

## Commands

```bash
# Пересобрать backend-образ после добавления rapidfuzz
make backend-build

# Применить миграции БД (добавит таблицы normalization)
make migrate

# Загрузить/обновить справочник услуг (идемпотентный seed >= 50 позиций)
make seed-catalog

# Запустить нормализацию raw-записей в PostgreSQL
make normalize

# Запустить тесты модуля normalization с покрытием
make test-normalization

# Линтинг и проверка типов по всему backend
make lint
make typecheck
```

## Project Structure

```text
backend/
├── alembic/
│   └── versions/
│       └── 0002_normalization_layer.py   → Таблицы service_catalog, clinics, service_offers, price_history, unmatched_services
├── app/
│   └── normalization/
│       ├── __init__.py
│       ├── models.py                     → ORM-модели: ServiceCatalog, Clinic, ServiceOffer, PriceHistory, UnmatchedService
│       ├── schemas.py                    → Pydantic DTO (ServiceCatalogDTO, ClinicDTO, ServiceOfferDTO, UnmatchedServiceDTO, PriceHistoryPointDTO, NormalizationSummary)
│       ├── data/
│       │   └── catalog_seed.json         → Курируемый справочник (60–80 услуг, синонимы, 4 категории) на базе реальных данных РК
│       ├── text_utils.py                 → Очистка текста (ё→е, пунктуация, префиксы, аббревиатуры) и конвертация валют (USD→KZT)
│       ├── matcher.py                    → Детерминированный матчер: exact → synonym → category-aware RapidFuzz
│       ├── pipeline.py                   → NormalizationPipeline: чтение из IngestionService, upsert клиник/предложений, снимки price_history, unmatched queue
│       ├── service.py                    → NormalizationService (публичный контракт для search-api и CLI)
│       └── cli.py                        → CLI: seed-catalog, run, refresh-stale, stats
└── tests/
    └── normalization/
        ├── test_text_and_currency.py     → Юнит-тесты нормализации текста и конвертации KZT/USD
        ├── test_matcher.py               → Юнит-тесты exact/synonym/fuzzy, разделения категорий, порогов и кандидатов
        ├── test_catalog_seed.py          → Проверка полноты справочника (>= 50 позиций, уникальные коды, все 4 категории, без пустых синонимов)
        ├── test_pipeline.py              → Интеграционные тесты против PostgreSQL: дедупликация, price_history, unmatched queue, stale > 30d
        └── test_service.py               → Тесты публичного контракта NormalizationService (включая resolve_unmatched + пополнение синонимов)
```

## Data Model & Provider Interface Contract

Этот контракт определяет границу модуля `normalization` для потребителя (`search-api`).

### 1. Таблицы БД (нормализованный слой)

1. **`service_catalog`** — канонический справочник услуг (≥ 50 позиций):
   - `id` (UUID, PK)
   - `code` (String(64), unique, indexed) — стабильный машинный код (напр. `lab_oak`, `doc_terapevt`, `diag_uzi_obp`)
   - `canonical_name` (String(256), unique, indexed) — единое название (напр. `Общий анализ крови (ОАК)`)
   - `category` (Enum `service_category_enum`: `lab` | `doctor` | `diagnostics` | `procedure`) — соответствует ТЗ: лаборатория / приём врача / диагностика / процедура
   - `synonyms` (JSONB, `list[str]`) — список синонимов и аббревиатур (`["ОАК", "CBC", "Клинический анализ крови", ...]`)
   - `description` (Text, nullable)
   - `is_active` (Boolean, default `True`)
   - `created_at` / `updated_at` (DateTime TZ)

2. **`clinics`** — дедуплицированные клиники и филиалы:
   - `id` (UUID, PK)
   - `source_id` (String(64), indexed)
   - `clinic_key` (String(64), unique, indexed) — SHA-256 от `(source_id, norm(clinic_name), norm(city), norm(address))`
   - `clinic_name` (Text, nullable=False)
   - `city` (String(128), index=True, nullable=False)
   - `address` (Text, nullable)
   - `phone` (String(128), nullable)
   - `working_hours` (Text, nullable)
   - `latitude` (Float, nullable), `longitude` (Float, nullable)
   - `rating` (Float, nullable) — шкала `0.0..5.0`
   - `has_online_booking` (Boolean, default `False`)
   - `website_url` (Text, nullable)
   - `updated_at` (DateTime TZ)

3. **`service_offers`** — актуальные нормализованные предложения клиник (покрывает все поля ТЗ 2.2):
   - `id` (UUID, PK)
   - `clinic_id` (UUID, FK → `clinics.id`, indexed)
   - `service_id` (UUID, FK → `service_catalog.id`, indexed)
   - `raw_record_id` (UUID, FK → `raw_service_records.id`, indexed)
   - `source_id` (String(64), indexed)
   - `source_url` (Text, nullable=False)
   - `service_name_raw` (Text, nullable=False)
   - `service_name_norm` (String(256), nullable=False)
   - `category` (Enum `service_category_enum`, indexed)
   - `price_kzt` (Numeric(12, 2), indexed, nullable=False)
   - `original_price` (Numeric(12, 2), nullable=False)
   - `currency` (Enum `currency_enum`: `KZT` | `USD`, nullable=False)
   - `duration_days` (Int, nullable)
   - `match_method` (Enum `match_method_enum`: `exact` | `synonym` | `fuzzy` | `manual`)
   - `match_score` (Float, nullable=False) — `0..100`
   - `parsed_at` (DateTime TZ, indexed, nullable=False)
   - `is_active` (Boolean, indexed, default `True`)
   - **Unique constraint**: `UNIQUE (clinic_id, service_id)` — одна актуальная цена на пару `(клиника, нормализованная услуга)`; при наличии нескольких сырых вариантов одной и той же услуги в одной клинике сохраняется самая свежая (а при равной свежести — минимальная цена).

4. **`price_history`** — снимки цен для графика динамики:
   - `id` (UUID, PK)
   - `clinic_id` (UUID, FK → `clinics.id`, indexed)
   - `service_id` (UUID, FK → `service_catalog.id`, indexed)
   - `offer_id` (UUID, FK → `service_offers.id`, nullable=True, ondelete=`SET NULL`)
   - `price_kzt` (Numeric(12, 2), nullable=False)
   - `recorded_at` (DateTime TZ, indexed, nullable=False)
   - Запись добавляется при первом появлении пары `(clinic_id, service_id)` и при каждом изменении `price_kzt` относительно последней точки истории (повторный прогон при неизменной цене дубли в `price_history` **не создаёт**).

5. **`unmatched_services`** — очередь ручной разметки:
   - `id` (UUID, PK)
   - `raw_record_id` (UUID, FK → `raw_service_records.id`, unique, indexed)
   - `source_id` (String(64), indexed)
   - `clinic_name_raw` (Text)
   - `city_raw` (String(128))
   - `service_name_raw` (Text, nullable=False)
   - `category_hint` (String(128), nullable)
   - `price_kzt` (Numeric(12, 2), nullable=False)
   - `suggested_service_id` (UUID, FK → `service_catalog.id`, nullable)
   - `suggested_score` (Float, nullable)
   - `status` (Enum `unmatched_status_enum`: `pending` | `mapped` | `ignored`, indexed, default `pending`)
   - `resolved_service_id` (UUID, FK → `service_catalog.id`, nullable)
   - `resolved_at` (DateTime TZ, nullable)
   - `created_at` (DateTime TZ, nullable=False)

### 2. Python-контракт (`NormalizationService`)

- `seed_catalog() -> SeedSummary` — идемпотентная загрузка/обновление справочника из `catalog_seed.json`.
- `run_normalization(updated_since: datetime | None = None, source_id: str | None = None) -> NormalizationSummary` — потоковое чтение raw-записей из `IngestionService`, матчинг, upsert `clinics`/`service_offers`, запись точек в `price_history` и пополнение `unmatched_services`.
- `list_catalog(category: ServiceCategory | None = None, query: str | None = None) -> list[ServiceCatalogDTO]` — список нормализованных услуг (для автодополнения и админки).
- `list_unmatched(status: UnmatchedStatus = UnmatchedStatus.PENDING, limit: int = 50, offset: int = 0) -> list[UnmatchedServiceDTO]` — просмотр очереди ручной разметки.
- `resolve_unmatched(unmatched_id: UUID, service_id: UUID, *, add_as_synonym: bool = True) -> ServiceOfferDTO` — ручная привязка нераспознанной записи к услуге справочника, создание/обновление `service_offers` и опциональное добавление `service_name_raw` в синонимы (плюс автоматический перематчинг совпадающих `pending`-записей с тем же `service_name_raw`).
- `ignore_unmatched(unmatched_id: UUID) -> UnmatchedServiceDTO` — пометка шумной/нерелевантной позиции как `ignored`.
- `get_price_history(service_id: UUID, clinic_id: UUID | None = None, days: int = 90) -> list[PriceHistoryPointDTO]` — история изменения цен для графика в UI.
- `refresh_stale_offers(max_age_days: int = 30) -> int` — выставляет `is_active = False` всем предложениям с `parsed_at < now - max_age_days`.

## Code Style

```python
from dataclasses import dataclass
from enum import StrEnum
import uuid


class MatchMethod(StrEnum):
    EXACT = "exact"
    SYNONYM = "synonym"
    FUZZY = "fuzzy"
    MANUAL = "manual"


@dataclass(frozen=True, slots=True)
class MatchResult:
    service_id: uuid.UUID | None
    canonical_name: str | None
    method: MatchMethod | None
    score: float
    suggested_service_id: uuid.UUID | None = None
    suggested_score: float | None = None

    @property
    def is_matched(self) -> bool:
        return self.service_id is not None
```

### Ключевые соглашения
- Все денежные вычисления и конвертация `USD → KZT` — строго через `Decimal` с округлением `ROUND_HALF_UP` до `0.01`.
- Категорийная изоляция в fuzzy-матчере: при наличии `category_hint` (`лаборатория`, `приём врача`, `диагностика`, `процедура`) `RapidFuzz` сопоставляет только в рамках соответствующей категории `ServiceCategory`, исключая ложные склейки (напр. «Анализ крови на ТТГ» не может сматчиться с «Приём эндокринолога»).
- `normalization` **никогда** не пишет в таблицы `raw_service_records`, `scrape_runs`, `scrape_errors` — только читает через `IngestionService.iter_raw_records`.
- Форматирование и строгая типизация: `ruff check` + `mypy --strict`.

## Testing Strategy

- **Фреймворк**: `pytest` + `pytest-cov` против реальной тестовой БД `medprice_test` (PostgreSQL 16).
- **Уровни тестов**:
  1. **Unit-тесты текста и валют** (`test_text_and_currency.py`): `ё→е`, кавычки/звёздочки, аббревиатуры (`ОАК`/`CBC`), конвертация `KZT` и `USD → KZT` через `Decimal`.
  2. **Unit-тесты матчера** (`test_matcher.py`): точное совпадение, синонимы, fuzzy-матчинг выше порога, отправка в unmatched ниже порога с `suggested_service_id`, запрет меж-категорийного ложного матча.
  3. **Валидация справочника** (`test_catalog_seed.py`): ≥ 50 позиций, уникальные `code` и `canonical_name`, представлены все 4 категории, валидный JSON, идемпотентность повторного `seed_catalog()`.
  4. **Интеграционные тесты пайплайна и сервиса** (`test_pipeline.py`, `test_service.py`):
     - Прогон raw-записей создаёт `clinics`, `service_offers`, `price_history` и `unmatched_services`.
     - Повторный прогон тех же данных не создаёт дублей ни в `service_offers`, ни в `price_history`, ни в `unmatched_services`.
     - Изменение цены в raw-слое обновляет `service_offers.price_kzt` и добавляет новую точку в `price_history`.
     - `resolve_unmatched(..., add_as_synonym=True)` переводит запись в `mapped`, создаёт `service_offers` и позволяет повторным записям с тем же названием матчиться через `synonym`.
     - `refresh_stale_offers(30)` деактивирует предложения старше 30 дней и сохраняет свежие активными.
- **Живая проверка**: запуск `make seed-catalog && make normalize` на реальных **1 427 записях** в PostgreSQL (`medprice`).
- **Целевое покрытие**: ≥ 85% по `app/normalization/`.

## Boundaries

- **Always**:
  - Хранить справочник `catalog_seed.json` под версионным контролем и проверять автотестом порог ≥ 50 позиций.
  - Использовать `Decimal` для всех цен и курсов валют.
  - Проверять `pytest`, `ruff check` и `mypy --strict` после каждой задачи.
  - Соблюдать одностороннюю зависимость `normalization → ingestion`.
- **Ask first**:
  - Изменение схемы уже задеплоенных таблиц `ingestion` (таблицы `normalization` добавляются новой миграцией `0002`).
  - Изменение подхода к нормализации (напр. подключение внешнего LLM API — остаётся в V2).
- **Never**:
  - Изменять или удалять строки в `raw_service_records` из модуля `normalization`.
  - Скрывать нераспознанные услуги (каждая нераспознанная строка обязана попасть в `unmatched_services`).
  - Склеивать услуги разных категорий через fuzzy-матчинг без ручного подтверждения.

## Success Criteria

1. Справочник `service_catalog` содержит **≥ 50 нормализованных позиций** (целевой ориентир 60–80) с синонимами по всем 4 категориям ТЗ (`lab`, `doctor`, `diagnostics`, `procedure`), загружается идемпотентно через `make seed-catalog`.
2. Детерминированный матчер (`exact` → `synonym` → `RapidFuzz`) корректно сводит синонимы (включая кейс ТЗ `«ОАК»` / `«Общий анализ крови»` / `«CBC»` / `«Клинический анализ крови»` → единая услуга) и не допускает меж-категорийных склеек.
3. Конвертация `KZT` / `USD → KZT` работает через `Decimal` и покрыта тестами.
4. Живой прогон `make normalize` на реальных 1 427 raw-записях из `kdlolymp`, `invivo`, `doq` заполняет `clinics`, `service_offers`, `price_history` и `unmatched_services`, обеспечивая **реальные пересечения между клиниками** (одна нормализованная услуга — предложения из нескольких клиник/лабораторий для сравнения цен!).
5. Повторный запуск `make normalize` идемпотентен: 0 дублей в `clinics`, `service_offers`, `price_history` и `unmatched_services`.
6. Ручная разметка через `resolve_unmatched` переводит позицию из `unmatched_services` в `service_offers` и пополняет синонимы.
7. `refresh_stale_offers(30)` корректно снимает `is_active` у предложений старше 30 дней.
8. `make test-normalization` (покрытие ≥ 85%), `make lint` и `make typecheck` проходят без ошибок.

## Out of Scope (Deferred)

- **LLM / embedding-матчинг** (OpenAI / Gemini API) — V2; в V1 используется быстрый детерминированный пайплайн (словарь + RapidFuzz + ручная разметка).
- **Автоматическая загрузка курса USD с API Нацбанка РК (НБРК)** — V2; в V1 курс задаётся через `USD_TO_KZT_RATE` в конфигурации (`Settings`).
- **Объединение филиалов одной сети с разных агрегаторов** (cross-source clinic entity resolution, напр. сопоставление `AQmed` на `doq.kz` с внешним сайтом `aqmed.kz`) — V2; в V1 клиники дедуплицируются в пределах `(source_id, clinic_name, city, address)`.
- **REST-эндпоинты и UI для `unmatched queue`** — принадлежат модулям `search-api` и `web-ui` (следующие спецификации).

## Resolved Decisions

- **Порог автоматического fuzzy-матчинга**: `FUZZY_MATCH_THRESHOLD = 86.0`, порог автоподсказки в `unmatched_services`: `FUZZY_SUGGESTION_THRESHOLD = 60.0` (конфигурируются через `Settings`).
- **Курс конвертации USD → KZT**: `USD_TO_KZT_RATE = 495.00` по умолчанию (переопределяется через `.env`).
- **Спецификация утверждена**: переходим к Phase 2 (Plan) и Phase 3 (Tasks) для модуля `normalization`.

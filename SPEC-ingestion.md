# Spec: Ingestion (`ingestion`) — V1

> Часть карты модулей [CAPABILITY-MAP.md](./CAPABILITY-MAP.md). Модуль `ingestion` не зависит от других модулей и выступает поставщиком сырых данных и метаданных парсинга для `normalization` и `search-api`.

## Objective

Реализовать отказоустойчивый, расширяемый модуль сбора прайс-листов медицинских услуг с открытых источников Казахстана (сайты лабораторий, клиник и агрегаторов).

### Пользовательские и системные истории
- Как **система нормализации** (`normalization`), я получаю структурированные сырые записи услуг и клиник из raw-слоя с отметкой времени парсинга (`parsed_at`), не теряя историю изменений цен и не получая дубликатов при повторном запуске.
- Как **оператор / API** (`search-api`), я могу запустить сбор по всем или выбранным источникам вручную либо по расписанию (cron / планировщик) и просмотреть статусы запусков и журнал ошибок.
- Как **разработчик**, я могу подключить новый источник (HTML, JSON, PDF, DOCX или Excel), добавив один класс-адаптер без изменения ядра парсера, БД или оркестратора.
- Как **владелец платформы**, я гарантирую соблюдение `robots.txt`, ограничение частоты запросов, отсутствие парсинга закрытых разделов и хранение сырых данных не менее 90 дней для аудита.

## Tech Stack

- **Язык и рантайм**: Python 3.12 в контейнере `podman` (`python:3.12-slim`), чтобы гарантировать совместимость binary wheels независимо от хостового Python 3.15
- **HTTP и парсинг**:
  - `httpx` (асинхронный/синхронный HTTP-клиент с таймаутами и ретраями)
  - `beautifulsoup4` + `lxml` (HTML)
  - `pdfplumber` (PDF-прайс-листы)
  - `python-docx` (DOCX-прайс-листы)
  - `openpyxl` (Excel `.xlsx` прайс-листы)
  - Стандартный `urllib.robotparser` (проверка `robots.txt`)
- **БД и миграции**: PostgreSQL 16 (`postgres:16-alpine` через `podman` в общей сети/поде), `SQLAlchemy 2.0`, `psycopg[binary]`, `alembic`
- **Валидация и конфиг**: `pydantic` v2, `pydantic-settings`
- **Планировщик**: `APScheduler` (плюс CLI-команда для системного `cron`)
- **Тесты и линтинг**: `pytest`, `pytest-asyncio`, `pytest-cov`, `respx` (моки HTTP), `ruff`, `mypy`

## Commands

```bash
# Создать podman-сеть и поднять PostgreSQL 16 (поддерживается через Makefile)
podman network exists medprice-net || podman network create medprice-net
podman run -d --name medprice-pg --network medprice-net \
  -e POSTGRES_USER=medprice -e POSTGRES_PASSWORD=medprice -e POSTGRES_DB=medprice \
  -p 5432:5432 postgres:16-alpine

# Собрать контейнер backend (Python 3.12)
podman build -t medprice-backend:dev -f backend/Containerfile backend

# Применить миграции БД внутри контейнера
podman run --rm --network medprice-net -v ./backend:/app:Z \
  -e DATABASE_URL=postgresql+psycopg://medprice:medprice@medprice-pg:5432/medprice \
  medprice-backend:dev alembic upgrade head

# Запустить парсинг всех активных источников вручную
podman run --rm --network medprice-net -v ./backend:/app:Z \
  -e DATABASE_URL=postgresql+psycopg://medprice:medprice@medprice-pg:5432/medprice \
  medprice-backend:dev python -m app.ingestion.cli run --source all

# Запустить парсинг одного источника / список источников
podman run --rm --network medprice-net -v ./backend:/app:Z \
  -e DATABASE_URL=postgresql+psycopg://medprice:medprice@medprice-pg:5432/medprice \
  medprice-backend:dev python -m app.ingestion.cli run --source kdlolymp --limit 50
podman run --rm --network medprice-net -v ./backend:/app:Z \
  medprice-backend:dev python -m app.ingestion.cli list-sources

# Запуск тестов модуля ingestion с покрытием
podman run --rm --network medprice-net -v ./backend:/app:Z \
  -e DATABASE_URL=postgresql+psycopg://medprice:medprice@medprice-pg:5432/medprice \
  medprice-backend:dev pytest tests/ingestion --cov=app.ingestion --cov-report=term-missing

# Линтинг и проверка типов
podman run --rm -v ./backend:/app:Z medprice-backend:dev ruff check app/ingestion tests/ingestion
podman run --rm -v ./backend:/app:Z medprice-backend:dev mypy app/ingestion
```

## Project Structure

```text
backend/
├── alembic.ini
├── alembic/
│   └── versions/                  → Миграции БД (таблицы raw-слоя)
├── pyproject.toml                 → Зависимости, конфиг ruff, pytest, mypy
├── app/
│   ├── core/
│   │   ├── config.py              → Настройки (DATABASE_URL, rate limits, User-Agent, retention)
│   │   └── db.py                  → SQLAlchemy engine, SessionLocal, Base
│   └── ingestion/
│       ├── __init__.py
│       ├── models.py              → ORM-модели: ScrapeRun, RawServiceRecord, ScrapeError
│       ├── schemas.py             → Pydantic DTO (RawServiceInput, ScrapeRunDTO, ScrapeErrorDTO, SourceInfo)
│       ├── http_client.py         → PoliteHttpClient: robots.txt cache, per-domain delay + jitter, retries
│       ├── extractors/
│       │   ├── html.py            → Утилиты извлечения таблиц/карточек из HTML
│       │   ├── pdf.py             → Извлечение табличных прайсов из PDF (pdfplumber)
│       │   ├── docx.py            → Извлечение таблиц из DOCX (python-docx)
│       │   └── excel.py           → Извлечение строк прайса из XLSX (openpyxl)
│       ├── adapters/
│       │   ├── base.py            → BaseSourceAdapter (ABC) + SourceMetadata
│       │   ├── registry.py        → Реестр адаптеров (подключение новых источников без правок ядра)
│       │   └── <source>.py        → Адаптеры реальных источников (минимум 3–5, напр. kdlolymp, invitro, doq, helix/olymp)
│       ├── runner.py              → IngestionRunner: изоляция ошибок по источникам, дедупликация, запись raw-слоя
│       ├── service.py             → IngestionService (публичный контракт для normalization и search-api)
│       ├── scheduler.py           → Настройка периодического запуска (по умолчанию 1 раз в сутки)
│       └── cli.py                 → CLI-интерфейс (run, list-sources, purge-expired)
└── tests/
    └── ingestion/
        ├── fixtures/              → Сохранённые HTML/JSON/PDF/DOCX/XLSX-фикстуры для офлайн-тестов
        ├── test_http_client.py    → Тесты robots.txt, rate-limit, retry
        ├── test_extractors.py     → Юнит-тесты HTML, PDF, DOCX, Excel экстракторов
        ├── test_adapters.py       → Контрактные тесты адаптеров на сохранённых фикстурах
        ├── test_runner.py         → Дедупликация, изоляция сбоев, retention, аудит ошибок
        └── test_service.py        → Тесты публичного контракта IngestionService
```

## Data Model & Provider Interface Contract

Этот контракт определяет границу модуля `ingestion` для потребителей (`normalization`, `search-api`).

### 1. Таблицы БД (raw-слой)

1. **`scrape_runs`** — журнал запусков парсинга:
   - `id` (UUID, PK)
   - `source_id` (String, indexed) — идентификатор адаптера (напр. `kdlolymp`, `invitro`, `doq`)
   - `triggered_by` (Enum: `manual` | `cron`)
   - `status` (Enum: `running` | `success` | `partial` | `failed`)
   - `started_at` (DateTime TZ)
   - `finished_at` (DateTime TZ, nullable)
   - `records_fetched` (Int) — всего извлечено адаптером
   - `records_inserted` (Int) — новых уникальных записей в raw-слое
   - `records_updated` (Int) — существующих записей с обновлённым `last_seen_at`/`parsed_at`
   - `errors_count` (Int)

2. **`raw_service_records`** — сырые записи (отдельно от нормализованного слоя, хранятся ≥ 90 дней):
   - `id` (UUID, PK)
   - `source_id` (String, indexed)
   - `source_url` (Text) — конкретная страница/документ прайса
   - `record_fingerprint` (String(64), indexed) — SHA-256 от канонического ключа `(source_id, clinic_name_raw, city_raw, address_raw, service_name_raw, price_raw, currency_raw, duration_days_raw)`
   - `clinic_name_raw` (Text)
   - `city_raw` (String)
   - `address_raw` (Text, nullable)
   - `phone_raw` (String, nullable)
   - `working_hours_raw` (Text, nullable)
   - `latitude` (Float, nullable), `longitude` (Float, nullable)
   - `clinic_rating_raw` (Float, nullable)
   - `has_online_booking` (Boolean, nullable)
   - `service_name_raw` (Text)
   - `category_hint` (String, nullable) — подсказка категории с сайта источника
   - `price_raw` (Numeric(12, 2))
   - `currency_raw` (String(8), default `KZT`)
   - `duration_days_raw` (Int, nullable)
   - `raw_payload` (JSONB) — исходный фрагмент/строка данных для аудита
   - `first_seen_at` (DateTime TZ)
   - `last_seen_at` (DateTime TZ, indexed)
   - `parsed_at` (DateTime TZ, indexed) — время последнего подтверждения парсером
   - `last_run_id` (UUID, FK → `scrape_runs.id`)
   - **Unique constraint**: `UNIQUE (source_id, record_fingerprint)` — гарантирует дедупликацию при повторном запуске без потери новой записи при изменении цены.

3. **`scrape_errors`** — журнал ошибок парсинга:
   - `id` (UUID, PK)
   - `run_id` (UUID, FK → `scrape_runs.id`, indexed)
   - `source_id` (String, indexed)
   - `url` (Text, nullable)
   - `error_type` (String) — напр. `robots_disallowed`, `http_error`, `timeout`, `parse_error`
   - `message` (Text)
   - `details` (JSONB, nullable)
   - `occurred_at` (DateTime TZ)

### 2. Python-контракт (`IngestionService`)

- `list_sources() -> list[SourceInfo]` — список зарегистрированных адаптеров (id, название, формат, города, enabled).
- `trigger_run(source_ids: list[str] | None = None, triggered_by: Literal["manual", "cron"] = "manual") -> list[ScrapeRunDTO]` — запуск парсинга с полной изоляцией ошибок между источниками.
- `list_runs(source_id: str | None = None, limit: int = 20) -> list[ScrapeRunDTO]` — история запусков.
- `list_errors(run_id: UUID | None = None, source_id: str | None = None, limit: int = 50) -> list[ScrapeErrorDTO]` — журнал ошибок.
- `iter_raw_records(updated_since: datetime | None = None, source_id: str | None = None, batch_size: int = 500) -> Iterator[list[RawServiceRecordDTO]]` — потоковое чтение raw-записей для модуля `normalization`.
- `purge_expired_raw_records(retention_days: int = 90) -> int` — удаление raw-записей, у которых `last_seen_at < now() - retention_days` (минимум 90 дней, защита от значения `< 90`).

## Code Style

```python
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from decimal import Decimal
from pydantic import BaseModel, Field, HttpUrl


class RawServiceInput(BaseModel):
    clinic_name_raw: str = Field(min_length=1)
    city_raw: str = Field(min_length=1)
    address_raw: str | None = None
    phone_raw: str | None = None
    working_hours_raw: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    clinic_rating_raw: float | None = None
    has_online_booking: bool | None = None
    service_name_raw: str = Field(min_length=1)
    category_hint: str | None = None
    price_raw: Decimal = Field(gt=0)
    currency_raw: str = "KZT"
    duration_days_raw: int | None = Field(default=None, ge=0)
    source_url: HttpUrl
    raw_payload: dict[str, object] = Field(default_factory=dict)


class BaseSourceAdapter(ABC):
    source_id: str
    display_name: str
    supported_format: str  # "html" | "json" | "pdf" | "docx" | "excel"

    @abstractmethod
    async def fetch_records(
        self,
        client: "PoliteHttpClient",
        limit: int | None = None,
    ) -> AsyncIterator[RawServiceInput]:
        """Yields parsed raw records without mutating DB directly."""
        ...
```

### Ключевые соглашения
- Типизация всех публичных функций и DTO (`mypy` без ошибок).
- Адаптеры **никогда** не обращаются к БД напрямую — они только отдают поток `RawServiceInput`; всю дедупликацию, транзакции и запись ошибок выполняет `IngestionRunner`.
- Денежные суммы — строго `Decimal` (никогда `float`).
- Все временные метки — timezone-aware UTC (`datetime.now(timezone.utc)`).
- Форматирование и импорты — `ruff` (line-length 100).

## Testing Strategy

- **Фреймворк**: `pytest` + `pytest-asyncio` + `respx` (никаких реальных сетевых запросов в CI/юнит-тестах).
- **Уровни тестов**:
  1. **Unit-тесты экстракторов** (`test_extractors.py`): проверка извлечения строк прайса из фикстур HTML, PDF, DOCX, XLSX (включая битые строки, пустые цены, валюты KZT/USD).
  2. **Unit-тесты `PoliteHttpClient`** (`test_http_client.py`): проверка запрета по `robots.txt`, соблюдения задержки между запросами к одному домену, обработки HTTP 429/5xx и таймаутов.
  3. **Контрактные тесты адаптеров** (`test_adapters.py`): прогон каждого реального адаптера на сохранённых локальных снэпшотах страниц/API.
  4. **Интеграционные тесты `IngestionRunner` & `IngestionService`** (`test_runner.py`, `test_service.py`):
     - Повторный запуск того же набора данных не создаёт дубликатов (`records_inserted == 0`, `records_updated == N`).
     - Изменение цены по той же услуге создаёт новую raw-запись (старая сохраняется для аудита).
     - Падение одного адаптера записывается в `scrape_errors` и не мешает успешному завершению остальных адаптеров.
     - `purge_expired_raw_records` не допускает `retention_days < 90` и удаляет только записи старше порога.
- **Живая проверка (manual smoke)**: отдельный CLI-запуск против реальных целевых сайтов перед сдачей, результат фиксируется в БД (≥ 3 реальных источника, ≥ 100 услуг).
- **Целевое покрытие**: ≥ 80% по `app/ingestion/`.

## Boundaries

- **Always**:
  - Проверять `robots.txt` целевого домена перед парсингом и соблюдать задержку между запросами (≥ 1.5 сек на домен).
  - Валидировать каждую запись через Pydantic до записи в БД; некорректные записи логировать в `scrape_errors`, а не ронять весь запуск.
  - Запускать `pytest` и `ruff check` перед завершением каждой задачи.
  - Хранить сырые данные в raw-слое с политикой ретеншна ≥ 90 дней.
- **Ask first**:
  - Изменение схемы БД после утверждения спеки или добавление тяжёлых зависимостей (напр. Playwright/Chromium, если какой-то источник окажется строго JS-only и не будет иметь публичного JSON API).
  - Замена или исключение целевого источника из выбранного набора, если сайт заблокирован `robots.txt` или антибот-защитой.
- **Never**:
  - Обходить авторизацию, CAPTCHA или `robots.txt`.
  - Собирать персональные данные пациентов.
  - Запускать агрессивный параллельный обход без задержек на один домен.
  - Коммитить секреты, дампы с ПДн или удалять падающие тесты.

## Success Criteria

1. Реализовано и протестировано ядро `ingestion` с поддержкой экстракторов для **HTML, PDF, DOCX, Excel** (все 4 покрыты юнит-тестами на фикстурах).
2. Подключено **минимум 3 реальных открытых источника** из списка ТЗ (целевой ориентир: 3–5 источников с охватом ≥ 3 городов РК), живой запуск собирает **≥ 100 реальных записей услуг** в `raw_service_records`.
3. Повторный запуск парсера на неизменных данных даёт **0 дубликатов** (`records_inserted == 0`) и обновляет `parsed_at` / `last_seen_at`.
4. При искусственном или реальном сбое одного источника остальные источники завершают сбор со статусом `success`, а ошибка фиксируется в `scrape_errors` с указанием `source_id`, `url`, `error_type` и `message`.
5. Добавление нового тестового источника в `adapters/` + регистрация в `registry.py` не требует правок в `runner.py`, `models.py`, `service.py` или `cli.py`.
6. Возможен запуск как вручную (через CLI и через `IngestionService.trigger_run`), так и по расписанию (через `scheduler.py` / cron).
7. `pytest tests/ingestion` и `ruff check` проходят полностью без ошибок.

## Out of Scope (Deferred)

- **Headless-браузеры (Playwright / Selenium)** — отложены; добавляем только по согласованию (`Ask first`), если для ключевых источников не найдётся HTML/JSON/PDF-эндпоинтов.
- **Распределённая очередь задач (Celery + Redis)** — отложена до V2; для MVP достаточно `APScheduler` + асинхронный `IngestionRunner`.
- **Нормализация названий услуг, справочник, конвертация валют и `unmatched queue`** — принадлежат модулю `normalization` (следующая спецификация).
- **Геокодирование адресов через платные API** — в V1 координаты берутся из открытых данных источника/2GIS-карточек, если доступны; отдельное массовое геокодирование — V2.

## Resolved Decisions

- **Среда выполнения**: Python 3.12 в контейнере `podman` + PostgreSQL 16 (`podman`, без `podman compose`).
- **Режим разработки**: строгий помодульный SDD (`SPEC` → `Plan` → `Tasks` → `Implement` для `ingestion`, затем переход к `normalization`).
- **Утверждённые реальные источники V1**: `kdlolymp.kz`, `invivo.kz`, `doq.kz` (все проверены на разрешающий `robots.txt` и валидный TLS; `invitro.kz` исключён из-за `robots.txt: Disallow: /`, `helix.kz` исключён из-за невалидной TLS-цепочки).

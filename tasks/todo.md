# Task List: Ingestion (`ingestion`) — V1

Source plan: [tasks/plan.md](./plan.md) | Source spec: [SPEC-ingestion.md](../SPEC-ingestion.md)

---

## Task 1: Подготовить `podman`-окружение (Python 3.12 + PostgreSQL 16), `pyproject.toml` и `Makefile`

**Description:** Создать минимальный воспроизводимый каркас backend-проекта с контейнером Python 3.12 (`backend/Containerfile`), описанием зависимостей и инструментов качества (`pyproject.toml`) и `Makefile` для управления сетью `podman`, контейнером PostgreSQL 16 и запуском тестов/линтеров.

**Acceptance criteria:**
- [x] `backend/Containerfile` собирается на базе `python:3.12-slim` со всеми зависимостями модуля `ingestion` (`sqlalchemy`, `psycopg[binary]`, `alembic`, `httpx`, `beautifulsoup4`, `lxml`, `pdfplumber`, `python-docx`, `openpyxl`, `pydantic-settings`, `apscheduler`, `pytest`, `pytest-asyncio`, `pytest-cov`, `respx`, `ruff`, `mypy`).
- [x] `Makefile` предоставляет команды `db-up`, `db-down`, `backend-build`, `migrate`, `test-ingestion`, `lint`, `typecheck`.
- [x] PostgreSQL 16 запускается в сети `medprice-net` и отвечает на `pg_isready`.

**Verification:**
- [x] Build succeeds: `make backend-build && make db-up`
- [x] Tests pass: `make test-ingestion` (запускает `pytest` внутри контейнера без ошибок импорта)
- [x] Manual check: `podman exec medprice-pg pg_isready -U medprice` возвращает `accepting connections`

**Dependencies:** None

**Files likely touched:**
- `Makefile`
- `backend/Containerfile`
- `backend/pyproject.toml`
- `backend/app/__init__.py`
- `backend/tests/__init__.py`

**Estimated scope:** Medium (5 files)

---

## Task 2: Реализовать конфиг, подключение БД, ORM-модели raw-слоя и миграцию Alembic

**Description:** Создать конфигурацию (`Settings` через `pydantic-settings`), движок/сессию SQLAlchemy 2.0, ORM-модели raw-слоя (`ScrapeRun`, `RawServiceRecord`, `ScrapeError` с уникальным ключом `(source_id, record_fingerprint)` и индексами) и первую миграцию Alembic.

**Acceptance criteria:**
- [x] Таблицы `scrape_runs`, `raw_service_records`, `scrape_errors` создаются миграцией Alembic со всеми полями, типами (`Numeric(12, 2)`, timezone-aware `DateTime`, `JSONB`), FK и `UNIQUE (source_id, record_fingerprint)`.
- [x] Миграция обратима (`alembic upgrade head` → `alembic downgrade base` → `alembic upgrade head` проходит без ошибок).
- [x] Конфиг считывает `DATABASE_URL`, `USER_AGENT`, `DEFAULT_MIN_DELAY_SEC` (≥ 1.5), `RAW_RETENTION_DAYS` (≥ 90).

**Verification:**
- [x] Tests pass: `make migrate && make test-ingestion`
- [x] Build succeeds: `make lint && make typecheck`
- [x] Manual check: проверить созданные таблицы и constraints в PostgreSQL через `\dt` и `\d raw_service_records`

**Dependencies:** Task 1

**Files likely touched:**
- `backend/app/core/config.py`
- `backend/app/core/db.py`
- `backend/app/ingestion/models.py`
- `backend/alembic.ini`
- `backend/alembic/env.py` + `backend/alembic/versions/0001_ingestion_raw_layer.py`

**Estimated scope:** Medium (5 files)

---

## Checkpoint 1: After Tasks 1–2 (Foundation)
- [x] Контейнер `medprice-backend:dev` (Python 3.12) собран и `medprice-pg` (PostgreSQL 16) работает
- [x] `alembic upgrade head` и `downgrade`/`upgrade` проходят без ошибок
- [x] `ruff`, `mypy` и `pytest` работают внутри контейнера

---

## Task 3: Реализовать `PoliteHttpClient` (`robots.txt`, rate limit, ретраи) и офлайн-тесты

**Description:** Реализовать асинхронный HTTP-клиент `PoliteHttpClient` поверх `httpx.AsyncClient` с кэшируемой проверкой `robots.txt` (через `urllib.robotparser`), ограничением конкурентности `1` на домен, минимальной задержкой ≥ 1.5 сек (+ jitter), понятным `User-Agent`, строгой проверкой TLS и ретраями на временные ошибки (429/5xx/таймаут).

**Acceptance criteria:**
- [x] Запрос к URL, запрещённому в `robots.txt`, не выполняется и выбрасывает типизированное исключение `RobotsDisallowedError`.
- [x] Последовательные запросы к одному домену соблюдают минимальную задержку `min_delay_sec` (проверено в юнит-тесте с подменой таймера/sleep).
- [x] Временные ответы `429`/`503` ретраятся с backoff ограниченное число раз, после чего поднимают структурированную ошибку.

**Verification:**
- [x] Tests pass: `make test-ingestion PYTEST_ARGS="tests/ingestion/test_http_client.py"`
- [x] Build succeeds: `make lint && make typecheck`
- [x] Manual check: убедиться, что `verify=True` по умолчанию и отключение TLS не используется

**Dependencies:** Task 2

**Files likely touched:**
- `backend/app/ingestion/http_client.py`
- `backend/tests/ingestion/test_http_client.py`

**Estimated scope:** Small (2 files)

---

## Task 4: Реализовать HTML и PDF экстракторы прайс-листов с тестами на фикстурах

**Description:** Создать переиспользуемые экстракторы для извлечения табличных и списочных прайс-листов из HTML (`beautifulsoup4` + `lxml`) и PDF (`pdfplumber`), включая нормализацию строковых цен в `Decimal` и разбор валют (`KZT`, `₸`, `тг`, `USD`, `$`) и сроков выполнения.

**Acceptance criteria:**
- [x] HTML-экстрактор извлекает строки `(service_name_raw, price_raw, currency_raw, duration_days_raw)` из типовых HTML-таблиц и блоков прайса, пропуская заголовки/пустые цены с отчётом об ошибках строк.
- [x] PDF-экстрактор извлекает прайс-таблицы из многостраничного PDF через `pdfplumber` без падения на пустых/битых строках.
- [x] Оба экстрактора покрыты офлайн-тестами на фикстурах (валидные строки, пробелы/разделители тысяч, невалидные цены, USD/KZT).

**Verification:**
- [x] Tests pass: `make test-ingestion PYTEST_ARGS="tests/ingestion/test_extractors_html_pdf.py"`
- [x] Build succeeds: `make lint && make typecheck`
- [x] Manual check: проверить, что суммы возвращаются строго как `Decimal`

**Dependencies:** Task 2

**Files likely touched:**
- `backend/app/ingestion/extractors/__init__.py`
- `backend/app/ingestion/extractors/html.py`
- `backend/app/ingestion/extractors/pdf.py`
- `backend/tests/ingestion/test_extractors_html_pdf.py`

**Estimated scope:** Medium (4 files)

---

## Task 5: Реализовать DOCX и Excel экстракторы прайс-листов с тестами на фикстурах

**Description:** Создать переиспользуемые экстракторы для извлечения прайс-листов из документов Word (`.docx` через `python-docx`) и электронных таблиц Excel (`.xlsx` через `openpyxl`), с тестами на программно генерируемых/сохранённых фикстурах.

**Acceptance criteria:**
- [x] DOCX-экстрактор извлекает прайс-строки из таблиц Word-документа, корректно определяя колонки названия, цены и срока.
- [x] Excel-экстрактор извлекает прайс-строки со всех/выбранных листов `.xlsx`, обрабатывая числовые и строковые ячейки цен.
- [x] Некорректные/пустые строки возвращаются как ошибки разбора, не прерывая обработку остальных строк документа.

**Verification:**
- [x] Tests pass: `make test-ingestion PYTEST_ARGS="tests/ingestion/test_extractors_docx_excel.py"`
- [x] Build succeeds: `make lint && make typecheck`
- [x] Manual check: убедиться, что все 4 формата из ТЗ 3.1 (HTML, PDF, DOCX, Excel) доступны через общий пакет `app.ingestion.extractors`

**Dependencies:** Task 4

**Files likely touched:**
- `backend/app/ingestion/extractors/docx.py`
- `backend/app/ingestion/extractors/excel.py`
- `backend/tests/ingestion/test_extractors_docx_excel.py`

**Estimated scope:** Small (3 files)

---

## Checkpoint 2: After Tasks 3–5 (Politeness & Extractors)
- [x] Все офлайн-тесты `PoliteHttpClient` и 4 экстракторов (HTML, PDF, DOCX, Excel) зелёные
- [x] `ruff check` и `mypy` проходят без предупреждений и ошибок

---

## Task 6: Реализовать DTO, `BaseSourceAdapter`, `AdapterRegistry` и `IngestionRunner`

**Description:** Реализовать Pydantic-схемы (`RawServiceInput`, `RawServiceRecordDTO`, `ScrapeRunDTO`, `ScrapeErrorDTO`, `SourceInfo`), базовый интерфейс адаптера, реестр подключаемых источников и оркестратор `IngestionRunner` с вычислением `record_fingerprint`, идемпотентным UPSERT-ом и полной изоляцией ошибок между источниками.

**Acceptance criteria:**
- [ ] Повторный запуск `IngestionRunner` на неизменных данных даёт `records_inserted == 0` и `records_updated == N` (0 дубликатов в БД).
- [ ] Изменение цены для той же услуги создаёт новую запись в `raw_service_records`, сохраняя старую запись нетронутой.
- [ ] Исключение в одном адаптере (или `RobotsDisallowedError` / ошибка валидации строки) фиксируется в `scrape_errors`, помечает запуск этого источника как `failed`/`partial` и не прерывает остальные источники.

**Verification:**
- [ ] Tests pass: `make test-ingestion PYTEST_ARGS="tests/ingestion/test_runner.py"`
- [ ] Build succeeds: `make lint && make typecheck`
- [ ] Manual check: проверить, что добавление фикстурного тестового адаптера через `AdapterRegistry.register()` не требует правок в `runner.py`

**Dependencies:** Tasks 2, 3

**Files likely touched:**
- `backend/app/ingestion/schemas.py`
- `backend/app/ingestion/adapters/base.py`
- `backend/app/ingestion/adapters/registry.py`
- `backend/app/ingestion/runner.py`
- `backend/tests/ingestion/test_runner.py`

**Estimated scope:** Medium (5 files)

---

## Task 7: Реализовать публичный `IngestionService`, `scheduler.py`, `cli.py` и очистку ≥ 90 дней

**Description:** Реализовать публичный фасад `IngestionService` (контракт для `normalization` и `search-api`: `list_sources`, `trigger_run`, `list_runs`, `list_errors`, `iter_raw_records`, `purge_expired_raw_records`), периодический планировщик (`APScheduler`) и CLI (`run`, `list-sources`, `purge-expired`).

**Acceptance criteria:**
- [ ] `IngestionService.iter_raw_records(updated_since=...)` возвращает батчи `RawServiceRecordDTO` в детерминированном порядке для модуля `normalization`.
- [ ] `purge_expired_raw_records(retention_days)` отклоняет значение `< 90` (`ValueError`) и удаляет только записи с `last_seen_at < now - retention_days`.
- [ ] CLI поддерживает `python -m app.ingestion.cli list-sources`, `run --source all|<id> [--limit N]`, `purge-expired`, а `scheduler.py` конфигурирует ежедневный запуск (24h).

**Verification:**
- [ ] Tests pass: `make test-ingestion PYTEST_ARGS="tests/ingestion/test_service.py"`
- [ ] Build succeeds: `make lint && make typecheck`
- [ ] Manual check: запустить `python -m app.ingestion.cli list-sources` внутри контейнера

**Dependencies:** Task 6

**Files likely touched:**
- `backend/app/ingestion/service.py`
- `backend/app/ingestion/scheduler.py`
- `backend/app/ingestion/cli.py`
- `backend/tests/ingestion/test_service.py`

**Estimated scope:** Medium (4 files)

---

## Checkpoint 3: After Tasks 6–7 (Ingestion Core)
- [ ] Весь движок `ingestion` (дедупликация, изоляция ошибок, 90-дневный аудит, реестр адаптеров, `IngestionService`, CLI, планировщик) протестирован против реальной PostgreSQL 16
- [ ] Все тесты, `ruff` и `mypy` проходят чисто

---

## Task 8: Реализовать адаптер источника #1 — `kdlolymp.kz` (КДЛ Олимп)

**Description:** Изучить открытую структуру каталога/прайса и городов на `kdlolymp.kz` (в рамках разрешённого `robots.txt`), реализовать `KdlOlympAdapter`, зарегистрировать в `registry.py` и написать офлайн-тесты на сохранённых HTML/JSON-фикстурах.

**Acceptance criteria:**
- [ ] Адаптер извлекает реальные лабораторные услуги, цены в KZT, сроки выполнения (где указаны), город и контактные метаданные `kdlolymp.kz` без обхода `robots.txt`.
- [ ] Зарегистрирован в `registry.py` без изменений в `runner.py`, `models.py`, `service.py` или `cli.py`.
- [ ] Офлайн-контрактные тесты на сохранённых фикстурах проверяют валидность `RawServiceInput` и корректный парсинг цен/сроков.

**Verification:**
- [ ] Tests pass: `make test-ingestion PYTEST_ARGS="tests/ingestion/test_adapter_kdlolymp.py"`
- [ ] Build succeeds: `make lint && make typecheck`
- [ ] Manual check: пробный CLI-прогон `run --source kdlolymp --limit 30` сохраняет ≥ 30 валидных записей в `raw_service_records`

**Dependencies:** Tasks 4, 7

**Files likely touched:**
- `backend/app/ingestion/adapters/kdlolymp.py`
- `backend/app/ingestion/adapters/registry.py`
- `backend/tests/ingestion/fixtures/kdlolymp_*`
- `backend/tests/ingestion/test_adapter_kdlolymp.py`

**Estimated scope:** Medium (4 files)

---

## Task 9: Реализовать адаптер источника #2 — `invivo.kz` *(или альтернатива по согласованию)*

**Description:** Изучить открытую структуру прайса/каталога и городов на `invivo.kz` (или другом утверждённом источнике вместо заблокированного `invitro.kz`), реализовать адаптер, зарегистрировать в `registry.py` и покрыть офлайн-тестами на фикстурах.

**Acceptance criteria:**
- [ ] Адаптер извлекает реальные услуги, цены в KZT, сроки выполнения и городские метаданные с соблюдением `robots.txt` и задержек.
- [ ] Зарегистрирован в `registry.py` без изменений в ядре `ingestion`.
- [ ] Офлайн-контрактные тесты на сохранённых фикстурах проходят полностью.

**Verification:**
- [ ] Tests pass: `make test-ingestion PYTEST_ARGS="tests/ingestion/test_adapter_invivo.py"`
- [ ] Build succeeds: `make lint && make typecheck`
- [ ] Manual check: пробный CLI-прогон `run --source invivo --limit 30` сохраняет ≥ 30 валидных записей

**Dependencies:** Tasks 4, 7

**Files likely touched:**
- `backend/app/ingestion/adapters/invivo.py`
- `backend/app/ingestion/adapters/registry.py`
- `backend/tests/ingestion/fixtures/invivo_*`
- `backend/tests/ingestion/test_adapter_invivo.py`

**Estimated scope:** Medium (4 files)

---

## Task 10: Реализовать адаптер источника #3 — `doq.kz` *(или альтернатива по согласованию)*

**Description:** Изучить открытую структуру клиник/приёмов врачей/диагностики на `doq.kz` (агрегатор из ТЗ с открытым `robots.txt`, покрывает приёмы врачей, диагностику, рейтинги клиник, адреса, онлайн-запись и города РК), реализовать адаптер, зарегистрировать в `registry.py` и покрыть офлайн-тестами на фикстурах.

**Acceptance criteria:**
- [ ] Адаптер извлекает услуги клиник/врачей, цены в KZT, город, адрес, рейтинг и флаг онлайн-записи (где присутствуют на странице) с соблюдением `robots.txt`.
- [ ] Зарегистрирован в `registry.py` без изменений в ядре `ingestion`.
- [ ] Офлайн-контрактные тесты на сохранённых фикстурах проходят полностью.

**Verification:**
- [ ] Tests pass: `make test-ingestion PYTEST_ARGS="tests/ingestion/test_adapter_doq.py"`
- [ ] Build succeeds: `make lint && make typecheck`
- [ ] Manual check: пробный CLI-прогон `run --source doq --limit 30` сохраняет ≥ 30 валидных записей

**Dependencies:** Tasks 4, 7

**Files likely touched:**
- `backend/app/ingestion/adapters/doq.py`
- `backend/app/ingestion/adapters/registry.py`
- `backend/tests/ingestion/fixtures/doq_*`
- `backend/tests/ingestion/test_adapter_doq.py`

**Estimated scope:** Medium (4 files)

---

## Task 11: Провести живой E2E-прогон и финальную проверку модуля `ingestion`

**Description:** Запустить полный сбор по всем 3+ зарегистрированным источникам в PostgreSQL, проверить повторный идемпотентный запуск (0 дублей), проверить объём реальных данных (≥ 100 услуг, ≥ 3 источника, ≥ 3 города РК), покрытие тестами ≥ 80% и зафиксировать команды запуска в `README.md`.

**Acceptance criteria:**
- [ ] В `raw_service_records` собрано ≥ 100 реальных услуг минимум из 3 открытых источников.
- [ ] Повторный запуск на тех же параметрах даёт 0 дублей (`records_inserted == 0`).
- [ ] Покрытие `pytest --cov=app.ingestion` ≥ 80%, `ruff check` и `mypy` проходят без ошибок.

**Verification:**
- [ ] Tests pass: `make test-ingestion`
- [ ] Build succeeds: `make lint && make typecheck`
- [ ] Manual check: SQL-запрос по `raw_service_records` (`GROUP BY source_id, city_raw`) подтверждает ≥ 3 источников и ≥ 100 записей; повторный запуск даёт `records_inserted = 0`

**Dependencies:** Tasks 8, 9, 10

**Files likely touched:**
- `README.md`
- `backend/tests/ingestion/test_integration_e2e.py`

**Estimated scope:** Small (2 files)

---

## Checkpoint 4: After Task 11 (Module Complete)
- [ ] Все 7 критериев успеха из [SPEC-ingestion.md](../SPEC-ingestion.md) выполнены и подтверждены
- [ ] Готово к ревью пользователя и переходу к `SPEC-normalization.md`

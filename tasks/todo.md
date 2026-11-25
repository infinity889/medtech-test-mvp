# Task List: Normalization (`normalization`) — V1

Source plan: [tasks/plan.md](./plan.md) | Source spec: [SPEC-normalization.md](../SPEC-normalization.md)

---

## Task 1: Добавить `rapidfuzz`, настройки нормализации в `Settings`, цели в `Makefile` и пересобрать контейнер

**Description:** Добавить зависимость `rapidfuzz>=3.10,<4.0` в `backend/pyproject.toml`, расширить `Settings` параметрами нормализации (`usd_to_kzt_rate=Decimal("495.00")`, `fuzzy_match_threshold=86.0`, `fuzzy_suggestion_threshold=60.0`, `offer_max_age_days=30`), добавить команды `seed-catalog`, `normalize`, `test-normalization` в `Makefile` и пересобрать контейнер `medprice-backend:dev`.

**Acceptance criteria:**
- [x] `rapidfuzz` импортируется внутри контейнера `medprice-backend:dev`.
- [x] `Settings` считывает и валидирует `USD_TO_KZT_RATE` (> 0, `Decimal`), `FUZZY_MATCH_THRESHOLD` (0..100), `FUZZY_SUGGESTION_THRESHOLD` (0..100, ≤ match threshold), `OFFER_MAX_AGE_DAYS` (≥ 1).
- [x] `Makefile` содержит цели `seed-catalog`, `normalize`, `test-normalization`, `test-all`.

**Verification:**
- [x] Build succeeds: `make backend-build`
- [x] Tests pass: `make test-ingestion && make lint && make typecheck`
- [x] Manual check: `podman run --rm medprice-backend:dev python -c "import rapidfuzz; print(rapidfuzz.__version__)"`

**Dependencies:** None

**Files likely touched:**
- `backend/pyproject.toml`
- `backend/app/core/config.py`
- `Makefile`
- `backend/app/normalization/__init__.py`

**Estimated scope:** Small (4 files)

---

## Task 2: Реализовать ORM-модели слоя `normalization` и обратимую миграцию Alembic `0002`

**Description:** Создать SQLAlchemy 2.0 ORM-модели (`ServiceCatalog`, `Clinic`, `ServiceOffer`, `PriceHistory`, `UnmatchedService`) и enum-типы (`ServiceCategory`, `CurrencyCode`, `MatchMethod`, `UnmatchedStatus`), подключить модели в `alembic/env.py` и написать обратимую миграцию `0002_normalization_layer.py` со всеми индексами, FK и `UNIQUE (clinic_id, service_id)`.

**Acceptance criteria:**
- [ ] Миграция `0002_normalization_layer.py` создаёт 5 таблиц (`service_catalog`, `clinics`, `service_offers`, `price_history`, `unmatched_services`) со всеми полями, FK, индексами и уникальными ограничениями из `SPEC-normalization.md`.
- [ ] Миграция обратима (`alembic upgrade head` → `alembic downgrade 0001_ingestion_raw_layer` → `alembic upgrade head`) без потери таблиц `ingestion`.
- [ ] Интеграционный тест проверяет создание таблиц, `UNIQUE (clinic_id, service_id)` и `UNIQUE (raw_record_id)` в `unmatched_services`.

**Verification:**
- [ ] Tests pass: `make test-normalization PYTEST_ARGS="tests/normalization/test_models.py"`
- [ ] Build succeeds: `make migrate && make lint && make typecheck`
- [ ] Manual check: проверить обратимость `0002 → 0001 → 0002` на `medprice_test` и `\dt` в `medprice`

**Dependencies:** Task 1

**Files likely touched:**
- `backend/app/normalization/models.py`
- `backend/alembic/env.py`
- `backend/alembic/versions/0002_normalization_layer.py`
- `backend/tests/normalization/test_models.py`

**Estimated scope:** Medium (4 files)

---

## Checkpoint 1: After Tasks 1–2 (Foundation)
- [ ] Контейнер `medprice-backend:dev` пересобран с `rapidfuzz`
- [ ] Миграция `0002_normalization_layer` применена и проверена на обратимость
- [ ] Существующие 48 тестов `ingestion` и новые тесты моделей `normalization` проходят чисто

---

## Task 3: Реализовать нормализацию текста и конвертацию валют `KZT`/`USD → KZT` (`text_utils.py`)

**Description:** Реализовать чистые утилиты предобработки названий услуг (`ё→е`, снятие кавычек/звёздочек/скобок-мусора, сжатие пробелов, снятие типовых префиксов вроде «Кровь.», «Моча.», «Приём врача»), маппинг строкового `category_hint` в `ServiceCategory`, генерацию стабильного `clinic_key` (SHA-256) и конвертацию валют `convert_to_kzt(price, currency, usd_rate)` через `Decimal`.

**Acceptance criteria:**
- [ ] `normalize_service_text` детерминированно приводит «Общий анализ крови (ОАК)*», «Кровь. Общий анализ» и «Ёмкость...» к чистому нормализованному виду.
- [ ] `convert_to_kzt` возвращает `Decimal` с точностью `0.01` (`ROUND_HALF_UP`) для `KZT` и `USD`, и отклоняет неподдерживаемые валюты / неположительные цены.
- [ ] `map_category_hint` корректно маппит русские/английские подсказки в `ServiceCategory` (`lab`, `doctor`, `diagnostics`, `procedure`) или `None`.

**Verification:**
- [ ] Tests pass: `make test-normalization PYTEST_ARGS="tests/normalization/test_text_and_currency.py"`
- [ ] Build succeeds: `make lint && make typecheck`
- [ ] Manual check: убедиться, что везде используется `Decimal`, без `float` для денег

**Dependencies:** Task 2

**Files likely touched:**
- `backend/app/normalization/text_utils.py`
- `backend/tests/normalization/test_text_and_currency.py`

**Estimated scope:** Small (2 files)

---

## Task 4: Сформировать курируемый справочник `catalog_seed.json` (65–80 услуг на базе реальных данных РК)

**Description:** Проанализировать реальные названия услуг из `raw_service_records` (`kdlolymp`, `invivo`, `doq`) и составить версионируемый JSON-справочник `backend/app/normalization/data/catalog_seed.json` на 65–80 наиболее востребованных позиций по всем 4 категориям ТЗ (`lab`, `doctor`, `diagnostics`, `procedure`) с богатыми синонимами и аббревиатурами (включая `ОАК`/`CBC`, `ОАМ`, `ТТГ`, `СОЭ`, `Ферритин`, `Витамин D`, `Терапевт`, `Кардиолог`, `УЗИ ОБП`, `ЭКГ`, `МРТ` и др.).

**Acceptance criteria:**
- [ ] `catalog_seed.json` содержит ≥ 65 (строго ≥ 50 по ТЗ) уникальных позиций с валидными `code`, `canonical_name`, `category`, `synonyms`.
- [ ] Представлены все 4 категории (`lab`, `doctor`, `diagnostics`, `procedure`), нет дубликатов `code`, `canonical_name` или пересекающихся точных синонимов между разными услугами.
- [ ] Кейс ТЗ (`«ОАК»`, `«Общий анализ крови»`, `«CBC»`, `«Клинический анализ крови»`) присутствует в синонимах единой услуги `Общий анализ крови (ОАК)`.

**Verification:**
- [ ] Tests pass: `make test-normalization PYTEST_ARGS="tests/normalization/test_catalog_seed.py"`
- [ ] Build succeeds: `make lint && make typecheck`
- [ ] Manual check: проверить распределение позиций по 4 категориям в выводе теста

**Dependencies:** Task 2

**Files likely touched:**
- `backend/app/normalization/data/catalog_seed.json`
- `backend/app/normalization/catalog_loader.py`
- `backend/tests/normalization/test_catalog_seed.py`

**Estimated scope:** Small (3 files)

---

## Task 5: Реализовать детерминированный `ServiceMatcher` (`exact` → `synonym` → `RapidFuzz`)

**Description:** Реализовать матчер `ServiceMatcher`, индексирующий канонические названия и синонимы справочника в памяти, и выполняющий 3-ступенчатый поиск: 1) `exact` по нормализованному `canonical_name`, 2) `synonym` по нормализованным синонимам, 3) категорийно-изолированный `RapidFuzz` (`fuzz.token_sort_ratio` / `fuzz.ratio` с защитой от коротких ложных совпадений типа `АЛТ`/`АСТ`) с порогом авто-матча `86.0` и подсказкой кандидата `>= 60.0`.

**Acceptance criteria:**
- [ ] «ОАК», «Общий анализ крови», «CBC», «Клинический анализ крови» и реальные названия из `kdlolymp`/`invivo` сводятся к одной услуге `Общий анализ крови (ОАК)`.
- [ ] Услуги с известным `category_hint` никогда не матчатся через `RapidFuzz` с другой категорией (напр. `lab` не склеивается с `doctor`).
- [ ] Похожие, но разные короткие анализы (`АЛТ` vs `АСТ`, `Т3` vs `Т4`, `Витамин D` vs `Витамин B12`) не склеиваются ошибочно.
- [ ] Нераспознанная услуга возвращает `is_matched == False` и заполняет `suggested_service_id` / `suggested_score`, если лучший кандидат `>= 60.0`.

**Verification:**
- [ ] Tests pass: `make test-normalization PYTEST_ARGS="tests/normalization/test_matcher.py"`
- [ ] Build succeeds: `make lint && make typecheck`
- [ ] Manual check: проверить точность на наборе из ≥ 15 реальных названий из `kdlolymp`, `invivo`, `doq`

**Dependencies:** Tasks 3, 4

**Files likely touched:**
- `backend/app/normalization/matcher.py`
- `backend/tests/normalization/test_matcher.py`

**Estimated scope:** Small (2 files)

---

## Checkpoint 2: After Tasks 3–5 (Dictionary & Matching Engine)
- [ ] `text_utils`, `catalog_seed.json` (≥ 65 позиций) и `ServiceMatcher` полностью протестированы
- [ ] `ruff check` и `mypy --strict` проходят без ошибок

---

## Task 6: Реализовать DTO (`schemas.py`) и `NormalizationPipeline`

**Description:** Создать Pydantic v2 DTO (`ServiceCatalogDTO`, `ClinicDTO`, `ServiceOfferDTO`, `UnmatchedServiceDTO`, `PriceHistoryPointDTO`, `SeedSummary`, `NormalizationSummary`) и оркестратор `NormalizationPipeline`, читающий батчи из `IngestionService.iter_raw_records(...)`, дедуплицирующий `clinics`, выполняющий upsert `service_offers` (с выбором свежайшей/минимальной цены при коллизии `(clinic_id, service_id)`), фиксирующий изменения в `price_history` и отправляющий нераспознанные строки в `unmatched_services`.

**Acceptance criteria:**
- [ ] Прогон пайплайна на raw-данных создаёт `clinics`, `service_offers`, начальные точки `price_history` и записи `unmatched_services`.
- [ ] Повторный прогон на тех же raw-данных идемпотентен: 0 дублей в `clinics`, `service_offers`, `price_history` и `unmatched_services`.
- [ ] Появление новой цены в raw-слое обновляет `service_offers.price_kzt` и добавляет новую запись в `price_history`.
- [ ] Предложение с `parsed_at` старше 30 дней сохраняется с `is_active = False`.

**Verification:**
- [ ] Tests pass: `make test-normalization PYTEST_ARGS="tests/normalization/test_pipeline.py"`
- [ ] Build succeeds: `make lint && make typecheck`
- [ ] Manual check: проверить, что `NormalizationPipeline` не делает ни одной записи в таблицы `ingestion`

**Dependencies:** Task 5

**Files likely touched:**
- `backend/app/normalization/schemas.py`
- `backend/app/normalization/pipeline.py`
- `backend/tests/normalization/test_pipeline.py`

**Estimated scope:** Medium (3 files)

---

## Task 7: Реализовать публичный `NormalizationService` и CLI (`cli.py`)

**Description:** Реализовать фасад `NormalizationService` (полный контракт для `search-api`: `seed_catalog`, `run_normalization`, `list_catalog`, `list_unmatched`, `resolve_unmatched` с добавлением синонима и авто-резолвом совпадающих `pending`-записей, `ignore_unmatched`, `get_price_history`, `refresh_stale_offers`, `close`) и CLI (`seed-catalog`, `run`, `refresh-stale`, `stats`).

**Acceptance criteria:**
- [ ] `seed_catalog()` идемпотентно загружает `catalog_seed.json` (повторный вызов обновляет без дублей).
- [ ] `resolve_unmatched(id, service_id, add_as_synonym=True)` переводит запись в `mapped`, создаёт `service_offers` + `price_history`, добавляет `service_name_raw` в синонимы и перематчивает совпадающие `pending`-записи.
- [ ] `ignore_unmatched(id)` переводит запись в `ignored`, `refresh_stale_offers(30)` деактивирует предложения старше 30 дней, `get_price_history(...)` возвращает хронологический ряд цен.
- [ ] CLI `python -m app.normalization.cli seed-catalog | run | refresh-stale | stats` работает внутри контейнера и корректно освобождает `Engine`.

**Verification:**
- [ ] Tests pass: `make test-normalization PYTEST_ARGS="tests/normalization/test_service.py"`
- [ ] Build succeeds: `make lint && make typecheck`
- [ ] Manual check: проверить `python -m app.normalization.cli stats`

**Dependencies:** Task 6

**Files likely touched:**
- `backend/app/normalization/service.py`
- `backend/app/normalization/cli.py`
- `backend/tests/normalization/test_service.py`

**Estimated scope:** Medium (3 files)

---

## Checkpoint 3: After Tasks 6–7 (Pipeline & Public Contract)
- [ ] Весь движок `normalization` и контракт `NormalizationService` протестированы против реальной PostgreSQL 16
- [ ] `make test-normalization`, `make test-ingestion`, `make lint`, `make typecheck` проходят чисто

---

## Task 8: Живой прогон на 2 625 реальных записях РК, верификация пересечений и обновление `README.md`

**Description:** Применить миграцию `0002` на `medprice`, выполнить `make seed-catalog && make normalize` на реальных 2 625 записях из `kdlolymp`, `invivo` и `doq`, проверить качество матчинга и реальные межклинические сравнения цен (одна услуга в нескольких клиниках/лабораториях), проверить идемпотентность повторного `make normalize`, подтвердить покрытие ≥ 85% и обновить `README.md`.

**Acceptance criteria:**
- [ ] В `service_catalog` загружено ≥ 65 позиций по 4 категориям.
- [ ] В `service_offers` есть реальные нормализованные предложения по всем 3 источникам (`kdlolymp`, `invivo`, `doq`) и реальные пересечения цен между клиниками по ключевым услугам (напр. ОАК, ОАМ, ТТГ, Ферритин, Терапевт, Кардиолог, УЗИ).
- [ ] Повторный `make normalize` даёт 0 новых дублей в `clinics`, `service_offers`, `price_history`, `unmatched_services`.
- [ ] Покрытие `make test-normalization` ≥ 85%, все тесты (`ingestion` + `normalization`), `ruff` и `mypy` зелёные.

**Verification:**
- [ ] Tests pass: `make test-all`
- [ ] Build succeeds: `make lint && make typecheck`
- [ ] Manual check: SQL-отчёт по `service_offers`, `clinics`, `price_history`, `unmatched_services` и пример сравнения цен по «Общий анализ крови (ОАК)» и «Приём терапевта»

**Dependencies:** Task 7

**Files likely touched:**
- `README.md`
- `backend/app/normalization/data/catalog_seed.json` *(при необходимости точечное дообогащение синонимов по результатам живого прогона)*

**Estimated scope:** Small (2 files)

---

## Checkpoint 4: After Task 8 (Module Complete)
- [ ] Все 8 критериев успеха из [SPEC-normalization.md](../SPEC-normalization.md) выполнены и подтверждены
- [ ] Готово к ревью пользователя и переходу к `SPEC-search-api.md`

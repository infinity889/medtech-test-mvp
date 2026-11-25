# Task List: Search & Comparison API (`search-api`) — V1

Source plan: [tasks/plan.md](./plan.md) | Source spec: [SPEC-search-api.md](../SPEC-search-api.md)

---

## Task 1: Добавить `fastapi` и `uvicorn[standard]`, настройки API в `Settings`, цели в `Makefile` и пересобрать контейнер

**Description:** Добавить `fastapi>=0.115.0,<1.0` и `uvicorn[standard]>=0.32.0,<1.0` в `backend/pyproject.toml`, расширить `Settings` (`admin_api_token`, `cors_origins`, `api_host`, `api_port`), добавить цели `api-up`, `api-down`, `api-dev`, `test-api` в `Makefile`, создать `backend/app/api/__init__.py` и пересобрать контейнер `medprice-backend:dev`.

**Acceptance criteria:**
- [x] `fastapi` и `uvicorn` импортируются внутри контейнера `medprice-backend:dev`.
- [x] `Settings` предоставляет `admin_api_token` (дефолт `dev-admin-token`), `cors_origins_list` и `api_port` (дефолт `8000`).
- [x] Все существующие 91 тест (`ingestion` + `normalization`), `ruff` и `mypy` зелёные.

**Verification:**
- [x] Build succeeds: `make backend-build`
- [x] Tests pass: `make test-all && make lint && make typecheck`
- [x] Manual check: `podman run --rm medprice-backend:dev python -c "import fastapi, uvicorn; print(fastapi.__version__)"`

**Dependencies:** None

**Files likely touched:**
- `backend/pyproject.toml`
- `backend/app/core/config.py`
- `Makefile`
- `backend/app/api/__init__.py`

**Estimated scope:** Small (4 files)

---

## Task 2: Реализовать каркас FastAPI (`schemas.py`, `errors.py`, `deps.py`, `main.py`, `routes/health.py`)

**Description:** Создать Pydantic v2 схемы ответов/запросов (`APIError`, `PaginationMeta`, `HealthResponse`, `FiltersMetaResponse`, `OfferSearch*`, `Clinic*`, `Compare*`, `PriceHistory*`, `Admin*`), единые обработчики ошибок (`400`/`401`/`404`/`409`/`422`/`500`), зависимости DI (`get_session_factory`, `get_ingestion_service`, `get_normalization_service`, `require_admin_token` через `hmac.compare_digest`), CORS-настройки, фабрику `create_app()` в `app/main.py` и маршрут `/api/v1/health`.

**Acceptance criteria:**
- [x] `GET /api/v1/health` возвращает `200 {"status": "ok", "database": "ok"}`.
- [x] Неизвестный маршрут и ошибки валидации возвращают единый формат `{"error": {"code", "message", "details"}}`.
- [x] CORS preflight для `http://localhost:5173` возвращает корректный `Access-Control-Allow-Origin`.

**Verification:**
- [x] Tests pass: `make test-api API_PYTEST_ARGS="tests/api/test_health_and_meta.py"`
- [x] Build succeeds: `make lint && make typecheck`
- [x] Manual check: проверить `/openapi.json` через `TestClient`/`AsyncClient`

**Dependencies:** Task 1

**Files likely touched:**
- `backend/app/api/errors.py`
- `backend/app/api/schemas.py`
- `backend/app/api/deps.py`
- `backend/app/api/routes/health.py`
- `backend/app/main.py`

**Estimated scope:** Medium (5 files)

---

## Checkpoint 1: After Tasks 1–2 (Foundation)
- [x] Контейнер `medprice-backend:dev` пересобран с `fastapi` + `uvicorn`
- [x] `/api/v1/health`, CORS и единая обработка ошибок работают и протестированы

---

## Task 3: Реализовать `SearchQueryService` и маршруты `/meta/filters`, `/services/autocomplete`, `/offers`

**Description:** Реализовать сервисный слой чтения `SearchQueryService` (агрегаты фильтров, ранжированное автодополнение по справочнику и синонимам, поиск и сравнение предложений с фильтрами города/категории/цены/рейтинга/онлайн-записи, расчётом расстояния Haversine, сортировкой `price_asc|price_desc|distance_asc|updated_desc|rating_desc`, ссылками 2GIS/Google Maps и жёстким правилом свежести ≤ 30 дней) и подключить маршруты.

**Acceptance criteria:**
- [x] `GET /api/v1/meta/filters` возвращает города, категории с русскими названиями, мин/макс цены и дату последнего обновления.
- [x] `GET /api/v1/services/autocomplete?q=ОАК` и `?q=CBC` возвращают «Общий анализ крови (ОАК)» с `offers_count` и `min_price_kzt`.
- [x] `GET /api/v1/offers` поддерживает все фильтры, сортировки (включая `distance_asc` по `lat`/`lng`), пагинацию, агрегаты `summary` и **никогда** не возвращает предложения старше 30 дней.
- [x] Некорректные диапазоны (`min_price > max_price` или `lat` без `lng`) возвращают `422 VALIDATION_ERROR`.

**Verification:**
- [x] Tests pass: `make test-api API_PYTEST_ARGS="tests/api/test_search_and_offers.py"`
- [x] Build succeeds: `make lint && make typecheck`
- [x] Manual check: убедиться, что `distance_km` корректен по формуле Haversine

**Dependencies:** Task 2

**Files likely touched:**
- `backend/app/api/query_service.py`
- `backend/app/api/routes/health.py`
- `backend/app/api/routes/services.py`
- `backend/app/api/routes/offers.py`
- `backend/tests/api/test_search_and_offers.py`

**Estimated scope:** Medium (5 files)

---

## Task 4: Реализовать маршруты `/clinics`, `/clinics/{clinic_id}`, `/compare` и `/services/{service_id}/price-history`

**Description:** Реализовать список клиник (с фильтром `has_geo=true` для карты Leaflet), карточку клиники со всеми активными услугами ≤ 30 дней и ссылками маршрутов 2GIS/Google Maps, матрицу табличного сравнения 2–5 клиник (`GET /api/v1/compare` с определением `cheapest_clinic_id`) и историю изменения цен (`GET /api/v1/services/{service_id}/price-history`).

**Acceptance criteria:**
- [x] `GET /api/v1/clinics?has_geo=true` возвращает только клиники с непустыми `latitude` и `longitude`.
- [x] `GET /api/v1/clinics/{clinic_id}` возвращает контакты, график работы, ссылки маршрутов и только актуальные (≤ 30 дней) услуги; несуществующий UUID → `404 NOT_FOUND`.
- [x] `GET /api/v1/compare` сравнивает 2–5 клиник, корректно отмечает `cheapest_clinic_id` в каждой строке и возвращает `422` при `< 2` или `> 5` клиниках.
- [x] `GET /api/v1/services/{service_id}/price-history` возвращает хронологические точки цен с `clinic_name` и `city`.

**Verification:**
- [x] Tests pass: `make test-api API_PYTEST_ARGS="tests/api/test_clinics_and_compare.py"`
- [x] Build succeeds: `make lint && make typecheck`
- [x] Manual check: проверить генерацию ссылок 2GIS и Google Maps как по GPS, так и по адресу-фоллбэку

**Dependencies:** Task 3

**Files likely touched:**
- `backend/app/api/query_service.py`
- `backend/app/api/routes/clinics.py`
- `backend/app/api/routes/services.py`
- `backend/app/main.py`
- `backend/tests/api/test_clinics_and_compare.py`

**Estimated scope:** Medium (5 files)

---

## Checkpoint 2: After Tasks 3–4 (Public Patient API)
- [x] Все публичные пациентские маршруты (`/health`, `/meta/filters`, `/services/autocomplete`, `/offers`, `/clinics`, `/clinics/{id}`, `/compare`, `/price-history`) работают и протестированы
- [x] `ruff` и `mypy --strict` чистые

---

## Task 5: Реализовать админ-маршруты `/api/v1/admin/*` с защитой `X-Admin-Token` и блокировкой `409`

**Description:** Реализовать защищённые `X-Admin-Token` админ-эндпоинты (`GET /admin/sources`, `scrape-runs`, `scrape-errors`, `stats`, `unmatched`; `POST /admin/scrape-runs` с `asyncio.Lock` и возвратом `409 SCRAPE_IN_PROGRESS`; `POST /admin/unmatched/{id}/resolve` и `/ignore`), полностью делегируя операции фасадам `IngestionService` и `NormalizationService`.

**Acceptance criteria:**
- [x] Запрос без `X-Admin-Token` или с неверным токеном возвращает `401 UNAUTHORIZED` в формате `APIError`.
- [x] `GET /api/v1/admin/unmatched` возвращает пагинированный список с обогащённым полем `suggested_service_name`.
- [x] `POST /api/v1/admin/unmatched/{id}/resolve` создаёт актуальное предложение, которое сразу находится в `GET /api/v1/offers`; `/ignore` переводит запись в `ignored`.
- [x] `POST /api/v1/admin/scrape-runs` возвращает `{runs, normalization_summary}`, а параллельный вызов при активном запуске возвращает `409 SCRAPE_IN_PROGRESS`.

**Verification:**
- [x] Tests pass: `make test-api API_PYTEST_ARGS="tests/api/test_admin_endpoints.py"`
- [x] Build succeeds: `make lint && make typecheck`
- [x] Manual check: убедиться, что `admin.py` не обращается к таблицам `raw_service_records` напрямую

**Dependencies:** Task 4

**Files likely touched:**
- `backend/app/api/routes/admin.py`
- `backend/app/main.py`
- `backend/tests/api/test_admin_endpoints.py`

**Estimated scope:** Small (3 files)

---

## Task 6: Живой запуск API (`make api-up`) на реальной БД `medprice`, замер latency и обновление `README.md`

**Description:** Поднять FastAPI-контейнер `medprice-api` на порту `8000` поверх реальной БД `medprice` (64 клиники, 499 предложений, 88 услуг), проверить реальные запросы `/health`, `/meta/filters`, `/services/autocomplete?q=ОАК`, `/offers?q=ОАК`, `/clinics`, `/compare`, `/docs`, замерить время ответа (`< 500 мс`), подтвердить покрытие ≥ 85% по `app/api` и обновить `README.md`.

**Acceptance criteria:**
- [x] `make api-up` поднимает API в сети `medprice-net` на `http://127.0.0.1:8000`.
- [x] Живые запросы к `/api/v1/services/autocomplete?q=ОАК` и `/api/v1/offers?q=ОАК` возвращают реальные предложения `kdlolymp` + `invivo` за `< 500 мс`.
- [x] `make test-all` (покрытие `app/api` ≥ 85%), `make lint`, `make typecheck` проходят без ошибок.

**Verification:**
- [x] Tests pass: `make test-all`
- [x] Build succeeds: `make api-up && make lint && make typecheck`
- [x] Manual check: `curl -sS -w "\ntime_total=%{time_total}s\n"` по `/health`, `/meta/filters`, `/services/autocomplete?q=ОАК`, `/offers?q=ОАК`

**Dependencies:** Task 5

**Files likely touched:**
- `README.md`

**Estimated scope:** Small (1 file)

---

## Checkpoint 3: After Task 6 (Module Complete)
- [x] Все 6 критериев успеха из [SPEC-search-api.md](../SPEC-search-api.md) выполнены и подтверждены
- [x] Готово к ревью пользователя и переходу к `SPEC-web-ui.md`

# Implementation Plan: Search & Comparison API (`search-api`) — V1

Source spec: [SPEC-search-api.md](../SPEC-search-api.md)

## Overview

Реализуем модуль `search-api` — быстрый, строго типизированный FastAPI REST API (`/api/v1`) для пациентского поиска и сравнения цен на медицинские услуги в Казахстане (автодополнение, фильтры, сортировка по цене/расстоянию/свежести/рейтингу, правило актуальности ≤ 30 дней, карточка клиники, карта клиник, матрица сравнения 2–5 клиник, история цен) и защищённые `X-Admin-Token` админ-эндпоинты для ручного запуска парсинга и разбора `unmatched queue`.

## Architecture Decisions

1. **Нулевые новые миграции БД**: `search-api` целиком работает поверх таблиц и сервисных контрактов модулей `normalization` и `ingestion`; все мутации (`trigger_run`, `run_normalization`, `resolve_unmatched`, `ignore_unmatched`) проходят исключительно через `IngestionService` и `NormalizationService`.
2. **Двойная гарантия свежести ≤ 30 дней**: публичные запросы `/offers`, `/clinics/{id}`, `/compare` и агрегаты `/meta/filters`, `/services/autocomplete` всегда фильтруют `is_active = true AND parsed_at >= now() - interval '30 days'`, не полагаясь только на периодический джоб `refresh_stale_offers`.
3. **Единый формат ошибок и пагинации**: кастомные обработчики исключений (`APIError`, `RequestValidationError`, `HTTPException`, `Exception`) гарантируют одинаковую JSON-структуру `{"error": {"code", "message", "details"}}` без утечки внутренних стектрейсов.
4. **Haversine + маршруты 2GIS / Google Maps**: расстояние до клиники вычисляется по координатам `(lat, lng)` (клиники без GPS помещаются в конец при `sort_by=distance_asc`); для каждой клиники генерируются прямые ссылки маршрута в 2GIS и Google Maps.
5. **Защита от параллельных запусков парсинга**: `POST /api/v1/admin/scrape-runs` защищён `asyncio.Lock` — конкурентный запрос получает `409 SCRAPE_IN_PROGRESS`.

## Dependency Graph

```text
Task 1 (fastapi + uvicorn in pyproject/container, API Settings, Makefile targets)
   │
   └── Task 2 (API schemas, unified APIError handlers, DI deps + X-Admin-Token, FastAPI app shell + /health)
          │
          ├── Task 3 (SearchQueryService: /meta/filters, /services/autocomplete, /offers with filters/Haversine/30d freshness)
          │
          ├── Task 4 (Clinics, Clinic Detail, 2GIS/Google Maps links, /compare 2–5 clinics matrix, /price-history)
          │
          └── Task 5 (Admin routes: sources, runs, errors, stats, unmatched resolve/ignore, POST scrape-runs + 409 lock)
                 │
                 └── Task 6 (Live API smoke test on medprice via podman, latency < 500ms check, README update)
```

## Task List

Подробные карточки задач находятся в [tasks/todo.md](./todo.md).

### Phase 1: Foundation & App Shell
- [x] Task 1: Добавить `fastapi` и `uvicorn[standard]`, настройки API в `Settings`, цели `api-up`/`api-down`/`test-api` в `Makefile` и пересобрать контейнер
- [ ] Task 2: Реализовать `schemas.py`, `errors.py`, `deps.py`, `main.py` и `routes/health.py` (`/health`, CORS, `APIError`, `X-Admin-Token`)

### Checkpoint 1: Foundation
- [ ] Контейнер пересобран с FastAPI/uvicorn, `/api/v1/health` и OpenAPI `/docs` работают, единый формат ошибок протестирован

### Phase 2: Patient Search, Clinics, Compare & Price History
- [ ] Task 3: Реализовать `query_service.py` и маршруты `/meta/filters`, `/services/autocomplete`, `/offers` (все фильтры, сортировки, Haversine, свежесть ≤ 30 дней)
- [ ] Task 4: Реализовать маршруты `/clinics`, `/clinics/{clinic_id}`, `/compare` (2–5 клиник) и `/services/{service_id}/price-history`

### Checkpoint 2: Public API
- [ ] Все пациентские эндпоинты протестированы против PostgreSQL (`medprice_test`), включая правило 30 дней, Haversine и сравнение 2–5 клиник

### Phase 3: Admin API & Live Verification
- [ ] Task 5: Реализовать защищённые `X-Admin-Token` маршруты `/api/v1/admin/*` (sources, runs, errors, stats, unmatched resolve/ignore, scrape-runs с `409` lock)
- [ ] Task 6: Провести живой прогон контейнера API (`make api-up`) на 499 реальных предложениях `medprice`, замерить задержки `< 500 мс`, проверить покрытие ≥ 85% и обновить `README.md`

### Checkpoint 3: Module Complete
- [ ] Все 6 критериев успеха из `SPEC-search-api.md` выполнены, `make test-all`, `make lint`, `make typecheck` чистые
- [ ] Ревью с человеком перед переходом к `SPEC-web-ui.md`

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Длительный синхронный парсинг в `POST /admin/scrape-runs` может заблокировать event loop или быть запущен дважды | Medium | `asyncio.Lock` с немедленным `409 SCRAPE_IN_PROGRESS` при повторном вызове + асинхронный `IngestionService.trigger_run` + опциональный `limit` |
| Утечка просроченных цен (> 30 дней), если забыть фильтр `parsed_at >= cutoff` в одном из запросов | High | Выносим единый helper `_freshness_cutoff()` в `SearchQueryService` и проверяем отдельным тестом на `/offers` и `/clinics/{id}` |
| Проблемы CORS при подключении React/Vite (`localhost:5173`) в модуле `web-ui` | Low | Явный `CORSMiddleware` из `Settings.cors_origins` + тест на preflight `OPTIONS` |

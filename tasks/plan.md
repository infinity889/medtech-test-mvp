# Implementation Plan: Ingestion (`ingestion`) — V1

Source spec: [SPEC-ingestion.md](../SPEC-ingestion.md)

## Overview

Реализуем модуль `ingestion` — отказоустойчивую подсистему сбора публичных прайс-листов клиник и лабораторий Казахстана с хранением в отдельном raw-слое PostgreSQL 16 (ретеншн ≥ 90 дней), идемпотентной дедупликацией, соблюдением `robots.txt` и задержек, переиспользуемыми экстракторами (HTML, PDF, DOCX, Excel), планировщиком/CLI и минимум 3 живыми адаптерами источников. Вся разработка и запуск выполняются в контейнере Python 3.12 через `podman`.

## Architecture Decisions

1. **Контейнерная инфраструктура без `podman compose`**: на хосте установлен `podman 6.1.3` без `podman-compose`, поэтому поднимаем общую сеть `medprice-net` и контейнеры `medprice-pg` (`postgres:16-alpine`) + `medprice-backend:dev` (`python:3.12-slim`) через воспроизводимый `Makefile`.
2. **Идемпотентная дедупликация с сохранением истории цен**: `raw_service_records` использует `UNIQUE (source_id, record_fingerprint)` (SHA-256 от канонических полей клиники, услуги и цены). Повторный прогон при неизменной цене делает `UPSERT` (обновляет `last_seen_at`, `parsed_at`, `last_run_id` без дублей), а изменение цены создаёт новую raw-запись, сохраняя прежнюю на ≥ 90 дней для аудита и истории цен.
3. **Изоляция адаптеров от БД**: адаптеры наследуют `BaseSourceAdapter` и отдают `AsyncIterator[RawServiceInput]`. Они никогда не работают с SQLAlchemy напрямую — валидацией, дедупликацией, транзакциями и записью `scrape_errors` управляет `IngestionRunner`.
4. **Строгое соблюдение `robots.txt` и TLS**: `PoliteHttpClient` кэширует `robots.txt` на домен, соблюдает `min_delay_sec >= 1.5` + jitter с семафором `concurrency=1` на домен и не отключает проверку SSL.
5. **Офлайн-тестируемость**: все юнит-, экстракторные и контрактные тесты адаптеров работают полностью офлайн (`respx` + сохранённые фикстуры HTML/JSON/PDF/DOCX/XLSX) и не зависят от доступности внешних сайтов в CI; живой прогон вынесен в финальную задачу верификации.

## Dependency Graph

```text
Task 1 (Podman Python 3.12 + PG 16 + scaffold)
   │
   └── Task 2 (Config, DB engine, Raw ORM models + Alembic migration)
          │
          ├── Task 3 (PoliteHttpClient: robots.txt, rate limit, retry)
          ├── Task 4 (Extractors: HTML + PDF)
          └── Task 5 (Extractors: DOCX + Excel)
                 │
                 └── Task 6 (DTOs, BaseSourceAdapter, Registry, IngestionRunner)
                        │
                        └── Task 7 (IngestionService contract, Scheduler, CLI, 90d purge)
                               │
                               ├── Task 8 (Live Adapter #1: kdlolymp.kz)
                               ├── Task 9 (Live Adapter #2: invivo.kz*)
                               └── Task 10 (Live Adapter #3: doq.kz*)
                                      │
                                      └── Task 11 (Live E2E smoke run & full verification)
```

*\*Состав адаптеров #2 и #3 зависит от подтверждения замены `invitro.kz` / `helix.kz` в Open Questions.*

## Task List

Подробные карточки задач (описание, критерии приёмки, команды проверки, файлы, размер) находятся в [tasks/todo.md](./todo.md).

### Phase 1: Foundation
- [x] Task 1: Подготовить `podman`-окружение (Python 3.12 + PostgreSQL 16), `pyproject.toml` и `Makefile`
- [x] Task 2: Реализовать конфиг, подключение БД, ORM-модели raw-слоя и начальную миграцию Alembic

### Checkpoint 1: Foundation
- [x] Контейнеры собираются и стартуют, `alembic upgrade head` проходит чисто, `pytest` запускается внутри контейнера

### Phase 2: Politeness & Document Extractors
- [x] Task 3: Реализовать `PoliteHttpClient` (`robots.txt`, per-domain rate limit, ретраи) и офлайн-тесты
- [x] Task 4: Реализовать HTML и PDF экстракторы прайс-листов с тестами на фикстурах
- [x] Task 5: Реализовать DOCX и Excel экстракторы прайс-листов с тестами на фикстурах

### Checkpoint 2: Politeness & Extractors
- [x] Все тесты HTTP-клиента и 4 экстракторов проходят, `ruff` и `mypy` без ошибок

### Phase 3: Ingestion Core & Provider Contract
- [x] Task 6: Реализовать `RawServiceInput`, `BaseSourceAdapter`, `AdapterRegistry` и `IngestionRunner` (дедупликация + изоляция ошибок)
- [x] Task 7: Реализовать публичный `IngestionService`, `scheduler.py`, `cli.py` и очистку старше 90 дней

### Checkpoint 3: Ingestion Core
- [x] Повторный запуск на фикстурном адаптере даёт 0 дублей, падение одного адаптера не останавливает второй, `purge_expired_raw_records` защищён порогом ≥ 90 дней

### Phase 4: Real KZ Source Adapters & Live Verification
- [x] Task 8: Реализовать адаптер #1 — `kdlolymp.kz` (КДЛ Олимп) с фикстурными тестами
- [x] Task 9: Реализовать адаптер #2 — `invivo.kz` (Лаборатория INVIVO) с фикстурными тестами
- [x] Task 10: Реализовать адаптер #3 — `doq.kz` (DOQ.kz) с фикстурными тестами
- [x] Task 11: Провести живой E2E-прогон (≥ 3 источника, ≥ 100 услуг, 0 дублей при перезапуске) и финальную проверку качества

### Checkpoint 4: Module Complete
- [x] Все критерии успеха из `SPEC-ingestion.md` выполнены, покрытие ≥ 80%, `ruff` и `mypy` чистые
- [x] Ревью с человеком перед переходом к `SPEC-normalization.md`

## Parallelization Opportunities

- **Можно выполнять параллельно**: Task 3 (`PoliteHttpClient`), Task 4 (HTML/PDF), Task 5 (DOCX/Excel) после Task 2; а также Task 8, Task 9, Task 10 (три независимых адаптера источников) после Task 7.
- **Строго последовательно**: Task 1 → Task 2 → Task 6 → Task 7 → Task 11.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `invitro.kz` запрещает обход в `robots.txt` (`Disallow: /`), `helix.kz` имеет сломанную TLS-цепочку | High | Не обходим `robots.txt` и не отключаем TLS-валидацию; заменяем на проверенные открытые источники РК (`invivo.kz`, `doq.kz`, опционально `mck.kz`) после подтверждения пользователя |
| Часть страниц выбранных сайтов рендерится через JS (SPA) | High | В начале каждой задачи адаптера (Tasks 8–10) проверяем HTML и публичные JSON/sitemap-эндпоинты сайта; если JSON/SSR нет — эскалируем по правилу `Ask first` до добавления Playwright |
| Сетевые таймауты / временная недоступность сайта при живом прогоне | Medium | `PoliteHttpClient` с exponential backoff и таймаутами + полная изоляция ошибок в `IngestionRunner` + офлайн-фикстуры для всех автотестов |
| Различие прав/SELinux-меток на bind-mount в `podman` | Medium | Используем флаг `:Z` в `podman run -v` и фиксируем команды в `Makefile` |
| Блокировка по частоте запросов при тестировании | Medium | Строгий `min_delay_sec >= 1.5s`, `concurrency=1` на домен и флаг `--limit` в CLI для ограниченных прогонов |

## Resolved Decisions

1. **Утверждённая тройка источников V1**: **`kdlolymp.kz` + `invivo.kz` + `doq.kz`** (все три проверены на разрешающий `robots.txt` и валидный TLS; `invitro.kz` и `helix.kz` исключены).
2. **План утверждён**: переходим к Phase 4 (Implement), начиная с Task 1.

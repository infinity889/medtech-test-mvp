# MedServicePrice.kz — MVP

Агрегатор и сравнение цен на медицинские услуги в Казахстане (анализы, приёмы врачей, диагностика).

## Архитектура (Capability Map)

Проект разрабатывается строго по Spec-Driven Development — см. [CAPABILITY-MAP.md](./CAPABILITY-MAP.md):

1. **`ingestion`** ([SPEC-ingestion.md](./SPEC-ingestion.md)) — сбор прайс-листов из публичных источников, соблюдение `robots.txt` и rate-limit, raw-слой PostgreSQL (ретеншн ≥ 90 дней), экстракторы HTML/PDF/DOCX/Excel, дедупликация, журнал ошибок, CLI и планировщик.
2. **`normalization`** ([SPEC-normalization.md](./SPEC-normalization.md)) — справочник из 88 канонических услуг по 4 категориям, детерминированный матчер (`exact` → `synonym` → категорийно-изолированный `RapidFuzz`), конвертация `USD → KZT` (`Decimal`), дедуплицированные клиники и предложения, история цен (`price_history`), очередь ручной разметки (`unmatched_services`) и правило актуальности ≤ 30 дней.
3. **`search-api`** *(следующий этап)* — REST API поиска, фильтрации, сортировки и админки.
4. **`web-ui`** *(запланирован)* — адаптивный интерфейс (React + Vite + Leaflet).

## Подключённые открытые источники (`ingestion`)

Все источники проверены на разрешающий `robots.txt` и валидный TLS:

| `source_id` | Источник | Данные | Города |
|---|---|---|---|
| `kdlolymp` | [kdlolymp.kz](https://kdlolymp.kz) (КДЛ Олимп) | Лабораторные анализы, цены в KZT, сроки | Алматы, Астана, Шымкент, Караганда, Актобе, Павлодар |
| `invivo` | [invivo.kz](https://invivo.kz) (Лаборатория INVIVO) | Лабораторные анализы, цены в KZT, сроки | Алматы, Астана, Шымкент |
| `doq` | [doq.kz](https://doq.kz) (DOQ.kz) | Приёмы врачей, диагностика, адреса, GPS, рейтинги, онлайн-запись | Алматы, Астана, Шымкент |

## Быстрый старт (`podman` + Python 3.12 + PostgreSQL 16)

Требования на хосте: `podman`, `make`.

```bash
# 1. Собрать Python 3.12 образ backend
make backend-build

# 2. Поднять PostgreSQL 16 и применить миграции Alembic
make db-up
make migrate

# 3. Запустить все офлайн-тесты (ingestion + normalization) с покрытием + проверки качества
make test-all
make lint
make typecheck

# 4. Запустить сбор реальных данных по всем 3 источникам (опционально --limit N)
make ingest SOURCE=all EXTRA_ARGS="--limit 600"

# 5. Загрузить справочник услуг (88 позиций) и выполнить нормализацию raw → normalized
make seed-catalog
make normalize

# Просмотреть статистику нормализованного слоя
podman run --rm --network medprice-net -v $(pwd)/backend:/app:Z \
  -e DATABASE_URL=postgresql+psycopg://medprice:medprice@medprice-pg:5432/medprice \
  medprice-backend:dev python -m app.normalization.cli stats
```

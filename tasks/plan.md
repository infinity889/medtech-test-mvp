# Implementation Plan: Normalization (`normalization`) — V1

Source spec: [SPEC-normalization.md](../SPEC-normalization.md)

## Overview

Реализуем модуль `normalization` — детерминированный пайплайн приведения сырых записей из `raw_service_records` (через контракт `IngestionService.iter_raw_records`) к единой витрине медицинских услуг Казахстана: справочник ≥ 50 (целевой объём 65–80) канонических услуг по 4 категориям, `RapidFuzz`-матчинг с категорийной изоляцией, конвертация валют `USD → KZT` через `Decimal`, дедуплицированные таблицы `clinics` и `service_offers`, история цен `price_history`, очередь ручной разметки `unmatched_services` с пополнением синонимов и правило свежести ≤ 30 дней.

## Architecture Decisions

1. **Строгая односторонняя зависимость (`normalization → ingestion`)**: `NormalizationPipeline` читает сырые данные исключительно через `IngestionService.iter_raw_records(...)` и никогда не изменяет таблицы raw-слоя.
2. **Категорийная изоляция матчинга**: при наличии `category_hint` (`лаборатория`, `приём врача`, `диагностика`, `процедура`) `RapidFuzz` сопоставляет только в рамках соответствующей категории `ServiceCategory`, исключая ложные склейки между анализами и приёмами врачей.
3. **Уникальность предложения `UNIQUE (clinic_id, service_id)`**: одна актуальная запись на пару `(клиника, услуга)`; если в одном сыром прайсе несколько вариантов одной услуги в той же клинике, выбирается более свежая запись (`parsed_at`), а при равной свежести — минимальная `price_kzt` (аналогично Aviasales).
4. **Безубыточная история цен (`price_history`)**: снимок добавляется только при первом появлении пары `(clinic_id, service_id)` и при реальном изменении `price_kzt` относительно последней точки — повторный запуск `make normalize` даёт 0 дублей.
5. **Обратная связь ручной разметки**: `resolve_unmatched(..., add_as_synonym=True)` не только создаёт `service_offers` для выбранной записи, но и добавляет `service_name_raw` в `service_catalog.synonyms` и автоматически резолвит все совпадающие `pending`-записи с тем же `service_name_raw`.

## Dependency Graph

```text
Task 1 (rapidfuzz in Containerfile/pyproject + Settings + Makefile)
   │
   └── Task 2 (Normalization ORM models + Alembic 0002 migration + schema tests)
          │
          ├── Task 3 (text_utils: text normalization + USD→KZT Decimal converter)
          └── Task 4 (catalog_seed.json: 65–80 services from real KZ raw data)
                 │
                 └── Task 5 (ServiceMatcher: exact → synonym → category-isolated RapidFuzz)
                        │
                        └── Task 6 (DTOs + NormalizationPipeline: clinics, offers, price_history, unmatched)
                               │
                               └── Task 7 (NormalizationService contract + CLI + synonym feedback loop + 30d stale)
                                      │
                                      └── Task 8 (Live run on 2,625 real records, cross-clinic verification & README)
```

## Task List

Подробные карточки задач (описание, критерии приёмки, команды проверки, файлы, размер) находятся в [tasks/todo.md](./todo.md).

### Phase 1: Foundation
- [x] Task 1: Добавить `rapidfuzz`, настройки нормализации в `Settings`, цели в `Makefile` и пересобрать контейнер
- [x] Task 2: Реализовать ORM-модели слоя `normalization` и обратимую миграцию Alembic `0002`

### Checkpoint 1: Foundation
- [x] Образ `medprice-backend:dev` пересобран с `rapidfuzz`, миграция `0002` обратима, существующие 48 тестов `ingestion` зелёные

### Phase 2: Dictionary & Matching Engine
- [x] Task 3: Реализовать нормализацию текста и конвертацию валют `KZT`/`USD → KZT` (`text_utils.py`)
- [ ] Task 4: Сформировать курируемый справочник `catalog_seed.json` (65–80 услуг по 4 категориям на базе реальных данных РК)
- [ ] Task 5: Реализовать детерминированный `ServiceMatcher` (`exact` → `synonym` → `RapidFuzz`)

### Checkpoint 2: Dictionary & Matching Engine
- [ ] Справочник ≥ 50 позиций и матчер (включая кейс `ОАК`/`CBC` и категорийную изоляцию) покрыты юнит-тестами, `ruff` и `mypy` чистые

### Phase 3: Pipeline, Public Contract & CLI
- [ ] Task 6: Реализовать DTO (`schemas.py`) и `NormalizationPipeline` (клиники, предложения, `price_history`, `unmatched_services`)
- [ ] Task 7: Реализовать публичный `NormalizationService` (включая `resolve_unmatched`, `ignore_unmatched`, `get_price_history`, `refresh_stale_offers`) и CLI

### Checkpoint 3: Pipeline & Service
- [ ] Интеграционные тесты против PostgreSQL подтверждают 0 дублей при повторе, версионирование `price_history`, обратную связь синонимов и деактивацию > 30 дней

### Phase 4: Live Verification on Real KZ Data
- [ ] Task 8: Прогнать `make seed-catalog && make normalize` на 2 625 реальных raw-записях, проверить межклинические пересечения, идемпотентность, покрытие ≥ 85% и обновить `README.md`

### Checkpoint 4: Module Complete
- [ ] Все 8 критериев успеха из `SPEC-normalization.md` выполнены, покрытие ≥ 85%, `ruff` и `mypy` чистые
- [ ] Ревью с человеком перед переходом к `SPEC-search-api.md`

## Parallelization Opportunities

- **Можно выполнять параллельно**: Task 3 (`text_utils.py`) и Task 4 (`catalog_seed.json`) после Task 2.
- **Строго последовательно**: Task 1 → Task 2 → Task 5 → Task 6 → Task 7 → Task 8.

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Ложные склейки похожих анализов в `RapidFuzz` (напр. «Витамин B12» и «Витамин D» или «АЛТ» и «АСТ») | High | Консервативный порог `86.0`, категорийная изоляция и проверка коротких/конфликтных анализов в юнит-тестах `test_matcher.py`; сомнительные уходят в `unmatched_services` |
| Дубликаты названий с разным регистром/звёздочками (`Подсчет ретикулоцитов*`, `Кровь. Гематокрит`) снижают recall | Medium | Анализируем топ реальных строк из `raw_service_records` при составлении `catalog_seed.json` (Task 4) и снимаем шумовые префиксы/символы в `text_utils.py` |
| Пересборка `medprice-backend:dev` при добавлении `rapidfuzz` займёт время | Low | `rapidfuzz` распространяется как готовый binary wheel под `cp312-manylinux`; пересборка делается один раз в Task 1 |
| Старые raw-записи `kdlolymp`/`invivo` без адреса из раннего прогона конфликтуют с новыми записями с адресом | Medium | Дедупликация в `clinics` по `(source_id, clinic_name, city, address)`; перед финальным живым прогоном в Task 8 проверим чистоту витрины `clinics` и `service_offers` |

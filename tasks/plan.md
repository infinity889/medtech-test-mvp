# Implementation Plan: Web UI (`web-ui`) — V1

Source spec: [SPEC-web-ui.md](../SPEC-web-ui.md)

## Overview

Реализуем адаптивный веб-интерфейс MedServicePrice.kz на **React 19 + TypeScript (strict) + Vite 6 + Tailwind CSS v4 + Leaflet (OpenStreetMap)** в контейнере Node 22 (`podman`), потребляющий REST API модуля `search-api` (`/api/v1/*`) без хардкодных данных.

## Architecture Decisions

1. **Контейнеризированный Node 22 (`medprice-web:dev`)**: весь toolchain (`vite`, `vitest`, `tsc`, `eslint`) запускается в `podman` на базе `docker.io/library/node:22-alpine` в сети `medprice-net`, проксируя `/api` на `http://medprice-api:8000` (обход проблем CORS и отсутствие зависимости от Node на хосте).
2. **Tailwind CSS v4 + семантические клинические токены (`@theme`)**: палитра `#0F766E` (клинический бирюзовый), `#047857` (лучшая цена), `#F8FAFC` (фон), `#0F172A` (текст), `tabular-nums` для цен и расстояний — чистая типографика и высокая читаемость без AI-градиентов.
3. **URL-driven состояние поиска**: все фильтры, запрос, выбранная услуга, сортировка, геолокация и страница хранятся в `URLSearchParams` (`useSearchParams`), обеспечивая шаринг ссылок и работу кнопки «Назад».
4. **Контекст сравнения клиник (`CompareContext`)**: 2–5 клиник хранятся в `localStorage` и синхронизируются с `?clinic_ids=...` на `/compare`; липкий `CompareDock` доступен на всех пациентских страницах.
5. **Современные веб-примитивы и доступность (WCAG 2.1 AA)**: WAI-ARIA combobox для автодополнения, нативный `<dialog>` (`showModal()`) для графика истории цен, семантические кнопки/ссылки, явные бейджи и иконки (не только цвет), skeleton/empty/error состояния.
6. **Безопасность админки**: `X-Admin-Token` вводится пользователем на `/admin` и хранится только в `sessionStorage`, никогда не попадая в бандл или URL.

## Dependency Graph

```text
Task 1 (frontend/ scaffold: Node 22 Containerfile, React 19 + Vite 6 + Tailwind v4 + Leaflet + Vitest + ESLint, Makefile targets)
   │
   └── Task 2 (API client + strict TS types + format utils + CompareContext + Layout/Header/CompareDock + unit tests)
          │
          ├── Task 3 (SearchPage '/': WAI-ARIA SearchBar autocomplete, FiltersPanel + geolocation, OfferCard + sorting/pagination + tests)
          │
          ├── Task 4 (MapPage '/map' with reusable Leaflet ClinicMap + ClinicDetailPage '/clinics/:id' with 2GIS/Google Maps + PriceHistoryDialog SVG chart)
          │
          ├── Task 5 (ComparePage '/compare' 2–5 clinics matrix with cheapest highlight + tests)
          │
          └── Task 6 (AdminPage '/admin': X-Admin-Token login, stats, sources, manual scrape + 409 handling, unmatched resolve/ignore + tests)
                 │
                 └── Task 7 (Live end-to-end verification against medprice-api in browser: 375px & 1440px, console=0 errors, README update)
```

## Task List

Подробные карточки задач находятся в [tasks/todo.md](./todo.md).

### Phase 1: Runtime & Core Foundation
- [x] Task 1: Создать `frontend/` (Node 22 `Containerfile`, `package.json`, `vite.config.ts`, `tsconfig.json`, `eslint.config.js`, Tailwind v4 `app.css`), добавить цели `web-*` в `Makefile` и собрать образ `medprice-web:dev`
- [x] Task 2: Реализовать `api/types.ts`, `api/client.ts`, `utils/format.ts`, `CompareContext`, `StateViews`, `Layout` и `CompareDock` (+ unit-тесты)

### Checkpoint 1: Frontend Foundation
- [x] Образ `medprice-web:dev` собран, `make test-web`, `make lint-web`, `make typecheck-web`, `make build-web` зелёные

### Phase 2: Patient Experience (Search, Map, Clinic Detail, Price History & Compare)
- [x] Task 3: Реализовать `SearchPage` (`/`) — WAI-ARIA `SearchBar` с автодополнением, `FiltersPanel` с геолокацией и URL-синхронизацией, `OfferCard`, сводку цен, сортировку и пагинацию (+ тесты)
- [x] Task 4: Реализовать переиспользуемый `ClinicMap` (Leaflet + OpenStreetMap), `MapPage` (`/map`), `ClinicDetailPage` (`/clinics/:clinicId`) и `PriceHistoryDialog` (нативный `<dialog>` + SVG-график) (+ тесты)
- [ ] Task 5: Реализовать `ComparePage` (`/compare`) — матрица сравнения 2–5 клиник с фильтрацией по категории и подсветкой лучшей цены (+ тесты)

### Checkpoint 2: Patient Flows Complete
- [ ] Все пациентские экраны (`/`, `/map`, `/clinics/:id`, `/compare`, график истории цен) реализованы и покрыты тестами Vitest

### Phase 3: Admin UI & Live Browser Verification
- [ ] Task 6: Реализовать `AdminPage` (`/admin`) — форма токена (`sessionStorage`), статистика, источники, ручной запуск парсинга с обработкой `409`, история запусков/ошибок и 1-клик разметка/игнорирование `unmatched` (+ тесты)
- [ ] Task 7: Поднять `make api-up` + `make web-up` на живых данных `medprice`, провести проверку в реальном браузере (десктоп `1440px` и мобильный `375px`, 0 ошибок в консоли), обновить `README.md`

### Checkpoint 3: Module Complete (MVP Ready)
- [ ] Все 5 критериев успеха из `SPEC-web-ui.md` выполнены; `make test-all`, `make test-web`, `make lint-web`, `make typecheck-web`, `make build-web` зелёные
- [ ] Финальное ревью пользователя

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Иконки маркеров Leaflet по умолчанию ломаются при сборке Vite | Medium | Используем аккуратные кастомные `L.divIcon` в стиле клинической палитры (не зависят от относительных PNG-путей Leaflet и выглядят заметно чище) |
| Стили Tailwind Preflight конфликтуют с контейнером карты Leaflet | Medium | Явно сохраняем `max-width: none` для `.leaflet-pane img` в `src/styles/app.css` |
| Блокировка геолокации в браузере пользователя | Low | Явное дружелюбное сообщение при `PERMISSION_DENIED` без поломки остальных фильтров и сортировок |

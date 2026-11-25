# Task List: Web UI (`web-ui`) — V1

Source plan: [tasks/plan.md](./plan.md) | Source spec: [SPEC-web-ui.md](../SPEC-web-ui.md)

---

## Task 1: Инициализировать `frontend/` (Node 22 Containerfile, React 19, Vite 6, Tailwind CSS v4, Leaflet, Vitest, ESLint) и цели `Makefile`

**Description:** Создать каркас `frontend/` с `Containerfile` на базе `docker.io/library/node:22-alpine`, `package.json`, `tsconfig.json` (`strict: true`), `vite.config.ts` (прокси `/api → http://medprice-api:8000` + конфиг Vitest), `eslint.config.js`, `index.html` (`lang="ru"`), `src/styles/app.css` (`@import "tailwindcss"` + `@theme` клинические токены + fix для Leaflet), минимальный `App.tsx`, добавить цели `web-build`, `web-up`, `web-down`, `test-web`, `lint-web`, `typecheck-web`, `build-web` в `Makefile` и собрать образ `medprice-web:dev`.

**Acceptance criteria:**
- [x] `make web-build` успешно собирает образ `medprice-web:dev` с установленным `node_modules`.
- [x] `make typecheck-web`, `make lint-web` и `make build-web` проходят без ошибок.
- [x] Проверены гайды `modern-web-guidance` (dialog, combobox/form, responsive table) внутри контейнера перед реализацией UI-компонентов.

**Verification:**
- [x] Build succeeds: `make web-build && make build-web`
- [x] Lint & types pass: `make lint-web && make typecheck-web`

**Dependencies:** None

**Files likely touched:**
- `frontend/Containerfile`
- `frontend/package.json`
- `frontend/tsconfig.json`
- `frontend/vite.config.ts`
- `frontend/eslint.config.js`
- `frontend/index.html`
- `frontend/src/styles/app.css`
- `frontend/src/main.tsx`
- `frontend/src/App.tsx`
- `Makefile`

**Estimated scope:** Medium

---

## Task 2: Реализовать API-клиент, типы, утилиты форматирования, `CompareContext`, `Layout`, `CompareDock` и `StateViews`

**Description:** Создать строгие TypeScript-контракты `src/api/types.ts` (1:1 с `SPEC-search-api.md`), типизированный `src/api/client.ts` (с `ApiClientError`, поддержкой `AbortSignal` и заголовка `X-Admin-Token`), утилиты форматирования `src/utils/format.ts` (валюта `₸`, относительная и точная дата обновления, дистанция км, срок готовности), `src/context/CompareContext.tsx` (2–5 клиник + `localStorage`), общие `StateViews` (skeleton, empty, error) и каркас `Layout` + `CompareDock`. Написать unit-тесты на `format.ts`, `client.ts` и `CompareContext`.

**Acceptance criteria:**
- [x] `ApiClientError` корректно парсит единый формат ошибок `APIError` (`401`/`404`/`409`/`422`/`500`).
- [x] `CompareContext` хранит до 5 уникальных клиник, не позволяет добавить 6-ю и сохраняет состояние в `localStorage`.
- [x] `formatPriceKzt`, `formatFreshness`, `formatDuration` корректно форматируют казахстанские цены и даты на русском языке.

**Verification:**
- [x] Tests pass: `make test-web`
- [x] Checks pass: `make lint-web && make typecheck-web`

**Dependencies:** Task 1

**Files likely touched:**
- `frontend/src/api/types.ts`
- `frontend/src/api/client.ts`
- `frontend/src/utils/format.ts`
- `frontend/src/context/CompareContext.tsx`
- `frontend/src/components/StateViews.tsx`
- `frontend/src/components/Layout.tsx`
- `frontend/src/components/CompareDock.tsx`
- `frontend/src/test/setup.ts`
- `frontend/src/test/core.test.tsx`

**Estimated scope:** Medium

---

## Checkpoint 1: After Tasks 1–2 (Frontend Foundation)
- [x] Образ `medprice-web:dev` собран, каркас приложения и unit-тесты зелёные

---

## Task 3: Реализовать `SearchPage` (`/`) — Aviasales-поиск, WAI-ARIA автодополнение, фильтры, геолокация, сортировка и `OfferCard`

**Description:** Реализовать `SearchBar` (WAI-ARIA combobox с debounce-запросом `/api/v1/services/autocomplete`, клавиатурой `↑`/`↓`/`Enter`/`Esc` и отображением `offers_count` + `min_price_kzt`), `FiltersPanel` (город, категория, мин/макс цена, мин. рейтинг, онлайн-запись, кнопка «Рядом со мной» через `navigator.geolocation`, мобильный выдвижной блок), `OfferCard` (каноническое и оригинальное название, цена с бейджем «Лучшая цена», срок, рейтинг, `parsed_at`, ссылка на источник, кнопки «История цен» и «Сравнить») и `SearchPage` с синхронизацией URL `searchParams`, сводкой цен, сортировкой и пагинацией.

**Acceptance criteria:**
- [x] Ввод `ОАК` или `CBC` открывает список подсказок автодополнения и позволяет выбрать услугу мышью или клавиатурой.
- [x] Все фильтры и сортировки синхронизируются с URL и отправляют корректные параметры в `GET /api/v1/offers`.
- [x] Каждая карточка показывает дату последнего обновления (`parsed_at`) и ссылку на первоисточник.
- [x] Обработаны состояния загрузки (skeleton), пустой выдачи, ошибки сети и отказа геолокации.

**Verification:**
- [x] Tests pass: `make test-web` (`SearchPage.test.tsx`)
- [x] Checks pass: `make lint-web && make typecheck-web`

**Dependencies:** Task 2

**Files likely touched:**
- `frontend/src/components/SearchBar.tsx`
- `frontend/src/components/FiltersPanel.tsx`
- `frontend/src/components/OfferCard.tsx`
- `frontend/src/pages/SearchPage.tsx`
- `frontend/src/test/SearchPage.test.tsx`

**Estimated scope:** Medium

---

## Task 4: Реализовать `ClinicMap` (Leaflet), `MapPage` (`/map`), `ClinicDetailPage` (`/clinics/:clinicId`) и `PriceHistoryDialog`

**Description:** Реализовать переиспользуемый компонент карты `ClinicMap` (Leaflet + OpenStreetMap, кастомные клинические `divIcon` маркеры, `fitBounds`, попапы со ссылками на карточку, 2GIS и Google Maps), страницу `MapPage` (`/map`, фильтр по городу/поиску, список клиник + карта), страницу `ClinicDetailPage` (`/clinics/:clinicId`, контакты, график, мини-карта, кнопки 2GIS/Google Maps, добавление в сравнение, таблица всех актуальных услуг с поиском/фильтром по категории) и `PriceHistoryDialog` (нативный `<dialog>` с `showModal()`, выбором периода `30`/`90`/`365` дней и адаптивным SVG-графиком истории цен).

**Acceptance criteria:**
- [x] `MapPage` отображает клиники с GPS (`has_geo=true`), фильтрует по городу и показывает ссылки маршрутов 2GIS / Google Maps.
- [x] `ClinicDetailPage` загружает карточку клиники, отображает контакты, маршруты и таблицу услуг с датами обновления (`404` → понятное состояние ошибки).
- [x] `PriceHistoryDialog` открывается в нативном `<dialog>`, строит SVG-график по точкам `GET /api/v1/services/{id}/price-history` и корректно переключает период.

**Verification:**
- [x] Tests pass: `make test-web` (`ClinicAndHistory.test.tsx`)
- [x] Checks pass: `make lint-web && make typecheck-web`

**Dependencies:** Task 3

**Files likely touched:**
- `frontend/src/components/ClinicMap.tsx`
- `frontend/src/components/PriceHistoryDialog.tsx`
- `frontend/src/pages/MapPage.tsx`
- `frontend/src/pages/ClinicDetailPage.tsx`
- `frontend/src/test/ClinicAndHistory.test.tsx`

**Estimated scope:** Medium

---

## Task 5: Реализовать `ComparePage` (`/compare`) — табличное сравнение 2–5 клиник

**Description:** Реализовать страницу `ComparePage`, которая читает `clinic_ids` из URL (или из `CompareContext`), вызывает `GET /api/v1/compare`, строит адаптивную таблицу «услуга × клиники» с горизонтальной прокруткой на мобильных и фиксированным столбцом услуги, фильтром по категории, подсветкой `cheapest_clinic_id` (бейдж «Выгоднее» + иконка, не только цвет), датами обновления и кнопками удаления клиники из сравнения.

**Acceptance criteria:**
- [x] При `< 2` выбранных клиник показывается понятное пустое состояние с переходом к поиску/карте.
- [x] Для 2–5 клиник отображается матрица цен с выделением лучшей цены в каждой строке и расчётом экономии.
- [x] Работает синхронизация `CompareDock` ↔ `/compare?clinic_ids=...`.

**Verification:**
- [x] Tests pass: `make test-web` (`CompareFlow.test.tsx`)
- [x] Checks pass: `make lint-web && make typecheck-web`

**Dependencies:** Task 4

**Files likely touched:**
- `frontend/src/pages/ComparePage.tsx`
- `frontend/src/test/CompareFlow.test.tsx`

**Estimated scope:** Small

---

## Checkpoint 2: After Tasks 3–5 (Patient Experience Complete)
- [x] Все пациентские экраны (`/`, `/map`, `/clinics/:id`, `/compare`, график истории цен) работают и покрыты тестами Vitest
- [x] `make lint-web`, `make typecheck-web`, `make build-web` зелёные

---

## Task 6: Реализовать `AdminPage` (`/admin`) — токен, запуск парсинга, статистика и разбор `unmatched queue`

**Description:** Реализовать защищённый экран оператора `/admin`: ввод `X-Admin-Token` (хранение в `sessionStorage`, кнопка «Выйти»), карточки статистики (`/admin/stats`), список источников и кнопку ручного запуска парсинга + нормализации (`POST /admin/scrape-runs` с обработкой `409 SCRAPE_IN_PROGRESS`), вкладки «Очередь разметки (`unmatched`)» с 1-клик кнопками «Привязать к подсказке» (`resolve`) и «Игнорировать» (`ignore`), а также вкладки «История запусков» и «Ошибки».

**Acceptance criteria:**
- [x] Неверный токен (`401 UNAUTHORIZED`) показывает понятное сообщение и сбрасывает сессию.
- [x] Ошибка `409 SCRAPE_IN_PROGRESS` отображается как информационное предупреждение без падения интерфейса.
- [x] Кнопки `resolve` и `ignore` вызывают соответствующие POST-эндпоинты и обновляют список и счётчики.

**Verification:**
- [x] Tests pass: `make test-web` (`AdminPage.test.tsx`)
- [x] Checks pass: `make lint-web && make typecheck-web`

**Dependencies:** Task 5

**Files likely touched:**
- `frontend/src/pages/AdminPage.tsx`
- `frontend/src/test/AdminPage.test.tsx`

**Estimated scope:** Medium

---

## Task 7: Живой запуск (`make api-up` + `make web-up`), проверка в браузере (Desktop + Mobile) и обновление `README.md`

**Description:** Поднять полный стек (`medprice-pg` + `medprice-api` + `medprice-web`), проверить все экраны в реальном браузере на живых данных (поиск `ОАК`, фильтры, карта Leaflet, карточка клиники, сравнение `КДЛ Олимп` vs `INVIVO`, график истории цен, админка), проверить адаптивность (`375px` и `1440px`) и отсутствие ошибок в консоли, прогнать все тесты backend + frontend и обновить `README.md`.

**Acceptance criteria:**
- [x] `http://localhost:5173` загружается и работает с реальными данными `medprice-api` без ошибок в консоли браузера.
- [x] Проверены брейкпоинты `375px` (мобильный) и `1440px` (десктоп).
- [x] `make test-all`, `make test-web`, `make lint-web`, `make typecheck-web`, `make build-web` проходят без ошибок.

**Verification:**
- [x] Full suite passes: `make test-all && make test-web && make lint-web && make typecheck-web && make build-web`
- [x] Live browser check via browser subagent on `http://localhost:5173`

**Dependencies:** Task 6

**Files likely touched:**
- `README.md`

**Estimated scope:** Small

---

## Checkpoint 3: After Task 7 (Module Complete — MVP Ready)
- [x] Все 5 критериев успеха из [SPEC-web-ui.md](../SPEC-web-ui.md) подтверждены
- [x] Готово к финальному ревью пользователя и пушу на GitHub

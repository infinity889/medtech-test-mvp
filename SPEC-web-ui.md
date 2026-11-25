# Spec: Web UI (`web-ui`) — V1

> Часть карты модулей [CAPABILITY-MAP.md](./CAPABILITY-MAP.md). Модуль `web-ui` потребляет REST API модуля [`search-api`](./SPEC-search-api.md) (`/api/v1/*`) и предоставляет адаптивный веб-интерфейс (Desktop + Mobile) для пациентов и операторов MedServicePrice.kz.

## Objective

Создать быстрый, доступный (WCAG 2.1 AA) и визуально выверенный веб-интерфейс для сравнения цен на медицинские услуги в Казахстане (анализы, приёмы врачей, диагностика, процедуры):

- **Поиск в стиле Aviasales (`/`)**:
  - Выбор города, строка поиска с живым автодополнением (поддержка русских/английских синонимов `ОАК`/`CBC`, клавиатурная навигация `↑`/`↓`/`Enter`/`Esc`), быстрые категории и популярные запросы.
  - Боковая/складывающаяся панель фильтров (синхронизирована с URL `searchParams`): город, категория, диапазон цен ₸, минимальный рейтинг, «Есть онлайн-запись», кнопка «Рядом со мной» (`navigator.geolocation` с корректным fallback при отказе).
  - Сортировка (`price_asc`, `price_desc`, `distance_asc`, `updated_desc`, `rating_desc`), сводка цен (`от / средняя / до`), карточки выдачи с прозрачным отображением **даты обновления (`parsed_at`)** и ссылки на первоисточник.
- **Карта клиник (`/map`)**:
  - Интерактивная карта **Leaflet + OpenStreetMap** с маркерами всех клиник с GPS-координатами (`GET /api/v1/clinics?has_geo=true`), фильтрацией по городу, попапами с рейтингом, количеством услуг, минимальной ценой и прямыми ссылками маршрута в **2GIS** и **Google Maps**.
- **Карточка клиники (`/clinics/:clinicId`)**:
  - Контакты, адрес, телефон (`tel:`), график работы, рейтинг, статус онлайн-записи, встроенная мини-карта Leaflet, кнопки маршрута **2GIS / Google Maps**, кнопка добавления в сравнение и таблица всех актуальных (≤ 30 дней) услуг клиники с локальным фильтром.
- **Сравнение 2–5 клиник в таблице (`/compare`)**:
  - Плавающая панель (док) выбора клиник из поиска, карты или карточки (2–5 клиник, сохраняется в `localStorage` и передаётся в URL `?clinic_ids=...`).
  - Сравнительная матрица «услуга × клиники» (`GET /api/v1/compare`) с фильтром по категории, явным выделением лучшей цены (`cheapest_clinic_id`, бейдж + иконка, не только цвет) и переходом на первоисточник.
- **График истории изменения цен**:
  - Лёгкий адаптивный SVG-график (`GET /api/v1/services/{service_id}/price-history`) в модальном диалоге `<dialog>` с переключением периода (`30` / `90` / `365` дней), доступный прямо из карточки предложения и карточки клиники.
- **Админ-панель (`/admin`)**:
  - Авторизация по `X-Admin-Token` (ввод токена на экране, хранение в `sessionStorage`), сводка статистики (`/admin/stats`), список источников, кнопка ручного запуска парсинга + нормализации (`POST /admin/scrape-runs` с обработкой `409 SCRAPE_IN_PROGRESS`), история запусков/ошибок и очередь `unmatched` с 1-клик действиями **«Привязать»** (`resolve`) и **«Игнорировать»** (`ignore`).

### Визуальная система и дизайн-контракт
- **Характер интерфейса**: клиническая чистота и высокая информационная плотность (вдохновлено современными сервисами сравнения цен и цифрового здравоохранения — без фиолетовых AI-градиентов и декоративного шума).
- **Семантическая палитра (CSS Custom Properties)**:
  - Фон страницы `#F8FAFC`, поверхности карточек `#FFFFFF`, границы `#E2E8F0`.
  - Основной акцент: глубокий медицинский бирюзовый (`#0F766E` / hover `#115E59`), контраст ≥ 4.5:1.
  - Акцент лучшей цены / экономии: изумрудный (`#047857` на `#ECFDF5`) с текстовым бейджем «Лучшая цена».
  - Текст: `#0F172A` (основной), `#475569` (вторичный), `#B91C1C` (ошибки).
- **Типографика**: системный стек sans-serif (`Inter` / `-apple-system` / `Segoe UI`), для всех цен и расстояний — `font-variant-numeric: tabular-nums` для идеального выравнивания колонок.
- **Адаптивность**: mobile-first, проверка на брейкпоинтах `320px`, `768px`, `1024px`, `1440px`.

## Tech Stack

- **Runtime / сборка**: **Node.js 22 (`docker.io/library/node:22-alpine`) в контейнере `podman`** (`medprice-web:dev`, без требования устанавливать Node на хост)
- **Фреймворк**: React 19, TypeScript (`strict: true`), Vite 6, React Router v7
- **Карта**: `leaflet` + `@types/leaflet` (OpenStreetMap тайлы, без платных API-ключей)
- **Стили**: **Tailwind CSS v4** (`tailwindcss` + `@tailwindcss/vite`) с семантическими клиническими дизайн-токенами в `@theme` (`src/styles/app.css`) и изоляцией стилей Leaflet (`leaflet/dist/leaflet.css`)
- **Тесты и качество**: Vitest, `@testing-library/react`, `@testing-library/user-event`, `jsdom`, `eslint`, `tsc --noEmit`

## Commands

```bash
# Собрать frontend-образ Node 22 + зависимости (medprice-web:dev)
make web-build

# Запустить Vite dev-сервер (порт 5173, прокси /api -> medprice-api:8000 в сети medprice-net)
make web-up
make web-down

# Проверки качества frontend (внутри контейнера medprice-web:dev)
make test-web       # vitest run
make lint-web       # eslint src
make typecheck-web  # tsc --noEmit
make build-web      # vite build (production bundle check)
```

## Project Structure

```text
frontend/
├── Containerfile                 → Node 22 Alpine образ с установленными npm-зависимостями
├── package.json                  → React 19, Vite 6, React Router, Leaflet, Vitest, ESLint
├── tsconfig.json                 → TypeScript strict config
├── vite.config.ts                → Proxy /api -> VITE_API_PROXY_TARGET (http://medprice-api:8000) + Vitest config
├── index.html                    → lang="ru", title MedServicePrice.kz, meta viewport
└── src/
    ├── main.tsx                  → Точка входа, BrowserRouter, подключение tokens.css и leaflet.css
    ├── App.tsx                   → Layout (Header, Main, CompareDock, Footer) и маршруты (/, /map, /clinics/:id, /compare, /admin)
    ├── styles/
    │   └── app.css               → @import "tailwindcss", @theme семантические токены, табличные цифры, focus-visible и стили Leaflet
    ├── api/
    │   ├── types.ts              → Строгие TS-интерфейсы 1:1 к OpenAPI-контракту search-api
    │   └── client.ts             → Типизированный fetch-клиент с разбором APIError и AbortSignal
    ├── context/
    │   └── CompareContext.tsx    → Состояние выбранных 2–5 клиник (localStorage + методы add/remove/clear)
    ├── utils/
    │   └── format.ts             → Форматирование KZT, дат обновления (относительно + точно), расстояний, сроков
    ├── components/
    │   ├── Layout/               → Адаптивная шапка с навигацией, счётчиком сравнения и мобильным меню
    │   ├── SearchBar/            → WAI-ARIA combobox с debounce-автодополнением и клавиатурной навигацией
    │   ├── FiltersPanel/         → Панель фильтров + мобильный drawer + кнопка геолокации
    │   ├── OfferCard/            → Карточка предложения (цена, клиника, свежесть, источник, «История цен», «Сравнить»)
    │   ├── ClinicMap/            → Переиспользуемая карта Leaflet с маркерами, авто-fitBounds и попапами
    │   ├── PriceHistoryDialog/   → Нативный <dialog> с адаптивным SVG-графиком истории цен и выбором периода
    │   ├── CompareDock/          → Нижняя панель выбранных клиник (показывает статус N/5 и кнопку «Сравнить»)
    │   └── StateViews/           → Skeleton-загрузка, EmptyState, ErrorState с кнопкой повтора
    ├── pages/
    │   ├── SearchPage/           → Главная страница поиска и сравнения (URL-state, список/карта, пагинация)
    │   ├── MapPage/              → Полноэкранный обзор клиник на карте Leaflet с фильтрами
    │   ├── ClinicDetailPage/     → Карточка клиники (контакты, маршруты 2GIS/Google Maps, мини-карта, прайс-лист)
    │   ├── ComparePage/          → Таблица сравнения 2–5 клиник с выделением лучшей цены
    │   └── AdminPage/            → Панель оператора (токен, статистика, запуск парсера + 409, разбор unmatched)
    └── test/
        ├── setup.ts              → Настройка jest-dom и моков для jsdom (matchMedia, ResizeObserver)
        ├── SearchPage.test.tsx   → Автодополнение, фильтры, сортировка, отображение parsed_at и пустых состояний
        ├── CompareFlow.test.tsx  → Выбор клиник в CompareDock и рендер матрицы с подсветкой лучшей цены
        ├── ClinicAndHistory.test.tsx → Карточка клиники (2GIS/Google Maps) и SVG-график истории цен
        └── AdminPage.test.tsx    → Ввод токена, 401/409 обработка, resolve/ignore unmatched
```

## API Integration Contract (Consumes `search-api`)

Фронтенд обращается к `/api/v1/*` через относительный путь (в dev-режиме Vite проксирует `/api` на `http://medprice-api:8000` внутри сети `medprice-net`, в production — через reverse proxy):

| Экран | Используемые эндпоинты `search-api` |
|---|---|
| `SearchPage` (`/`) | `GET /api/v1/meta/filters`, `GET /api/v1/services/autocomplete`, `GET /api/v1/offers`, `GET /api/v1/services/{id}/price-history` |
| `MapPage` (`/map`) | `GET /api/v1/meta/filters`, `GET /api/v1/clinics?has_geo=true` |
| `ClinicDetailPage` (`/clinics/:id`) | `GET /api/v1/clinics/{id}`, `GET /api/v1/services/{id}/price-history` |
| `ComparePage` (`/compare`) | `GET /api/v1/compare?clinic_ids=...` |
| `AdminPage` (`/admin`) | `GET /api/v1/admin/{sources,scrape-runs,scrape-errors,stats,unmatched}`, `POST /api/v1/admin/scrape-runs`, `POST /api/v1/admin/unmatched/{id}/{resolve,ignore}` |

## Testing Strategy

- **Unit + Component тесты (`make test-web`)**: Vitest + React Testing Library (`jsdom`) с замоканным `fetch` (без обращения к внешним серверам):
  1. Форматирование цен KZT, относительных дат свежести и разбор ошибок `APIError`.
  2. `SearchPage`: ввод `ОАК` → подсказки автодополнения → фильтрация/сортировка → отображение `parsed_at`, ссылки источника и кнопки сравнения.
  3. `CompareFlow`: добавление 2 клиник в `CompareDock` → переход на `/compare` → подсветка `cheapest_clinic_id` и ограничение максимум 5 клиник.
  4. `ClinicDetailPage` + `PriceHistoryDialog`: отображение контактов, ссылок 2GIS/Google Maps и SVG-графика истории цен.
  5. `AdminPage`: проверка ввода `X-Admin-Token`, отображение ошибки `401`/`409`, 1-клик `resolve`/`ignore` в очереди `unmatched`.
- **Сборка и статический анализ**: `make typecheck-web` (`tsc --noEmit`), `make lint-web` (`eslint`), `make build-web` (`vite build`).
- **Живая проверка**: поднять `make api-up` + `make web-up` (`http://localhost:5173`) и проверить реальные сценарии в браузере (поиск `ОАК`, переключение на карту Leaflet, карточка клиники, таблица сравнения `КДЛ Олимп` vs `INVIVO`, график истории цен, админка, мобильная вёрстка `375px` и десктоп `1440px`, отсутствие ошибок в консоли).

## Boundaries

- **Always**:
  - Показывать дату последнего обновления цены (`parsed_at`) и ссылку на первоисточник в каждой карточке предложения и в таблице сравнения.
  - Обрабатывать все состояния: `loading` (skeletons), `empty`, `error` (с кнопкой «Повторить»), отказ геолокации.
  - Соблюдать доступность: семантические `<button>`, `<a>`, `<label>`, `<dialog>`, WAI-ARIA combobox для автодополнения, контраст ≥ 4.5:1, не полагаться только на цвет.
  - Хранить состояние фильтров поиска в URL (`searchParams`), а `X-Admin-Token` — только в `sessionStorage`.
- **Ask first**:
  - Подключение сторонних платных карт (2GIS JS SDK / Google Maps API с ключами) — в V1 используем бесплатный OpenStreetMap + Leaflet и прямые ссылки маршрута.
  - Добавление тяжёлых UI-фреймворков или глобальных стейт-менеджеров (Redux).
- **Never**:
  - Хардкодить `ADMIN_API_TOKEN` в клиентский бандл (пользователь вводит токен на экране `/admin`).
  - Выполнять клиентскую фильтрацию поверх фиктивных/хардкодных цен вместо реального `search-api`.
  - Пропускать проверку `tsc --noEmit`, `eslint`, `vitest` и `vite build`.

## Success Criteria

1. Пользователь может за 2 клика найти услугу (например, `ОАК` или `CBC`) через автодополнение, отфильтровать по городу/категории/цене/рейтингу/онлайн-записи, отсортировать по цене или расстоянию и увидеть актуальные цены клиник с датой обновления и ссылкой на источник.
2. Работают все дополнительные функции V1: интерактивная карта клиник Leaflet (`/map`), карточка клиники со ссылками маршрута 2GIS и Google Maps (`/clinics/:id`), сравнение 2–5 клиник в таблице (`/compare`) и SVG-график истории цен.
3. Работает админ-экран (`/admin`): ввод `X-Admin-Token`, статистика, запуск парсинга с обработкой `409`, 1-клик разметка/игнорирование `unmatched`.
4. Интерфейс адаптивен (`320px` – `1440px`), доступен с клавиатуры и не содержит ошибок в консоли браузера на живых данных `medprice-api`.
5. `make test-web`, `make lint-web`, `make typecheck-web` и `make build-web` проходят без ошибок.

## Out of Scope (Deferred)

- Авторизация пациентов, личный кабинет, история поисков в облаке — V2.
- Подписка на уведомления о снижении цен (email / Telegram) — V2.
- Тёмная тема и мультиязычность (KZ/EN интерфейс) — V2 (в V1 основной интерфейс на русском языке с поддержкой поиска по русским и английским терминам).

## Resolved Decisions

- **Стилизация**: используется **Tailwind CSS v4** (`@tailwindcss/vite`) с централизованными семантическими дизайн-токенами в `@theme` (`src/styles/app.css`) — быстрая сборка без лишних конфигов и чистая клиническая визуальная система.
- **Авторизация админки (`/admin`)**: явный ввод `X-Admin-Token` на форме входа `/admin`, хранение только в `sessionStorage` (секрет никогда не вшивается в клиентский бандл; в UI есть подсказка про `ADMIN_API_TOKEN` из `.env`).
- **Спецификация утверждена**: переходим к Phase 2 (Plan), Phase 3 (Tasks) и Phase 4 (Implement) для модуля `web-ui`.

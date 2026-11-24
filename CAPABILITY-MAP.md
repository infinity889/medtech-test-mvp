# Capability Map: MedServicePrice.kz — V1

Агрегатор и сравнение цен на медицинские услуги в Казахстане (Хакатон MVP).

## Модули

| Module id | Responsibility | Depends on | Spec |
|---|---|---|---|
| `ingestion` | Подключаемые адаптеры парсинга публичных источников (HTML, PDF, DOCX, Excel, JSON), соблюдение `robots.txt` и rate-limit, raw-слой хранения (аудит ≥ 90 дней), дедупликация, журнал запусков и ошибок, запуск вручную и по расписанию | — | [SPEC-ingestion.md](./SPEC-ingestion.md) |
| `normalization` | Справочник услуг (≥ 50 позиций, синонимы, категории), детерминированная нормализация (словарь + нормализация текста + RapidFuzz), конвертация валют в KZT, дедупликация предложений, очередь ручной разметки (`unmatched queue`), история изменения цен | `ingestion` | `SPEC-normalization.md` *(next)* |
| `search-api` | REST API (FastAPI): автодополнение, поиск/фильтрация/сортировка (цена, расстояние, свежесть), правило актуальности ≤ 30 дней, карточка клиники, сравнение клиник, история цен, админ-эндпоинты (запуск парсера, разметка `unmatched`) | `normalization`, `ingestion` | `SPEC-search-api.md` *(pending)* |
| `web-ui` | Адаптивный веб-интерфейс (React + Vite): поиск в стиле Aviasales, фильтры, сортировка, выдача с датой обновления, карточка клиники, карта клиник (Leaflet) с маршрутами 2GIS/Google Maps, таблица сравнения клиник, график истории цен, базовый экран админки/`unmatched` | `search-api` | `SPEC-web-ui.md` *(pending)* |

## Порядок разработки (Build Order)

```text
ingestion ──→ normalization ──→ search-api ──→ web-ui
```

## Утверждённый стек (V1)

- **Backend & Scraping**: Python (FastAPI, SQLAlchemy 2, Alembic, `httpx`, `beautifulsoup4`, `pdfplumber`, `python-docx`, `openpyxl`, `rapidfuzz`, APScheduler)
- **Database**: PostgreSQL 16 (локальный запуск через `podman`)
- **Frontend**: React + TypeScript + Vite + Leaflet (OpenStreetMap)

## Вне рамок V1 (Deferred to V2)

- Подписки и уведомления об изменении цен (email / Telegram) — кандидат на 5-й модуль `price-alerts`
- LLM/AI-assisted нормализация услуг
- Личный кабинет пациентов / авторизация пользователей
- Онлайн-запись напрямую через API клиник (в V1 — флаг наличия и переход по ссылке источника)

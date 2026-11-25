import { ArrowUpDown, ChevronLeft, ChevronRight, MapPin } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ApiClientError, fetchFiltersMeta, fetchOffers } from '../api/client';
import type {
  FiltersMetaResponse,
  OfferSearchResponse,
  OfferSortBy,
  ServiceAutocompleteItem,
  ServiceCategory,
} from '../api/types';
import { FiltersPanel } from '../components/FiltersPanel';
import type { ActiveFiltersState } from '../components/FiltersPanel';
import { OfferCard } from '../components/OfferCard';
import { SearchBar } from '../components/SearchBar';
import { CardListSkeleton, EmptyState, ErrorState } from '../components/StateViews';
import { formatPriceKzt } from '../utils/format';

interface SearchPageProps {
  onOpenPriceHistory?: (serviceId: string, canonicalName: string) => void;
}

const SORT_OPTIONS: Array<{ value: OfferSortBy; label: string }> = [
  { value: 'price_asc', label: 'Сначала дешевле' },
  { value: 'price_desc', label: 'Сначала дороже' },
  { value: 'distance_asc', label: 'Ближайшие ко мне' },
  { value: 'updated_desc', label: 'Свежие обновления' },
  { value: 'rating_desc', label: 'Высокий рейтинг' },
];

function parseCategory(val: string | null): ServiceCategory | '' {
  if (val === 'lab' || val === 'doctor' || val === 'diagnostics' || val === 'procedure') {
    return val;
  }
  return '';
}

function parseSort(val: string | null): OfferSortBy {
  if (
    val === 'price_asc' ||
    val === 'price_desc' ||
    val === 'distance_asc' ||
    val === 'updated_desc' ||
    val === 'rating_desc'
  ) {
    return val;
  }
  return 'price_asc';
}

function parseNum(val: string | null): number | null {
  if (!val) return null;
  const parsed = Number(val);
  return Number.isFinite(parsed) ? parsed : null;
}

export function SearchPage({ onOpenPriceHistory }: SearchPageProps) {
  const [searchParams, setSearchParams] = useSearchParams();
  const [meta, setMeta] = useState<FiltersMetaResponse | null>(null);
  const [offersData, setOffersData] = useState<OfferSearchResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);
  const [geoLoading, setGeoLoading] = useState(false);
  const [geoError, setGeoError] = useState<string | null>(null);

  const serviceId = searchParams.get('service_id') || '';
  const queryParam = searchParams.get('q') || '';
  const [searchInput, setSearchInput] = useState(queryParam);

  useEffect(() => {
    setSearchInput(queryParam);
  }, [queryParam]);

  const filters: ActiveFiltersState = {
    city: searchParams.get('city') || '',
    category: parseCategory(searchParams.get('category')),
    minPrice: searchParams.get('min_price') || '',
    maxPrice: searchParams.get('max_price') || '',
    minRating: searchParams.get('min_rating') || '',
    onlineBooking: searchParams.get('online_booking') === 'true',
    lat: parseNum(searchParams.get('lat')),
    lng: parseNum(searchParams.get('lng')),
  };

  const sortBy = parseSort(searchParams.get('sort_by'));
  const page = Math.max(1, Number(searchParams.get('page') || '1') || 1);

  const updateParams = useCallback(
    (updates: Record<string, string | null | undefined>, resetPage = true) => {
      setSearchParams(
        (prev) => {
          const next = new URLSearchParams(prev);
          for (const [k, v] of Object.entries(updates)) {
            if (v === null || v === undefined || v === '') {
              next.delete(k);
            } else {
              next.set(k, v);
            }
          }
          if (resetPage) {
            next.delete('page');
          }
          return next;
        },
        { replace: true },
      );
    },
    [setSearchParams],
  );

  // Load filter metadata once
  useEffect(() => {
    const controller = new AbortController();
    fetchFiltersMeta(controller.signal)
      .then(setMeta)
      .catch(() => {
        // Non-blocking: search still works without filter counts
      });
    return () => controller.abort();
  }, []);

  // Load offers whenever URL params change
  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    const minP = parseNum(filters.minPrice);
    const maxP = parseNum(filters.maxPrice);
    const minR = parseNum(filters.minRating);

    const effectiveSort: OfferSortBy =
      sortBy === 'distance_asc' && (filters.lat === null || filters.lng === null)
        ? 'price_asc'
        : sortBy;

    fetchOffers(
      {
        service_id: serviceId || undefined,
        q: serviceId ? undefined : queryParam || undefined,
        city: filters.city || undefined,
        category: filters.category || undefined,
        min_price: minP ?? undefined,
        max_price: maxP ?? undefined,
        min_rating: minR ?? undefined,
        online_booking: filters.onlineBooking ? true : undefined,
        lat: filters.lat ?? undefined,
        lng: filters.lng ?? undefined,
        sort_by: effectiveSort,
        page,
        page_size: 20,
      },
      controller.signal,
    )
      .then((res) => {
        setOffersData(res);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(
          err instanceof ApiClientError
            ? err.message
            : 'Не удалось получить предложения от сервера.',
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [
    serviceId,
    queryParam,
    filters.city,
    filters.category,
    filters.minPrice,
    filters.maxPrice,
    filters.minRating,
    filters.onlineBooking,
    filters.lat,
    filters.lng,
    sortBy,
    page,
    reloadTick,
  ]);

  function handleSelectService(item: ServiceAutocompleteItem) {
    setSearchInput(item.canonical_name);
    updateParams({
      service_id: item.service_id,
      q: item.canonical_name,
    });
  }

  function handleSubmitSearch(text: string) {
    const trimmed = text.trim();
    updateParams({
      service_id: null,
      q: trimmed || null,
    });
  }

  function handleClearSearch() {
    setSearchInput('');
    updateParams({ service_id: null, q: null });
  }

  function handleFilterChange(patch: Partial<ActiveFiltersState>) {
    const paramPatch: Record<string, string | null | undefined> = {};
    if ('city' in patch) paramPatch.city = patch.city || null;
    if ('category' in patch) paramPatch.category = patch.category || null;
    if ('minPrice' in patch) paramPatch.min_price = patch.minPrice || null;
    if ('maxPrice' in patch) paramPatch.max_price = patch.maxPrice || null;
    if ('minRating' in patch) paramPatch.min_rating = patch.minRating || null;
    if ('onlineBooking' in patch) {
      paramPatch.online_booking = patch.onlineBooking ? 'true' : null;
    }
    updateParams(paramPatch);
  }

  function handleRequestGeo() {
    if (!navigator.geolocation) {
      setGeoError('Браузер не поддерживает геолокацию.');
      return;
    }
    setGeoLoading(true);
    setGeoError(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setGeoLoading(false);
        updateParams({
          lat: pos.coords.latitude.toFixed(6),
          lng: pos.coords.longitude.toFixed(6),
          sort_by: 'distance_asc',
        });
      },
      () => {
        setGeoLoading(false);
        setGeoError('Нет доступа к геолокации. Вы можете выбрать город вручную.');
      },
      { timeout: 8000 },
    );
  }

  function handleClearGeo() {
    setGeoError(null);
    updateParams({
      lat: null,
      lng: null,
      sort_by: sortBy === 'distance_asc' ? 'price_asc' : sortBy,
    });
  }

  function handleResetAll() {
    setSearchInput('');
    setGeoError(null);
    setSearchParams({}, { replace: true });
  }

  const cheapestPrice = offersData?.summary.min_price_kzt ?? null;

  return (
    <div className="space-y-6">
      {/* Search hero */}
      <section className="rounded-2xl border border-border bg-surface p-5 sm:p-6">
        <div className="flex flex-col gap-1 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <h1 className="text-xl font-bold tracking-tight text-ink sm:text-2xl">
              Сравнение цен на медицинские услуги в Казахстане
            </h1>
            <p className="mt-1 text-sm text-ink-muted">
              Анализы, приёмы врачей и диагностика — актуальные прайс-листы клиник за последние 30
              дней.
            </p>
          </div>
          <Link
            to="/map"
            className="mt-2 inline-flex items-center gap-1.5 text-sm font-medium text-brand hover:underline sm:mt-0"
          >
            <MapPin className="h-4 w-4" aria-hidden="true" />
            Открыть карту клиник
          </Link>
        </div>

        <div className="mt-4">
          <SearchBar
            value={searchInput}
            city={filters.city || undefined}
            category={filters.category || undefined}
            onTextChange={setSearchInput}
            onSelectService={handleSelectService}
            onSubmitSearch={handleSubmitSearch}
            onClear={handleClearSearch}
          />
        </div>
      </section>

      {/* Main grid: filters + results */}
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-[270px_minmax(0,1fr)]">
        <FiltersPanel
          meta={meta}
          filters={filters}
          geoError={geoError}
          geoLoading={geoLoading}
          onChange={handleFilterChange}
          onRequestGeo={handleRequestGeo}
          onClearGeo={handleClearGeo}
          onReset={handleResetAll}
        />

        <section aria-label="Результаты поиска" className="space-y-4">
          {/* Summary + Sort bar */}
          <div className="flex flex-col gap-3 rounded-xl border border-border bg-surface px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
            <div className="text-sm text-ink-muted">
              {offersData ? (
                <>
                  Найдено{' '}
                  <strong className="font-semibold text-ink tabular-nums">
                    {offersData.pagination.total_items}
                  </strong>{' '}
                  предл.
                  {offersData.summary.min_price_kzt !== null &&
                  offersData.summary.max_price_kzt !== null ? (
                    <span className="ml-2 inline-block text-xs tabular-nums sm:text-sm">
                      · от{' '}
                      <strong className="text-savings">
                        {formatPriceKzt(offersData.summary.min_price_kzt)}
                      </strong>{' '}
                      до {formatPriceKzt(offersData.summary.max_price_kzt)}
                      {offersData.summary.avg_price_kzt !== null
                        ? ` (средняя ${formatPriceKzt(offersData.summary.avg_price_kzt)})`
                        : ''}
                    </span>
                  ) : null}
                </>
              ) : (
                'Загружаем актуальные предложения…'
              )}
            </div>

            <div className="flex items-center gap-2">
              <ArrowUpDown className="h-4 w-4 text-ink-subtle" aria-hidden="true" />
              <label htmlFor="sort-offers" className="sr-only">
                Сортировка предложений
              </label>
              <select
                id="sort-offers"
                value={sortBy}
                onChange={(e) => {
                  const nextSort = e.target.value as OfferSortBy;
                  if (nextSort === 'distance_asc' && (filters.lat === null || filters.lng === null)) {
                    handleRequestGeo();
                  } else {
                    updateParams({ sort_by: nextSort });
                  }
                }}
                className="h-9 rounded-lg border border-border-strong bg-surface px-2.5 text-sm text-ink focus:border-brand focus:outline-none"
              >
                {SORT_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {loading ? (
            <CardListSkeleton count={4} />
          ) : error ? (
            <ErrorState message={error} onRetry={() => setReloadTick((t) => t + 1)} />
          ) : !offersData || offersData.items.length === 0 ? (
            <EmptyState
              title="Предложений не найдено"
              description="Попробуйте изменить запрос, расширить ценовой диапазон или сбросить часть фильтров."
              action={
                <button
                  type="button"
                  onClick={handleResetAll}
                  className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-hover"
                >
                  Сбросить фильтры
                </button>
              }
            />
          ) : (
            <>
              <div className="space-y-3">
                {offersData.items.map((offer) => (
                  <OfferCard
                    key={offer.offer_id}
                    offer={offer}
                    isCheapest={
                      cheapestPrice !== null &&
                      offersData.pagination.total_items > 1 &&
                      offer.price_kzt <= cheapestPrice
                    }
                    onOpenPriceHistory={(id, name) => onOpenPriceHistory?.(id, name)}
                  />
                ))}
              </div>

              {offersData.pagination.total_pages > 1 ? (
                <nav
                  aria-label="Пагинация"
                  className="flex items-center justify-between rounded-xl border border-border bg-surface px-4 py-3 text-sm"
                >
                  <button
                    type="button"
                    disabled={page <= 1}
                    onClick={() => updateParams({ page: String(page - 1) }, false)}
                    className="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 font-medium text-ink transition hover:bg-surface-subtle disabled:opacity-40"
                  >
                    <ChevronLeft className="h-4 w-4" aria-hidden="true" />
                    Назад
                  </button>
                  <span className="text-ink-muted tabular-nums">
                    Страница <strong className="text-ink">{offersData.pagination.page}</strong> из{' '}
                    {offersData.pagination.total_pages}
                  </span>
                  <button
                    type="button"
                    disabled={page >= offersData.pagination.total_pages}
                    onClick={() => updateParams({ page: String(page + 1) }, false)}
                    className="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 font-medium text-ink transition hover:bg-surface-subtle disabled:opacity-40"
                  >
                    Вперёд
                    <ChevronRight className="h-4 w-4" aria-hidden="true" />
                  </button>
                </nav>
              ) : null}
            </>
          )}
        </section>
      </div>
    </div>
  );
}

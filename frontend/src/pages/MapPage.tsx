import { ExternalLink, MapPin, Scale, Search, Star } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ApiClientError, fetchClinics, fetchFiltersMeta } from '../api/client';
import type { ClinicListItem, FiltersMetaResponse } from '../api/types';
import { ClinicMap } from '../components/ClinicMap';
import { CardListSkeleton, EmptyState, ErrorState } from '../components/StateViews';
import { useCompare } from '../context/CompareContext';
import { formatPriceKzt } from '../utils/format';

export function MapPage() {
  const [meta, setMeta] = useState<FiltersMetaResponse | null>(null);
  const [clinics, setClinics] = useState<ClinicListItem[]>([]);
  const [city, setCity] = useState('');
  const [query, setQuery] = useState('');
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadTick, setReloadTick] = useState(0);

  const { isSelected, toggleClinic, clinics: compared, maxClinics } = useCompare();

  useEffect(() => {
    const controller = new AbortController();
    fetchFiltersMeta(controller.signal)
      .then(setMeta)
      .catch(() => {});
    return () => controller.abort();
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    fetchClinics(
      {
        city: city || undefined,
        q: query.trim() || undefined,
        has_geo: true,
        page_size: 200,
      },
      controller.signal,
    )
      .then((res) => {
        setClinics(res.items);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof ApiClientError ? err.message : 'Не удалось загрузить карту клиник.');
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [city, query, reloadTick]);

  return (
    <div className="space-y-5">
      <section className="flex flex-col gap-4 rounded-2xl border border-border bg-surface p-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-xl font-bold tracking-tight text-ink sm:text-2xl">
            Карта клиник и лабораторий
          </h1>
          <p className="mt-1 text-sm text-ink-muted">
            Нажмите на маркер или клинику в списке, чтобы увидеть цены и построить маршрут в 2GIS
            или Google Maps.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="relative">
            <Search
              className="pointer-events-none absolute top-2.5 left-3 h-4 w-4 text-ink-subtle"
              aria-hidden="true"
            />
            <input
              type="search"
              aria-label="Поиск клиники по названию или адресу"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Название или адрес…"
              className="h-9 w-52 rounded-lg border border-border-strong bg-surface pr-3 pl-9 text-sm text-ink focus:border-brand focus:outline-none"
            />
          </div>

          <label htmlFor="map-city" className="sr-only">
            Город
          </label>
          <select
            id="map-city"
            value={city}
            onChange={(e) => {
              setCity(e.target.value);
              setSelectedId(null);
            }}
            className="h-9 rounded-lg border border-border-strong bg-surface px-3 text-sm text-ink focus:border-brand focus:outline-none"
          >
            <option value="">Все города</option>
            {(meta?.cities ?? []).map((c) => (
              <option key={c.name} value={c.name}>
                {c.name} ({c.clinics_count})
              </option>
            ))}
          </select>
        </div>
      </section>

      {error ? (
        <ErrorState message={error} onRetry={() => setReloadTick((t) => t + 1)} />
      ) : (
        <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_380px]">
          <ClinicMap
            clinics={clinics}
            selectedClinicId={selectedId}
            onSelectClinic={setSelectedId}
            heightClassName="h-[460px] lg:h-[620px]"
          />

          <aside
            aria-label="Список клиник на карте"
            className="flex max-h-[620px] flex-col rounded-xl border border-border bg-surface"
          >
            <div className="border-b border-border px-4 py-3 text-sm font-semibold text-ink">
              Клиник с координатами: <span className="tabular-nums">{clinics.length}</span>
            </div>
            <div className="flex-1 divide-y divide-border overflow-y-auto">
              {loading ? (
                <div className="p-4">
                  <CardListSkeleton count={3} />
                </div>
              ) : clinics.length === 0 ? (
                <div className="p-4">
                  <EmptyState
                    title="Клиники не найдены"
                    description="Попробуйте выбрать другой город или очистить поиск."
                  />
                </div>
              ) : (
                clinics.map((clinic) => {
                  const active = clinic.id === selectedId;
                  const inCompare = isSelected(clinic.id);
                  const compareFull = !inCompare && compared.length >= maxClinics;
                  return (
                    <div
                      key={clinic.id}
                      className={`p-4 transition ${
                        active ? 'bg-brand-soft/70' : 'hover:bg-surface-subtle/60'
                      }`}
                    >
                      <div className="flex items-start justify-between gap-2">
                        <button
                          type="button"
                          onClick={() => setSelectedId(clinic.id)}
                          className="text-left text-sm font-semibold text-ink hover:text-brand"
                        >
                          {clinic.clinic_name}
                        </button>
                        {clinic.rating !== null ? (
                          <span className="inline-flex shrink-0 items-center gap-0.5 text-xs font-medium text-ink tabular-nums">
                            <Star
                              className="h-3.5 w-3.5 fill-amber-400 text-amber-500"
                              aria-hidden="true"
                            />
                            {clinic.rating.toFixed(1)}
                          </span>
                        ) : null}
                      </div>

                      <p className="mt-1 flex items-center gap-1 text-xs text-ink-muted">
                        <MapPin className="h-3.5 w-3.5 shrink-0 text-ink-subtle" aria-hidden="true" />
                        {clinic.city}
                        {clinic.address ? `, ${clinic.address}` : ''}
                      </p>

                      <div className="mt-2 flex items-center justify-between text-xs tabular-nums">
                        <span className="text-ink-subtle">Услуг: {clinic.offers_count}</span>
                        {clinic.min_price_kzt !== null ? (
                          <span className="font-semibold text-savings">
                            от {formatPriceKzt(clinic.min_price_kzt)}
                          </span>
                        ) : null}
                      </div>

                      <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
                        <Link
                          to={`/clinics/${clinic.id}`}
                          className="rounded-md bg-brand px-2.5 py-1 font-medium text-white hover:bg-brand-hover"
                        >
                          Прайс-лист
                        </Link>
                        <a
                          href={clinic.route_2gis_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 font-medium text-ink-muted hover:text-brand"
                        >
                          2GIS <ExternalLink className="h-3 w-3" aria-hidden="true" />
                        </a>
                        <a
                          href={clinic.route_google_maps_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 font-medium text-ink-muted hover:text-brand"
                        >
                          Google <ExternalLink className="h-3 w-3" aria-hidden="true" />
                        </a>
                        <button
                          type="button"
                          disabled={compareFull}
                          onClick={() =>
                            toggleClinic({
                              id: clinic.id,
                              clinic_name: clinic.clinic_name,
                              city: clinic.city,
                            })
                          }
                          className={`ml-auto inline-flex items-center gap-1 rounded-md border px-2 py-1 font-medium ${
                            inCompare
                              ? 'border-brand bg-brand-soft text-brand'
                              : 'border-border text-ink-muted hover:border-brand disabled:opacity-50'
                          }`}
                        >
                          <Scale className="h-3 w-3" aria-hidden="true" />
                          {inCompare ? 'Выбрано' : 'Сравнить'}
                        </button>
                      </div>
                    </div>
                  );
                })
              )}
            </div>
          </aside>
        </div>
      )}
    </div>
  );
}

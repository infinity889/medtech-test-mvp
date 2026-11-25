import { LocateFixed, RotateCcw, SlidersHorizontal, X } from 'lucide-react';
import { useState } from 'react';
import type { FiltersMetaResponse, ServiceCategory } from '../api/types';

export interface ActiveFiltersState {
  city: string;
  category: ServiceCategory | '';
  minPrice: string;
  maxPrice: string;
  minRating: string;
  onlineBooking: boolean;
  lat: number | null;
  lng: number | null;
}

interface FiltersPanelProps {
  meta: FiltersMetaResponse | null;
  filters: ActiveFiltersState;
  geoError: string | null;
  geoLoading: boolean;
  onChange: (patch: Partial<ActiveFiltersState>) => void;
  onRequestGeo: () => void;
  onClearGeo: () => void;
  onReset: () => void;
}

export function FiltersPanel({
  meta,
  filters,
  geoError,
  geoLoading,
  onChange,
  onRequestGeo,
  onClearGeo,
  onReset,
}: FiltersPanelProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  const hasActiveFilters = Boolean(
    filters.city ||
      filters.category ||
      filters.minPrice ||
      filters.maxPrice ||
      filters.minRating ||
      filters.onlineBooking ||
      filters.lat !== null,
  );

  const content = (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ink">Фильтры</h2>
        {hasActiveFilters ? (
          <button
            type="button"
            onClick={onReset}
            className="inline-flex items-center gap-1 text-xs font-medium text-brand hover:underline"
          >
            <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />
            Сбросить
          </button>
        ) : null}
      </div>

      {/* City */}
      <div>
        <label htmlFor="filter-city" className="block text-xs font-medium text-ink-muted">
          Город
        </label>
        <select
          id="filter-city"
          value={filters.city}
          onChange={(e) => onChange({ city: e.target.value })}
          className="mt-1.5 h-10 w-full rounded-lg border border-border-strong bg-surface px-3 text-sm text-ink focus:border-brand focus:outline-none"
        >
          <option value="">Все города Казахстана</option>
          {(meta?.cities ?? []).map((c) => (
            <option key={c.name} value={c.name}>
              {c.name} ({c.offers_count})
            </option>
          ))}
        </select>
      </div>

      {/* Category */}
      <fieldset>
        <legend className="text-xs font-medium text-ink-muted">Категория</legend>
        <div className="mt-1.5 flex flex-wrap gap-1.5">
          <button
            type="button"
            onClick={() => onChange({ category: '' })}
            className={`rounded-lg border px-2.5 py-1.5 text-xs font-medium transition ${
              filters.category === ''
                ? 'border-brand bg-brand-soft text-brand'
                : 'border-border bg-surface text-ink-muted hover:bg-surface-subtle'
            }`}
          >
            Все
          </button>
          {(meta?.categories ?? []).map((cat) => (
            <button
              key={cat.code}
              type="button"
              onClick={() => onChange({ category: cat.code })}
              className={`rounded-lg border px-2.5 py-1.5 text-xs font-medium transition ${
                filters.category === cat.code
                  ? 'border-brand bg-brand-soft text-brand'
                  : 'border-border bg-surface text-ink-muted hover:bg-surface-subtle'
              }`}
            >
              {cat.label_ru} ({cat.offers_count})
            </button>
          ))}
        </div>
      </fieldset>

      {/* Price range */}
      <fieldset>
        <legend className="text-xs font-medium text-ink-muted">Цена, ₸</legend>
        <div className="mt-1.5 grid grid-cols-2 gap-2">
          <input
            type="number"
            min={0}
            inputMode="numeric"
            aria-label="Минимальная цена в тенге"
            placeholder={meta?.price_min_kzt ? `от ${meta.price_min_kzt}` : 'от'}
            value={filters.minPrice}
            onChange={(e) => onChange({ minPrice: e.target.value })}
            className="h-10 w-full rounded-lg border border-border-strong bg-surface px-3 text-sm tabular-nums text-ink focus:border-brand focus:outline-none"
          />
          <input
            type="number"
            min={0}
            inputMode="numeric"
            aria-label="Максимальная цена в тенге"
            placeholder={meta?.price_max_kzt ? `до ${meta.price_max_kzt}` : 'до'}
            value={filters.maxPrice}
            onChange={(e) => onChange({ maxPrice: e.target.value })}
            className="h-10 w-full rounded-lg border border-border-strong bg-surface px-3 text-sm tabular-nums text-ink focus:border-brand focus:outline-none"
          />
        </div>
      </fieldset>

      {/* Rating */}
      <div>
        <label htmlFor="filter-rating" className="block text-xs font-medium text-ink-muted">
          Рейтинг клиники
        </label>
        <select
          id="filter-rating"
          value={filters.minRating}
          onChange={(e) => onChange({ minRating: e.target.value })}
          className="mt-1.5 h-10 w-full rounded-lg border border-border-strong bg-surface px-3 text-sm text-ink focus:border-brand focus:outline-none"
        >
          <option value="">Любой рейтинг</option>
          <option value="4.5">От 4.5 ★</option>
          <option value="4.0">От 4.0 ★</option>
          <option value="3.5">От 3.5 ★</option>
        </select>
      </div>

      {/* Online booking */}
      <label className="flex cursor-pointer items-center gap-2.5 rounded-lg border border-border bg-surface-subtle/60 px-3 py-2.5 text-sm text-ink">
        <input
          type="checkbox"
          checked={filters.onlineBooking}
          onChange={(e) => onChange({ onlineBooking: e.target.checked })}
          className="h-4 w-4 rounded border-border-strong accent-brand"
        />
        <span>Есть онлайн-запись</span>
      </label>

      {/* Geolocation */}
      <div className="space-y-1.5 border-t border-border pt-4">
        <p className="text-xs font-medium text-ink-muted">Геолокация</p>
        {filters.lat !== null && filters.lng !== null ? (
          <div className="flex items-center justify-between rounded-lg border border-brand-border bg-brand-soft px-3 py-2 text-xs text-brand">
            <span className="font-medium">Координаты определены</span>
            <button
              type="button"
              onClick={onClearGeo}
              aria-label="Сбросить геолокацию"
              className="rounded p-0.5 hover:bg-brand/10"
            >
              <X className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          </div>
        ) : (
          <button
            type="button"
            disabled={geoLoading}
            onClick={onRequestGeo}
            className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-border-strong bg-surface px-3 py-2 text-xs font-medium text-ink transition hover:border-brand hover:bg-brand-soft hover:text-brand disabled:opacity-60"
          >
            <LocateFixed className="h-4 w-4" aria-hidden="true" />
            {geoLoading ? 'Определяем…' : 'Рядом со мной'}
          </button>
        )}
        {geoError ? <p className="text-xs text-danger">{geoError}</p> : null}
      </div>
    </div>
  );

  return (
    <>
      <div className="lg:hidden">
        <button
          type="button"
          onClick={() => setMobileOpen((v) => !v)}
          aria-expanded={mobileOpen}
          className="inline-flex w-full items-center justify-between rounded-xl border border-border-strong bg-surface px-4 py-3 text-sm font-medium text-ink"
        >
          <span className="inline-flex items-center gap-2">
            <SlidersHorizontal className="h-4 w-4 text-brand" aria-hidden="true" />
            Фильтры и город
          </span>
          <span className="text-xs text-brand">{mobileOpen ? 'Скрыть' : 'Открыть'}</span>
        </button>
        {mobileOpen ? (
          <div className="mt-2 rounded-xl border border-border bg-surface p-4">{content}</div>
        ) : null}
      </div>

      <aside
        aria-label="Панель фильтров"
        className="hidden h-fit rounded-xl border border-border bg-surface p-5 lg:sticky lg:top-20 lg:block"
      >
        {content}
      </aside>
    </>
  );
}

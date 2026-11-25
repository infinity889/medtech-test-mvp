import {
  CalendarCheck,
  Clock,
  ExternalLink,
  MapPin,
  Navigation,
  Scale,
  Star,
  TrendingUp,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import type { OfferSearchItem } from '../api/types';
import { useCompare } from '../context/CompareContext';
import {
  categoryLabelRu,
  formatDistanceKm,
  formatDurationDays,
  formatExactDate,
  formatFreshness,
  formatPriceKzt,
} from '../utils/format';

interface OfferCardProps {
  offer: OfferSearchItem;
  isCheapest: boolean;
  onOpenPriceHistory: (serviceId: string, canonicalName: string) => void;
}

export function OfferCard({ offer, isCheapest, onOpenPriceHistory }: OfferCardProps) {
  const { isSelected, toggleClinic, clinics, maxClinics } = useCompare();
  const selected = isSelected(offer.clinic.id);
  const compareFull = !selected && clinics.length >= maxClinics;
  const distanceLabel = formatDistanceKm(offer.distance_km);

  return (
    <article className="rounded-xl border border-border bg-surface p-4 transition hover:border-border-strong sm:p-5">
      <div className="flex flex-col justify-between gap-4 sm:flex-row">
        {/* Left: Service & Clinic Info */}
        <div className="min-w-0 flex-1 space-y-2">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-md bg-surface-subtle px-2 py-0.5 text-xs font-medium text-ink-muted">
              {categoryLabelRu(offer.category)}
            </span>
            {isCheapest ? (
              <span className="inline-flex items-center gap-1 rounded-md bg-savings-bg px-2 py-0.5 text-xs font-semibold text-savings">
                ★ Лучшая цена
              </span>
            ) : null}
            {offer.clinic.has_online_booking ? (
              <span className="inline-flex items-center gap-1 rounded-md bg-brand-soft px-2 py-0.5 text-xs font-medium text-brand">
                <CalendarCheck className="h-3.5 w-3.5" aria-hidden="true" />
                Онлайн-запись
              </span>
            ) : null}
          </div>

          <div>
            <h3 className="text-base font-semibold leading-snug text-ink">
              {offer.canonical_name}
            </h3>
            {offer.service_name_raw.toLowerCase() !== offer.canonical_name.toLowerCase() ? (
              <p className="mt-0.5 line-clamp-2 text-xs text-ink-subtle">
                В прайсе клиники: {offer.service_name_raw}
              </p>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-sm">
            <Link
              to={`/clinics/${offer.clinic.id}`}
              className="font-semibold text-brand hover:underline"
            >
              {offer.clinic.clinic_name}
            </Link>
            {offer.clinic.rating !== null ? (
              <span className="inline-flex items-center gap-1 text-xs font-medium text-ink tabular-nums">
                <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-500" aria-hidden="true" />
                {offer.clinic.rating.toFixed(1)}
              </span>
            ) : null}
            <span className="inline-flex items-center gap-1 text-xs text-ink-muted">
              <MapPin className="h-3.5 w-3.5 shrink-0 text-ink-subtle" aria-hidden="true" />
              {offer.clinic.city}
              {offer.clinic.address ? `, ${offer.clinic.address}` : ''}
            </span>
            {distanceLabel ? (
              <span className="inline-flex items-center gap-1 rounded bg-surface-subtle px-1.5 py-0.5 text-xs font-medium text-ink tabular-nums">
                <Navigation className="h-3 w-3 text-brand" aria-hidden="true" />
                {distanceLabel}
              </span>
            ) : null}
          </div>

          <div className="flex flex-wrap items-center gap-x-4 gap-y-1 pt-1 text-xs text-ink-subtle">
            <span className="inline-flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" aria-hidden="true" />
              Срок: {formatDurationDays(offer.duration_days)}
            </span>
            <span title={`Точная дата парсинга: ${formatExactDate(offer.parsed_at)}`}>
              Обновлено {formatFreshness(offer.parsed_at)}
            </span>
            <a
              href={offer.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 font-medium text-ink-muted hover:text-brand hover:underline"
            >
              Источник ({offer.source_id})
              <ExternalLink className="h-3 w-3" aria-hidden="true" />
            </a>
          </div>
        </div>

        {/* Right: Price & Actions */}
        <div className="flex shrink-0 flex-row items-center justify-between gap-3 border-t border-border pt-3 sm:w-48 sm:flex-col sm:items-end sm:justify-between sm:border-t-0 sm:border-l sm:pt-0 sm:pl-4">
          <div className="sm:text-right">
            <p className="text-2xl font-bold tracking-tight text-ink tabular-nums">
              {formatPriceKzt(offer.price_kzt)}
            </p>
            <Link
              to={`/clinics/${offer.clinic.id}`}
              className="mt-0.5 inline-block text-xs font-medium text-brand hover:underline"
            >
              Карточка клиники →
            </Link>
          </div>

          <div className="flex flex-wrap justify-end gap-1.5">
            <button
              type="button"
              onClick={() => onOpenPriceHistory(offer.service_id, offer.canonical_name)}
              className="inline-flex items-center gap-1 rounded-lg border border-border px-2.5 py-1.5 text-xs font-medium text-ink-muted transition hover:border-brand hover:bg-brand-soft hover:text-brand"
            >
              <TrendingUp className="h-3.5 w-3.5" aria-hidden="true" />
              История цен
            </button>
            <button
              type="button"
              disabled={compareFull}
              onClick={() =>
                toggleClinic({
                  id: offer.clinic.id,
                  clinic_name: offer.clinic.clinic_name,
                  city: offer.clinic.city,
                })
              }
              className={`inline-flex items-center gap-1 rounded-lg border px-2.5 py-1.5 text-xs font-medium transition ${
                selected
                  ? 'border-brand bg-brand text-white hover:bg-brand-hover'
                  : 'border-border text-ink-muted hover:border-brand hover:bg-brand-soft hover:text-brand disabled:opacity-50'
              }`}
            >
              <Scale className="h-3.5 w-3.5" aria-hidden="true" />
              {selected ? 'В сравнении' : 'В сравнение'}
            </button>
          </div>
        </div>
      </div>
    </article>
  );
}

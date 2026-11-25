import {
  ArrowLeft,
  CalendarCheck,
  Clock,
  ExternalLink,
  Globe,
  MapPin,
  Phone,
  Scale,
  Search,
  Star,
  TrendingUp,
} from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ApiClientError, fetchClinicDetail } from '../api/client';
import type { ClinicDetail, ServiceCategory } from '../api/types';
import { ClinicMap } from '../components/ClinicMap';
import { CardListSkeleton, EmptyState, ErrorState } from '../components/StateViews';
import { useCompare } from '../context/CompareContext';
import {
  categoryLabelRu,
  formatDurationDays,
  formatExactDate,
  formatFreshness,
  formatPriceKzt,
} from '../utils/format';

interface ClinicDetailPageProps {
  onOpenPriceHistory?: (serviceId: string, canonicalName: string, clinicId?: string) => void;
}

export function ClinicDetailPage({ onOpenPriceHistory }: ClinicDetailPageProps) {
  const { clinicId } = useParams<{ clinicId: string }>();
  const [clinic, setClinic] = useState<ClinicDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [offerQuery, setOfferQuery] = useState('');
  const [offerCategory, setOfferCategory] = useState<ServiceCategory | ''>('');

  const { isSelected, toggleClinic, clinics: compared, maxClinics } = useCompare();

  useEffect(() => {
    if (!clinicId) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    fetchClinicDetail(clinicId, controller.signal)
      .then(setClinic)
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(
          err instanceof ApiClientError
            ? err.message
            : 'Не удалось загрузить карточку клиники.',
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [clinicId]);

  const filteredOffers = useMemo(() => {
    if (!clinic) return [];
    const norm = offerQuery.trim().toLowerCase();
    return clinic.offers.filter((offer) => {
      if (offerCategory && offer.category !== offerCategory) return false;
      if (!norm) return true;
      return (
        offer.canonical_name.toLowerCase().includes(norm) ||
        offer.service_name_raw.toLowerCase().includes(norm)
      );
    });
  }, [clinic, offerQuery, offerCategory]);

  if (loading) {
    return <CardListSkeleton count={3} />;
  }

  if (error || !clinic) {
    return (
      <div className="space-y-4">
        <Link to="/" className="inline-flex items-center gap-1.5 text-sm font-medium text-brand">
          <ArrowLeft className="h-4 w-4" aria-hidden="true" />
          Назад к поиску
        </Link>
        <ErrorState message={error || 'Клиника не найдена'} />
      </div>
    );
  }

  const inCompare = isSelected(clinic.id);
  const compareFull = !inCompare && compared.length >= maxClinics;

  return (
    <div className="space-y-6">
      <Link
        to="/"
        className="inline-flex items-center gap-1.5 text-sm font-medium text-brand hover:underline"
      >
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        Вернуться к поиску услуг
      </Link>

      {/* Clinic header + mini-map */}
      <section className="grid grid-cols-1 gap-6 rounded-2xl border border-border bg-surface p-5 lg:grid-cols-[minmax(0,1fr)_360px] lg:p-6">
        <div className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="rounded-md bg-surface-subtle px-2.5 py-0.5 text-xs font-medium text-ink-muted">
              Источник: {clinic.source_id}
            </span>
            {clinic.has_online_booking ? (
              <span className="inline-flex items-center gap-1 rounded-md bg-brand-soft px-2.5 py-0.5 text-xs font-medium text-brand">
                <CalendarCheck className="h-3.5 w-3.5" aria-hidden="true" />
                Есть онлайн-запись
              </span>
            ) : null}
            {clinic.rating !== null ? (
              <span className="inline-flex items-center gap-1 rounded-md bg-warning-bg px-2 py-0.5 text-xs font-semibold text-warning tabular-nums">
                <Star className="h-3.5 w-3.5 fill-amber-400 text-amber-500" aria-hidden="true" />
                {clinic.rating.toFixed(1)}
              </span>
            ) : null}
          </div>

          <h1 className="text-2xl font-bold tracking-tight text-ink">{clinic.clinic_name}</h1>

          <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
            <div className="flex items-start gap-2 text-ink-muted">
              <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-brand" aria-hidden="true" />
              <div>
                <dt className="text-xs text-ink-subtle">Адрес</dt>
                <dd className="font-medium text-ink">
                  {clinic.city}
                  {clinic.address ? `, ${clinic.address}` : ' (адрес уточняйте на сайте)'}
                </dd>
              </div>
            </div>

            {clinic.phone ? (
              <div className="flex items-start gap-2 text-ink-muted">
                <Phone className="mt-0.5 h-4 w-4 shrink-0 text-brand" aria-hidden="true" />
                <div>
                  <dt className="text-xs text-ink-subtle">Телефон</dt>
                  <dd>
                    <a
                      href={`tel:${clinic.phone.replace(/[^+\d]/g, '')}`}
                      className="font-medium text-ink hover:text-brand hover:underline"
                    >
                      {clinic.phone}
                    </a>
                  </dd>
                </div>
              </div>
            ) : null}

            {clinic.working_hours ? (
              <div className="flex items-start gap-2 text-ink-muted">
                <Clock className="mt-0.5 h-4 w-4 shrink-0 text-brand" aria-hidden="true" />
                <div>
                  <dt className="text-xs text-ink-subtle">График работы</dt>
                  <dd className="font-medium text-ink">{clinic.working_hours}</dd>
                </div>
              </div>
            ) : null}

            {clinic.website_url ? (
              <div className="flex items-start gap-2 text-ink-muted">
                <Globe className="mt-0.5 h-4 w-4 shrink-0 text-brand" aria-hidden="true" />
                <div>
                  <dt className="text-xs text-ink-subtle">Официальный сайт</dt>
                  <dd>
                    <a
                      href={clinic.website_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 font-medium text-brand hover:underline"
                    >
                      Перейти на сайт <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                    </a>
                  </dd>
                </div>
              </div>
            ) : null}
          </dl>

          <div className="flex flex-wrap items-center gap-2.5 pt-2">
            <a
              href={clinic.route_2gis_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-hover"
            >
              Маршрут в 2GIS
              <ExternalLink className="h-4 w-4" aria-hidden="true" />
            </a>
            <a
              href={clinic.route_google_maps_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 rounded-lg border border-border-strong bg-surface px-4 py-2 text-sm font-medium text-ink transition hover:border-brand hover:text-brand"
            >
              Google Maps
              <ExternalLink className="h-4 w-4" aria-hidden="true" />
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
              className={`inline-flex items-center gap-1.5 rounded-lg border px-4 py-2 text-sm font-medium transition ${
                inCompare
                  ? 'border-brand bg-brand-soft text-brand'
                  : 'border-border-strong bg-surface text-ink hover:border-brand hover:text-brand disabled:opacity-50'
              }`}
            >
              <Scale className="h-4 w-4" aria-hidden="true" />
              {inCompare ? 'Убрать из сравнения' : 'Добавить к сравнению'}
            </button>
          </div>
        </div>

        {clinic.latitude !== null && clinic.longitude !== null ? (
          <ClinicMap clinics={[clinic]} selectedClinicId={clinic.id} heightClassName="h-64" />
        ) : (
          <div className="flex h-64 flex-col items-center justify-center rounded-xl border border-border bg-surface-subtle p-4 text-center text-sm text-ink-muted">
            <MapPin className="h-7 w-7 text-ink-subtle" aria-hidden="true" />
            <p className="mt-2">Точные GPS-координаты не указаны — откройте адрес в 2GIS или Google Maps.</p>
          </div>
        )}
      </section>

      {/* Clinic active services table */}
      <section className="rounded-2xl border border-border bg-surface p-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h2 id="clinic-offers-heading" className="text-lg font-semibold text-ink">
              Актуальный прайс-лист ({filteredOffers.length})
            </h2>
            <p className="text-xs text-ink-subtle">
              Показываются только услуги, обновлённые не более 30 дней назад.
            </p>
          </div>

          <div className="flex flex-wrap gap-2">
            <div className="relative">
              <Search
                className="pointer-events-none absolute top-2.5 left-3 h-4 w-4 text-ink-subtle"
                aria-hidden="true"
              />
              <input
                type="search"
                aria-label="Фильтр услуг клиники"
                value={offerQuery}
                onChange={(e) => setOfferQuery(e.target.value)}
                placeholder="Фильтр по услуге…"
                className="h-9 w-52 rounded-lg border border-border-strong bg-surface pr-3 pl-9 text-sm text-ink focus:border-brand focus:outline-none"
              />
            </div>

            <select
              aria-label="Категория услуг клиники"
              value={offerCategory}
              onChange={(e) => setOfferCategory(e.target.value as ServiceCategory | '')}
              className="h-9 rounded-lg border border-border-strong bg-surface px-3 text-sm text-ink focus:border-brand focus:outline-none"
            >
              <option value="">Все категории</option>
              <option value="lab">Анализы</option>
              <option value="doctor">Приём врачей</option>
              <option value="diagnostics">Диагностика</option>
              <option value="procedure">Процедуры</option>
            </select>
          </div>
        </div>

        {filteredOffers.length === 0 ? (
          <div className="mt-4">
            <EmptyState
              title="Услуги не найдены"
              description="В этой клинике нет услуг по заданному фильтру."
            />
          </div>
        ) : (
          <div
            tabIndex={0}
            role="region"
            aria-labelledby="clinic-offers-heading"
            className="mt-4 overflow-x-auto rounded-xl border border-border"
          >
            <table className="w-full min-w-[640px] border-separate border-spacing-0 text-left text-sm">
              <thead className="sticky top-0 z-10 bg-surface-subtle text-xs font-semibold text-ink-muted">
                <tr>
                  <th className="border-b border-border px-4 py-3">Услуга</th>
                  <th className="border-b border-border px-4 py-3">Категория</th>
                  <th className="border-b border-border px-4 py-3">Срок</th>
                  <th className="border-b border-border px-4 py-3">Обновлено</th>
                  <th className="border-b border-border px-4 py-3 text-right">Цена</th>
                  <th className="border-b border-border px-4 py-3 text-right">Действия</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredOffers.map((offer) => (
                  <tr key={offer.offer_id} className="bg-surface hover:bg-canvas/60">
                    <th scope="row" className="px-4 py-3 font-medium text-ink">
                      <p>{offer.canonical_name}</p>
                      {offer.service_name_raw.toLowerCase() !==
                      offer.canonical_name.toLowerCase() ? (
                        <p className="mt-0.5 text-xs font-normal text-ink-subtle">
                          {offer.service_name_raw}
                        </p>
                      ) : null}
                    </th>
                    <td className="px-4 py-3 text-xs text-ink-muted">
                      {categoryLabelRu(offer.category)}
                    </td>
                    <td className="px-4 py-3 text-xs text-ink-muted">
                      {formatDurationDays(offer.duration_days)}
                    </td>
                    <td
                      className="px-4 py-3 text-xs text-ink-subtle"
                      title={formatExactDate(offer.parsed_at)}
                    >
                      {formatFreshness(offer.parsed_at)}
                    </td>
                    <td className="px-4 py-3 text-right font-bold text-ink tabular-nums">
                      {formatPriceKzt(offer.price_kzt)}
                    </td>
                    <td className="px-4 py-3 text-right">
                      <div className="inline-flex items-center gap-2">
                        <button
                          type="button"
                          onClick={() =>
                            onOpenPriceHistory?.(offer.service_id, offer.canonical_name)
                          }
                          className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs font-medium text-ink-muted hover:border-brand hover:text-brand"
                        >
                          <TrendingUp className="h-3.5 w-3.5" aria-hidden="true" />
                          История цен
                        </button>
                        <a
                          href={offer.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          aria-label={`Источник цены для ${offer.canonical_name}`}
                          className="rounded-md p-1.5 text-ink-subtle hover:bg-surface-subtle hover:text-brand"
                        >
                          <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                        </a>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

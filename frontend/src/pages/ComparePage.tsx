import { Check, ExternalLink, MapPin, Scale, Star, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ApiClientError, fetchCompareMatrix } from '../api/client';
import type { CompareMatrixResponse, ServiceCategory } from '../api/types';
import { CardListSkeleton, EmptyState, ErrorState } from '../components/StateViews';
import { useCompare } from '../context/CompareContext';
import {
  categoryLabelRu,
  formatDurationDays,
  formatFreshness,
  formatPriceKzt,
} from '../utils/format';

export function ComparePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const { clinics: storedClinics, removeClinic } = useCompare();

  const urlClinicIds = useMemo(() => {
    const raw = searchParams.get('clinic_ids');
    if (!raw) return [];
    return raw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean);
  }, [searchParams]);

  const activeClinicIds = useMemo(
    () => (urlClinicIds.length >= 2 ? urlClinicIds : storedClinics.map((c) => c.id)),
    [urlClinicIds, storedClinics],
  );
  const clinicIdsKey = activeClinicIds.join(',');

  const [category, setCategory] = useState<ServiceCategory | ''>('');
  const [onlyShared, setOnlyShared] = useState(false);
  const [data, setData] = useState<CompareMatrixResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (activeClinicIds.length < 2 || activeClinicIds.length > 5) {
      setData(null);
      return;
    }
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    fetchCompareMatrix(
      {
        clinicIds: activeClinicIds,
        category: category || undefined,
      },
      controller.signal,
    )
      .then(setData)
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(
          err instanceof ApiClientError
            ? err.message
            : 'Не удалось построить таблицу сравнения клиник.',
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [clinicIdsKey, category]);

  function handleRemoveClinic(clinicId: string) {
    removeClinic(clinicId);
    if (urlClinicIds.length > 0) {
      const remaining = urlClinicIds.filter((id) => id !== clinicId);
      setSearchParams(
        remaining.length > 0 ? { clinic_ids: remaining.join(',') } : {},
        { replace: true },
      );
    }
  }

  const visibleRows = useMemo(() => {
    if (!data) return [];
    if (!onlyShared) return data.rows;
    return data.rows.filter((row) => {
      const nonNullCount = Object.values(row.cells).filter(Boolean).length;
      return nonNullCount >= 2;
    });
  }, [data, onlyShared]);

  if (activeClinicIds.length < 2) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold tracking-tight text-ink">Сравнение клиник</h1>
        <EmptyState
          title="Выберите от 2 до 5 клиник для сравнения"
          description="Нажимайте «В сравнение» на карточках услуг в поиске или на карте клиник — они появятся на нижней панели, и вы сможете сравнить прайс-листы в одной таблице."
          action={
            <div className="flex flex-wrap justify-center gap-2">
              <Link
                to="/"
                className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white hover:bg-brand-hover"
              >
                Перейти к поиску
              </Link>
              <Link
                to="/map"
                className="rounded-lg border border-border-strong bg-surface px-4 py-2 text-sm font-medium text-ink hover:border-brand hover:text-brand"
              >
                Открыть карту клиник
              </Link>
            </div>
          }
        />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <section className="flex flex-col gap-4 rounded-2xl border border-border bg-surface p-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-brand">
            <Scale className="h-4 w-4" aria-hidden="true" />
            Сравнительная матрица
          </div>
          <h1 id="compare-table-heading" className="mt-1 text-xl font-bold text-ink sm:text-2xl">
            Сравнение цен в {activeClinicIds.length} клиниках
          </h1>
          <p className="mt-1 text-sm text-ink-muted">
            В каждой строке отмечена минимальная цена среди выбранных клиник (услуги актуальностью ≤
            30 дней).
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <label className="inline-flex cursor-pointer items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              checked={onlyShared}
              onChange={(e) => setOnlyShared(e.target.checked)}
              className="h-4 w-4 rounded border-border-strong accent-brand"
            />
            Только общие услуги
          </label>

          <select
            aria-label="Категория сравнения"
            value={category}
            onChange={(e) => setCategory(e.target.value as ServiceCategory | '')}
            className="h-9 rounded-lg border border-border-strong bg-surface px-3 text-sm text-ink focus:border-brand focus:outline-none"
          >
            <option value="">Все категории</option>
            <option value="lab">Анализы</option>
            <option value="doctor">Приём врачей</option>
            <option value="diagnostics">Диагностика</option>
            <option value="procedure">Процедуры</option>
          </select>
        </div>
      </section>

      {loading ? (
        <CardListSkeleton count={3} />
      ) : error ? (
        <ErrorState message={error} />
      ) : !data || visibleRows.length === 0 ? (
        <EmptyState
          title="Нет услуг для отображения"
          description="Попробуйте отключить фильтр «Только общие услуги» или выбрать другую категорию."
        />
      ) : (
        <div
          tabIndex={0}
          role="region"
          aria-labelledby="compare-table-heading"
          className="max-h-[72vh] overflow-auto rounded-2xl border border-border bg-surface"
        >
          <table className="w-full min-w-[680px] border-separate border-spacing-0 text-left text-sm">
            <thead className="sticky top-0 z-20 bg-surface-subtle">
              <tr>
                <th
                  scope="col"
                  className="sticky left-0 z-30 min-w-56 border-r border-b border-border bg-surface-subtle px-4 py-3.5 text-xs font-semibold uppercase tracking-wide text-ink-muted"
                >
                  Услуга ({visibleRows.length})
                </th>
                {data.clinics.map((clinic) => (
                  <th
                    key={clinic.id}
                    scope="col"
                    className="min-w-52 border-b border-border px-4 py-3.5 align-top"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <Link
                          to={`/clinics/${clinic.id}`}
                          className="font-semibold text-brand hover:underline"
                        >
                          {clinic.clinic_name}
                        </Link>
                        <p className="mt-0.5 flex items-center gap-1 text-xs font-normal text-ink-muted">
                          <MapPin className="h-3 w-3 shrink-0" aria-hidden="true" />
                          {clinic.city}
                        </p>
                        {clinic.rating !== null ? (
                          <p className="mt-0.5 inline-flex items-center gap-1 text-xs font-medium text-ink tabular-nums">
                            <Star
                              className="h-3 w-3 fill-amber-400 text-amber-500"
                              aria-hidden="true"
                            />
                            {clinic.rating.toFixed(1)}
                          </p>
                        ) : null}
                      </div>
                      <button
                        type="button"
                        onClick={() => handleRemoveClinic(clinic.id)}
                        aria-label={`Убрать ${clinic.clinic_name} из сравнения`}
                        className="rounded p-1 text-ink-subtle hover:bg-border/60 hover:text-ink"
                      >
                        <X className="h-4 w-4" aria-hidden="true" />
                      </button>
                    </div>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visibleRows.map((row) => {
                const prices = Object.values(row.cells)
                  .filter((c): c is NonNullable<typeof c> => c !== null)
                  .map((c) => c.price_kzt);
                const maxPrice = prices.length > 1 ? Math.max(...prices) : null;
                const minPrice = prices.length > 1 ? Math.min(...prices) : null;
                const savings =
                  maxPrice !== null && minPrice !== null && maxPrice > minPrice
                    ? maxPrice - minPrice
                    : null;

                return (
                  <tr key={row.service_id} className="hover:bg-canvas/70">
                    <th
                      scope="row"
                      className="sticky left-0 z-10 border-r border-b border-border bg-surface px-4 py-3.5 align-top font-medium text-ink"
                    >
                      <p>{row.canonical_name}</p>
                      <p className="mt-0.5 text-xs font-normal text-ink-subtle">
                        {categoryLabelRu(row.category)}
                        {savings !== null
                          ? ` · экономия до ${formatPriceKzt(savings)}`
                          : ''}
                      </p>
                    </th>
                    {data.clinics.map((clinic) => {
                      const cell = row.cells[clinic.id];
                      const isCheapest =
                        cell !== null &&
                        prices.length > 1 &&
                        row.cheapest_clinic_id === clinic.id;

                      return (
                        <td
                          key={clinic.id}
                          className={`border-b border-border px-4 py-3.5 align-top ${
                            isCheapest ? 'bg-savings-bg/70' : ''
                          }`}
                        >
                          {cell ? (
                            <div className="space-y-1">
                              <div className="flex flex-wrap items-center gap-1.5">
                                <span className="text-base font-bold text-ink tabular-nums">
                                  {formatPriceKzt(cell.price_kzt)}
                                </span>
                                {isCheapest ? (
                                  <span className="inline-flex items-center gap-0.5 rounded bg-savings px-1.5 py-0.5 text-[11px] font-semibold text-white">
                                    <Check className="h-3 w-3" aria-hidden="true" />
                                    Выгоднее
                                  </span>
                                ) : null}
                              </div>
                              <p className="text-xs text-ink-subtle">
                                {formatDurationDays(cell.duration_days)} ·{' '}
                                {formatFreshness(cell.parsed_at)}
                              </p>
                              <a
                                href={cell.source_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 text-xs font-medium text-brand hover:underline"
                              >
                                Источник <ExternalLink className="h-3 w-3" aria-hidden="true" />
                              </a>
                            </div>
                          ) : (
                            <span className="text-xs text-ink-subtle">— нет в прайсе</span>
                          )}
                        </td>
                      );
                    })}
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

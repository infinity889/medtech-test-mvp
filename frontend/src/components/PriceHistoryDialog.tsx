import { TrendingUp, X } from 'lucide-react';
import { useEffect, useId, useRef, useState } from 'react';
import { ApiClientError, fetchPriceHistory } from '../api/client';
import type { PriceHistoryPointItem, PriceHistoryResponse } from '../api/types';
import { formatExactDate, formatPriceKzt, formatShortDate } from '../utils/format';
import { ErrorState } from './StateViews';

interface PriceHistoryDialogProps {
  serviceId: string | null;
  serviceName: string;
  clinicId?: string;
  onClose: () => void;
}

const PERIOD_OPTIONS = [
  { days: 30, label: '30 дней' },
  { days: 90, label: '90 дней' },
  { days: 365, label: '365 дней' },
] as const;

const SERIES_COLORS = ['#0f766e', '#2563eb', '#d97706', '#dc2626', '#7c3aed'] as const;

function buildSeries(points: PriceHistoryPointItem[]) {
  const byClinic = new Map<string, { clinicName: string; city: string; items: PriceHistoryPointItem[] }>();
  for (const pt of points) {
    const existing = byClinic.get(pt.clinic_id);
    if (existing) {
      existing.items.push(pt);
    } else {
      byClinic.set(pt.clinic_id, {
        clinicName: pt.clinic_name,
        city: pt.city,
        items: [pt],
      });
    }
  }
  return Array.from(byClinic.entries()).map(([id, data], idx) => ({
    clinicId: id,
    clinicName: data.clinicName,
    city: data.city,
    color: SERIES_COLORS[idx % SERIES_COLORS.length] ?? '#0f766e',
    items: data.items,
  }));
}

export function PriceHistoryDialog({
  serviceId,
  serviceName,
  clinicId,
  onClose,
}: PriceHistoryDialogProps) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const titleId = useId();
  const [days, setDays] = useState<number>(90);
  const [data, setData] = useState<PriceHistoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Open/close native modal dialog cleanly via showModal()
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (serviceId) {
      if (!dialog.open) {
        dialog.showModal();
      }
    } else if (dialog.open) {
      dialog.close();
    }
  }, [serviceId]);

  // Safari fallback for declarative closedby="any" light dismiss
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog || typeof HTMLDialogElement === 'undefined') return;
    if ('closedBy' in HTMLDialogElement.prototype) return;

    const isOutside = (e: PointerEvent) => {
      const r = dialog.getBoundingClientRect();
      return e.clientX < r.left || e.clientX > r.right || e.clientY < r.top || e.clientY > r.bottom;
    };

    let pressedOutside = false;
    const onPointerDown = (e: PointerEvent) => {
      pressedOutside = isOutside(e);
    };
    const onPointerUp = (e: PointerEvent) => {
      if (pressedOutside && isOutside(e) && dialog.open) {
        dialog.close();
      }
      pressedOutside = false;
    };

    dialog.addEventListener('pointerdown', onPointerDown);
    dialog.addEventListener('pointerup', onPointerUp);
    return () => {
      dialog.removeEventListener('pointerdown', onPointerDown);
      dialog.removeEventListener('pointerup', onPointerUp);
    };
  }, []);

  useEffect(() => {
    if (!serviceId) return;
    const controller = new AbortController();
    setLoading(true);
    setError(null);

    fetchPriceHistory(serviceId, { clinic_id: clinicId, days }, controller.signal)
      .then(setData)
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setError(err instanceof ApiClientError ? err.message : 'Не удалось загрузить историю цен.');
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });

    return () => controller.abort();
  }, [serviceId, clinicId, days]);

  const points = data?.points ?? [];
  const series = buildSeries(points);

  // Chart coordinate math
  const width = 620;
  const height = 240;
  const pad = { top: 20, right: 20, bottom: 34, left: 68 };
  const innerW = width - pad.left - pad.right;
  const innerH = height - pad.top - pad.bottom;

  const prices = points.map((p) => p.price_kzt);
  const times = points.map((p) => new Date(p.recorded_at).getTime());
  const minPrice = prices.length > 0 ? Math.min(...prices) : 0;
  const maxPrice = prices.length > 0 ? Math.max(...prices) : 1000;
  const priceSpan = Math.max(maxPrice - minPrice, 100);
  const yMin = Math.max(0, Math.floor((minPrice - priceSpan * 0.12) / 50) * 50);
  const yMax = Math.ceil((maxPrice + priceSpan * 0.12) / 50) * 50;

  const minTime = times.length > 0 ? Math.min(...times) : Date.now() - 86_400_000;
  const maxTime = times.length > 0 ? Math.max(...times) : Date.now();
  const timeSpan = Math.max(maxTime - minTime, 1);

  const mapX = (iso: string) => {
    const t = new Date(iso).getTime();
    if (maxTime === minTime) return pad.left + innerW / 2;
    return pad.left + ((t - minTime) / timeSpan) * innerW;
  };
  const mapY = (price: number) =>
    pad.top + innerH - ((price - yMin) / Math.max(yMax - yMin, 1)) * innerH;

  const yTicks = [yMin, Math.round((yMin + yMax) / 2), yMax];

  return (
    <dialog
      ref={dialogRef}
      {...({ closedby: 'any' } as Record<string, string>)}
      aria-labelledby={titleId}
      onClose={() => {
        if (dialogRef.current) {
          dialogRef.current.returnValue = '';
        }
        onClose();
      }}
      className="m-auto w-[min(94vw,720px)] max-h-[90vh] overflow-y-auto rounded-2xl border border-border bg-surface p-0 text-ink shadow-2xl"
    >
      <div className="flex items-start justify-between gap-4 border-b border-border px-5 py-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-wide text-brand">
            <TrendingUp className="h-4 w-4" aria-hidden="true" />
            Динамика цен
          </div>
          <h1 id={titleId} className="mt-1 text-lg font-bold leading-snug text-ink">
            {data?.canonical_name || serviceName}
          </h1>
        </div>

        <button
          type="button"
          autoFocus
          onClick={() => dialogRef.current?.close()}
          aria-label="Закрыть окно истории цен"
          className="rounded-lg p-2 text-ink-muted transition hover:bg-surface-subtle hover:text-ink"
        >
          <X className="h-5 w-5" aria-hidden="true" />
        </button>
      </div>

      <div className="space-y-5 p-5">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="inline-flex rounded-lg border border-border bg-surface-subtle p-0.5">
            {PERIOD_OPTIONS.map((opt) => (
              <button
                key={opt.days}
                type="button"
                onClick={() => setDays(opt.days)}
                className={`rounded-md px-3 py-1.5 text-xs font-medium transition ${
                  days === opt.days
                    ? 'bg-surface text-brand shadow-xs'
                    : 'text-ink-muted hover:text-ink'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
          {points.length > 0 ? (
            <span className="text-xs text-ink-subtle tabular-nums">
              Наблюдений: {points.length} · от {formatPriceKzt(minPrice)} до{' '}
              {formatPriceKzt(maxPrice)}
            </span>
          ) : null}
        </div>

        {loading ? (
          <div className="h-56 animate-pulse rounded-xl bg-surface-subtle" />
        ) : error ? (
          <ErrorState message={error} />
        ) : points.length === 0 ? (
          <p className="rounded-xl border border-border bg-surface-subtle/50 p-6 text-center text-sm text-ink-muted">
            За выбранный период наблюдений по ценам пока нет.
          </p>
        ) : (
          <>
            <div className="overflow-x-auto rounded-xl border border-border bg-canvas p-3">
              <svg
                data-testid="price-history-svg"
                viewBox={`0 0 ${width} ${height}`}
                role="img"
                aria-label={`График истории цен на услугу ${data?.canonical_name || serviceName}`}
                className="h-auto w-full min-w-[460px]"
              >
                {/* Horizontal grid lines */}
                {yTicks.map((tick) => {
                  const y = mapY(tick);
                  return (
                    <g key={tick}>
                      <line
                        x1={pad.left}
                        x2={width - pad.right}
                        y1={y}
                        y2={y}
                        stroke="#cbd5e1"
                        strokeDasharray="3 3"
                      />
                      <text
                        x={pad.left - 8}
                        y={y + 4}
                        textAnchor="end"
                        fontSize="11"
                        fill="#475569"
                      >
                        {formatPriceKzt(tick)}
                      </text>
                    </g>
                  );
                })}

                {/* X-axis start/end dates */}
                <text x={pad.left} y={height - 8} fontSize="11" fill="#64748b">
                  {formatShortDate(new Date(minTime).toISOString())}
                </text>
                {maxTime !== minTime ? (
                  <text
                    x={width - pad.right}
                    y={height - 8}
                    textAnchor="end"
                    fontSize="11"
                    fill="#64748b"
                  >
                    {formatShortDate(new Date(maxTime).toISOString())}
                  </text>
                ) : null}

                {/* Series lines and points */}
                {series.map((s) => {
                  const pathD = s.items
                    .map((pt, idx) => `${idx === 0 ? 'M' : 'L'} ${mapX(pt.recorded_at)} ${mapY(pt.price_kzt)}`)
                    .join(' ');
                  return (
                    <g key={s.clinicId}>
                      {s.items.length > 1 ? (
                        <path
                          d={pathD}
                          fill="none"
                          stroke={s.color}
                          strokeWidth="2.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      ) : null}
                      {s.items.map((pt, i) => (
                        <circle
                          key={`${s.clinicId}-${i}`}
                          cx={mapX(pt.recorded_at)}
                          cy={mapY(pt.price_kzt)}
                          r="4.5"
                          fill={s.color}
                          stroke="#ffffff"
                          strokeWidth="1.5"
                        >
                          <title>
                            {`${s.clinicName} (${s.city}): ${formatPriceKzt(pt.price_kzt)} — ${formatExactDate(pt.recorded_at)}`}
                          </title>
                        </circle>
                      ))}
                    </g>
                  );
                })}
              </svg>
            </div>

            {/* Legend */}
            <div className="flex flex-wrap gap-3 text-xs">
              {series.map((s) => (
                <span key={s.clinicId} className="inline-flex items-center gap-1.5 text-ink-muted">
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: s.color }}
                    aria-hidden="true"
                  />
                  {s.clinicName} ({s.city})
                </span>
              ))}
            </div>

            {/* Accessible tabular observations */}
            <div
              tabIndex={0}
              role="region"
              aria-label="Таблица истории наблюдений цен"
              className="max-h-48 overflow-auto rounded-lg border border-border"
            >
              <table className="w-full border-separate border-spacing-0 text-left text-xs">
                <thead className="sticky top-0 bg-surface-subtle text-ink-muted">
                  <tr>
                    <th className="px-3 py-2 font-medium">Дата</th>
                    <th className="px-3 py-2 font-medium">Клиника</th>
                    <th className="px-3 py-2 font-medium">Город</th>
                    <th className="px-3 py-2 text-right font-medium">Цена</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {[...points].reverse().map((pt, idx) => (
                    <tr key={`${pt.clinic_id}-${pt.recorded_at}-${idx}`} className="bg-surface">
                      <td className="px-3 py-2 text-ink-muted tabular-nums">
                        {formatExactDate(pt.recorded_at)}
                      </td>
                      <td className="px-3 py-2 font-medium text-ink">{pt.clinic_name}</td>
                      <td className="px-3 py-2 text-ink-muted">{pt.city}</td>
                      <td className="px-3 py-2 text-right font-semibold text-ink tabular-nums">
                        {formatPriceKzt(pt.price_kzt)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
      </div>
    </dialog>
  );
}

import { AlertCircle, RefreshCw, SearchX } from 'lucide-react';
import type { ReactNode } from 'react';

export function CardListSkeleton({ count = 4 }: { count?: number }) {
  return (
    <div
      role="status"
      aria-busy="true"
      aria-label="Загрузка предложений"
      className="space-y-3"
    >
      {Array.from({ length: count }).map((_, idx) => (
        <div
          key={idx}
          className="animate-pulse rounded-xl border border-border bg-surface p-5"
        >
          <div className="flex flex-col justify-between gap-4 sm:flex-row">
            <div className="flex-1 space-y-2.5">
              <div className="h-5 w-2/3 rounded bg-surface-subtle" />
              <div className="h-4 w-1/2 rounded bg-surface-subtle" />
              <div className="h-3.5 w-1/3 rounded bg-surface-subtle" />
            </div>
            <div className="flex flex-col items-end gap-2">
              <div className="h-7 w-28 rounded bg-surface-subtle" />
              <div className="h-9 w-36 rounded bg-surface-subtle" />
            </div>
          </div>
        </div>
      ))}
    </div>
  );
}

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div
      role="status"
      className="flex flex-col items-center justify-center rounded-xl border border-border bg-surface px-6 py-12 text-center"
    >
      <div className="flex h-12 w-12 items-center justify-center rounded-full bg-surface-subtle text-ink-subtle">
        <SearchX className="h-6 w-6" aria-hidden="true" />
      </div>
      <h2 className="mt-4 text-base font-semibold text-ink">{title}</h2>
      <p className="mt-1.5 max-w-md text-sm text-ink-muted">{description}</p>
      {action ? <div className="mt-5">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  title = 'Не удалось загрузить данные',
  message,
  onRetry,
}: {
  title?: string;
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex flex-col items-start gap-3 rounded-xl border border-danger/25 bg-danger-bg p-5 text-danger sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="flex items-start gap-3">
        <AlertCircle className="mt-0.5 h-5 w-5 shrink-0" aria-hidden="true" />
        <div>
          <p className="text-sm font-semibold">{title}</p>
          <p className="mt-0.5 text-sm opacity-90">{message}</p>
        </div>
      </div>
      {onRetry ? (
        <button
          type="button"
          onClick={onRetry}
          className="inline-flex shrink-0 items-center gap-1.5 rounded-lg border border-danger/30 bg-surface px-3.5 py-2 text-sm font-medium text-danger transition hover:bg-danger-bg"
        >
          <RefreshCw className="h-4 w-4" aria-hidden="true" />
          Повторить
        </button>
      ) : null}
    </div>
  );
}

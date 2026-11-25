import { ArrowRight, Scale, Trash2, X } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { useCompare } from '../context/CompareContext';

export function CompareDock() {
  const { clinics, maxClinics, removeClinic, clearAll } = useCompare();
  const location = useLocation();

  if (clinics.length === 0 || location.pathname === '/compare') {
    return null;
  }

  const compareHref = `/compare?clinic_ids=${encodeURIComponent(
    clinics.map((c) => c.id).join(','),
  )}`;
  const canCompare = clinics.length >= 2;

  return (
    <aside
      aria-label="Выбранные клиники для сравнения"
      className="fixed inset-x-0 bottom-0 z-40 border-t border-border-strong bg-surface/95 shadow-lg backdrop-blur-sm"
    >
      <div className="mx-auto flex max-w-7xl flex-col gap-3 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex flex-wrap items-center gap-2">
          <span className="inline-flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-brand">
            <Scale className="h-4 w-4" aria-hidden="true" />
            Сравнение ({clinics.length}/{maxClinics})
          </span>
          {clinics.map((clinic) => (
            <span
              key={clinic.id}
              className="inline-flex items-center gap-1.5 rounded-full border border-border bg-surface-subtle py-1 pr-1.5 pl-3 text-xs font-medium text-ink"
            >
              <span className="max-w-40 truncate">{clinic.clinic_name}</span>
              <button
                type="button"
                onClick={() => removeClinic(clinic.id)}
                aria-label={`Убрать ${clinic.clinic_name} из сравнения`}
                className="rounded-full p-0.5 text-ink-subtle transition hover:bg-border hover:text-ink"
              >
                <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            </span>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={clearAll}
            className="inline-flex items-center gap-1 rounded-lg px-2.5 py-2 text-xs font-medium text-ink-muted transition hover:bg-surface-subtle hover:text-ink"
          >
            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" />
            Очистить
          </button>

          {canCompare ? (
            <Link
              to={compareHref}
              className="inline-flex items-center gap-1.5 rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-hover"
            >
              Сравнить ({clinics.length})
              <ArrowRight className="h-4 w-4" aria-hidden="true" />
            </Link>
          ) : (
            <span className="rounded-lg bg-surface-subtle px-3 py-2 text-xs font-medium text-ink-muted">
              Выберите ещё 1 клинику
            </span>
          )}
        </div>
      </div>
    </aside>
  );
}

import { Activity, MapPin, Menu, Scale, Search, ShieldCheck, X } from 'lucide-react';
import { useState } from 'react';
import type { ReactNode } from 'react';
import { Link, NavLink } from 'react-router-dom';
import { useCompare } from '../context/CompareContext';
import { CompareDock } from './CompareDock';

const NAV_ITEMS = [
  { to: '/', label: 'Поиск цен', icon: Search, end: true },
  { to: '/map', label: 'Карта клиник', icon: MapPin, end: false },
  { to: '/compare', label: 'Сравнение', icon: Scale, end: false },
  { to: '/admin', label: 'Админка', icon: ShieldCheck, end: false },
] as const;

export function Layout({ children }: { children: ReactNode }) {
  const { clinics } = useCompare();
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);

  return (
    <div className="flex min-h-screen flex-col bg-canvas text-ink">
      <header className="sticky top-0 z-30 border-b border-border bg-surface/95 backdrop-blur-sm">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4">
          <Link
            to="/"
            className="flex items-center gap-2.5 text-ink transition hover:opacity-90"
            onClick={() => setMobileMenuOpen(false)}
          >
            <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand text-white">
              <Activity className="h-5 w-5" aria-hidden="true" />
            </span>
            <span className="flex flex-col">
              <span className="text-base font-bold leading-tight tracking-tight">
                MedServicePrice<span className="text-brand">.kz</span>
              </span>
              <span className="hidden text-[11px] leading-tight text-ink-subtle sm:block">
                Сравнение цен клиник Казахстана
              </span>
            </span>
          </Link>

          <nav aria-label="Основная навигация" className="hidden items-center gap-1 md:flex">
            {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
              <NavLink
                key={to}
                to={to}
                end={end}
                className={({ isActive }) =>
                  `inline-flex items-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition ${
                    isActive
                      ? 'bg-brand-soft text-brand'
                      : 'text-ink-muted hover:bg-surface-subtle hover:text-ink'
                  }`
                }
              >
                <Icon className="h-4 w-4" aria-hidden="true" />
                {label}
                {to === '/compare' && clinics.length > 0 ? (
                  <span className="ml-0.5 inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-brand px-1.5 text-xs font-semibold text-white tabular-nums">
                    {clinics.length}
                  </span>
                ) : null}
              </NavLink>
            ))}
          </nav>

          <button
            type="button"
            aria-expanded={mobileMenuOpen}
            aria-label={mobileMenuOpen ? 'Закрыть меню' : 'Открыть меню'}
            onClick={() => setMobileMenuOpen((v) => !v)}
            className="inline-flex items-center justify-center rounded-lg p-2 text-ink-muted transition hover:bg-surface-subtle hover:text-ink md:hidden"
          >
            {mobileMenuOpen ? (
              <X className="h-5 w-5" aria-hidden="true" />
            ) : (
              <Menu className="h-5 w-5" aria-hidden="true" />
            )}
          </button>
        </div>

        {mobileMenuOpen ? (
          <nav
            aria-label="Мобильная навигация"
            className="border-t border-border bg-surface px-4 py-2 md:hidden"
          >
            <div className="flex flex-col gap-1">
              {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
                <NavLink
                  key={to}
                  to={to}
                  end={end}
                  onClick={() => setMobileMenuOpen(false)}
                  className={({ isActive }) =>
                    `flex items-center justify-between rounded-lg px-3 py-2.5 text-sm font-medium ${
                      isActive ? 'bg-brand-soft text-brand' : 'text-ink-muted hover:bg-surface-subtle'
                    }`
                  }
                >
                  <span className="inline-flex items-center gap-2">
                    <Icon className="h-4 w-4" aria-hidden="true" />
                    {label}
                  </span>
                  {to === '/compare' && clinics.length > 0 ? (
                    <span className="inline-flex h-5 min-w-5 items-center justify-center rounded-full bg-brand px-1.5 text-xs font-semibold text-white tabular-nums">
                      {clinics.length}
                    </span>
                  ) : null}
                </NavLink>
              ))}
            </div>
          </nav>
        ) : null}
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 pb-24">{children}</main>

      <footer className="border-t border-border bg-surface py-6 text-xs text-ink-subtle">
        <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 sm:flex-row sm:items-center sm:justify-between">
          <p>
            MedServicePrice.kz — агрегатор публичных прайс-листов медицинских клиник и лабораторий
            Казахстана.
          </p>
          <p>Показываются только актуальные цены (обновление ≤ 30 дней). Уточняйте детали в клинике.</p>
        </div>
      </footer>

      <CompareDock />
    </div>
  );
}

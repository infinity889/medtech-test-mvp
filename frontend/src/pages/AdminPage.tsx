import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  Database,
  LogOut,
  Play,
  RefreshCw,
  ShieldCheck,
} from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';
import type { FormEvent } from 'react';
import {
  ApiClientError,
  fetchAdminErrors,
  fetchAdminRuns,
  fetchAdminSources,
  fetchAdminStats,
  fetchAdminUnmatched,
  ignoreAdminUnmatched,
  resolveAdminUnmatched,
  triggerAdminScrape,
} from '../api/client';
import type {
  AdminStatsResponse,
  AdminUnmatchedListResponse,
  ScrapeErrorDTO,
  ScrapeRunDTO,
  SourceInfo,
} from '../api/types';
import { CardListSkeleton, EmptyState, ErrorState } from '../components/StateViews';
import { formatExactDate, formatPriceKzt } from '../utils/format';

const SESSION_KEY = 'medprice_admin_token_v1';

type AdminTab = 'unmatched' | 'runs' | 'errors';

export function AdminPage() {
  const [token, setToken] = useState<string>(() => sessionStorage.getItem(SESSION_KEY) || '');
  const [tokenInput, setTokenInput] = useState('');
  const [authError, setAuthError] = useState<string | null>(null);
  const [authSubmitting, setAuthSubmitting] = useState(false);

  const [activeTab, setActiveTab] = useState<AdminTab>('unmatched');
  const [stats, setStats] = useState<AdminStatsResponse | null>(null);
  const [sources, setSources] = useState<SourceInfo[]>([]);
  const [unmatched, setUnmatched] = useState<AdminUnmatchedListResponse | null>(null);
  const [runs, setRuns] = useState<ScrapeRunDTO[]>([]);
  const [errors, setErrors] = useState<ScrapeErrorDTO[]>([]);
  const [page, setPage] = useState(1);

  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionBanner, setActionBanner] = useState<{
    kind: 'success' | 'warning' | 'error';
    text: string;
  } | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [scrapeRunning, setScrapeRunning] = useState(false);
  const [selectedSource, setSelectedSource] = useState<string>('');
  const [scrapeLimit, setScrapeLimit] = useState<string>('50');

  const handleUnauthorized = useCallback(() => {
    sessionStorage.removeItem(SESSION_KEY);
    setToken('');
    setAuthError('Неверный токен администратора или сессия истекла.');
  }, []);

  const loadDashboard = useCallback(
    async (activeToken: string, targetPage: number, signal?: AbortSignal) => {
      setLoading(true);
      setLoadError(null);
      try {
        const [statsRes, sourcesRes, unmatchedRes, runsRes, errorsRes] = await Promise.all([
          fetchAdminStats(activeToken, signal),
          fetchAdminSources(activeToken, signal),
          fetchAdminUnmatched(activeToken, { status: 'pending', page: targetPage, page_size: 20 }, signal),
          fetchAdminRuns(activeToken, 20, signal),
          fetchAdminErrors(activeToken, 30, signal),
        ]);
        setStats(statsRes);
        setSources(sourcesRes);
        setUnmatched(unmatchedRes);
        setRuns(runsRes);
        setErrors(errorsRes);
      } catch (err: unknown) {
        if (signal?.aborted) return;
        if (err instanceof ApiClientError && err.status === 401) {
          handleUnauthorized();
          return;
        }
        setLoadError(
          err instanceof ApiClientError
            ? err.message
            : 'Не удалось загрузить данные панели оператора.',
        );
      } finally {
        if (!signal?.aborted) setLoading(false);
      }
    },
    [handleUnauthorized],
  );

  useEffect(() => {
    if (!token) return;
    const controller = new AbortController();
    void loadDashboard(token, page, controller.signal);
    return () => controller.abort();
  }, [token, page, loadDashboard]);

  async function handleLogin(event: FormEvent) {
    event.preventDefault();
    const candidate = tokenInput.trim();
    if (!candidate) {
      setAuthError('Введите X-Admin-Token.');
      return;
    }
    setAuthSubmitting(true);
    setAuthError(null);
    try {
      await fetchAdminStats(candidate);
      sessionStorage.setItem(SESSION_KEY, candidate);
      setToken(candidate);
      setTokenInput('');
    } catch (err: unknown) {
      if (err instanceof ApiClientError && err.status === 401) {
        setAuthError('Неверный токен администратора.');
      } else {
        setAuthError('Не удалось связаться с API.');
      }
    } finally {
      setAuthSubmitting(false);
    }
  }

  function handleLogout() {
    sessionStorage.removeItem(SESSION_KEY);
    setToken('');
    setStats(null);
    setActionBanner(null);
  }

  async function handleTriggerScrape() {
    setScrapeRunning(true);
    setActionBanner(null);
    try {
      const limitNum = Number(scrapeLimit);
      const res = await triggerAdminScrape(token, {
        source_ids: selectedSource ? [selectedSource] : null,
        limit: Number.isFinite(limitNum) && limitNum > 0 ? limitNum : null,
        normalize: true,
      });
      const fetchedTotal = res.runs.reduce((acc, r) => acc + r.records_fetched, 0);
      setActionBanner({
        kind: 'success',
        text: `Парсинг завершён: обработано ${fetchedTotal} записей, новых предложений: ${res.normalization_summary?.offers_inserted ?? 0}.`,
      });
      await loadDashboard(token, page);
    } catch (err: unknown) {
      if (err instanceof ApiClientError && err.status === 401) {
        handleUnauthorized();
      } else if (err instanceof ApiClientError && err.status === 409) {
        setActionBanner({
          kind: 'warning',
          text: 'Парсинг уже выполняется другим запросом (409 SCRAPE_IN_PROGRESS). Подождите завершения.',
        });
      } else {
        setActionBanner({
          kind: 'error',
          text: err instanceof ApiClientError ? err.message : 'Ошибка запуска парсинга.',
        });
      }
    } finally {
      setScrapeRunning(false);
    }
  }

  async function handleResolve(unmatchedId: string, serviceId: string, serviceName: string) {
    setBusyId(unmatchedId);
    setActionBanner(null);
    try {
      await resolveAdminUnmatched(token, unmatchedId, serviceId, true);
      setActionBanner({
        kind: 'success',
        text: `Привязано к «${serviceName}» и добавлено в синонимы справочника.`,
      });
      await loadDashboard(token, page);
    } catch (err: unknown) {
      if (err instanceof ApiClientError && err.status === 401) {
        handleUnauthorized();
      } else {
        setActionBanner({
          kind: 'error',
          text: err instanceof ApiClientError ? err.message : 'Не удалось привязать услугу.',
        });
      }
    } finally {
      setBusyId(null);
    }
  }

  async function handleIgnore(unmatchedId: string) {
    setBusyId(unmatchedId);
    setActionBanner(null);
    try {
      await ignoreAdminUnmatched(token, unmatchedId);
      setActionBanner({
        kind: 'success',
        text: 'Позиция перемещена в список игнорируемых.',
      });
      await loadDashboard(token, page);
    } catch (err: unknown) {
      if (err instanceof ApiClientError && err.status === 401) {
        handleUnauthorized();
      } else {
        setActionBanner({
          kind: 'error',
          text: err instanceof ApiClientError ? err.message : 'Не удалось игнорировать позицию.',
        });
      }
    } finally {
      setBusyId(null);
    }
  }

  if (!token) {
    return (
      <div className="mx-auto max-w-md py-8">
        <section className="rounded-2xl border border-border bg-surface p-6">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand-soft text-brand">
            <ShieldCheck className="h-6 w-6" aria-hidden="true" />
          </div>
          <h1 className="mt-4 text-xl font-bold text-ink">Панель оператора</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Введите заголовок <code>X-Admin-Token</code> (настраивается в <code>.env</code>{' '}
            переменной <code>ADMIN_API_TOKEN</code>). Токен хранится только в{' '}
            <code>sessionStorage</code> текущей вкладки.
          </p>

          <form onSubmit={handleLogin} className="mt-5 space-y-4">
            <div>
              <label
                htmlFor="admin-token-input"
                className="block text-xs font-medium text-ink-muted"
              >
                Токен администратора
              </label>
              <input
                id="admin-token-input"
                type="password"
                autoComplete="off"
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                placeholder="Введите X-Admin-Token…"
                className="mt-1.5 h-11 w-full rounded-lg border border-border-strong bg-surface px-3.5 text-sm text-ink focus:border-brand focus:outline-none"
              />
            </div>

            {authError ? (
              <p role="alert" className="rounded-lg bg-danger-bg px-3 py-2 text-xs text-danger">
                {authError}
              </p>
            ) : null}

            <button
              type="submit"
              disabled={authSubmitting}
              className="w-full rounded-lg bg-brand px-4 py-2.5 text-sm font-medium text-white transition hover:bg-brand-hover disabled:opacity-60"
            >
              {authSubmitting ? 'Проверка токена…' : 'Войти'}
            </button>
          </form>
        </section>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <section className="flex flex-col gap-4 rounded-2xl border border-border bg-surface p-5 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-xl font-bold text-ink sm:text-2xl">Панель оператора и парсинга</h1>
          <p className="mt-1 text-sm text-ink-muted">
            Управление ручным запуском парсера, мониторинг ошибок и разметка очереди{' '}
            <code>unmatched</code>.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => void loadDashboard(token, page)}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border-strong bg-surface px-3 py-2 text-xs font-medium text-ink hover:border-brand hover:text-brand"
          >
            <RefreshCw className="h-3.5 w-3.5" aria-hidden="true" />
            Обновить
          </button>
          <button
            type="button"
            onClick={handleLogout}
            className="inline-flex items-center gap-1.5 rounded-lg border border-border px-3 py-2 text-xs font-medium text-ink-muted hover:bg-surface-subtle hover:text-ink"
          >
            <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
            Выйти
          </button>
        </div>
      </section>

      {actionBanner ? (
        <div
          role={actionBanner.kind === 'error' ? 'alert' : 'status'}
          className={`flex items-center gap-2.5 rounded-xl border px-4 py-3 text-sm ${
            actionBanner.kind === 'success'
              ? 'border-savings/25 bg-savings-bg text-savings'
              : actionBanner.kind === 'warning'
                ? 'border-warning/30 bg-warning-bg text-warning'
                : 'border-danger/30 bg-danger-bg text-danger'
          }`}
        >
          {actionBanner.kind === 'success' ? (
            <CheckCircle2 className="h-4 w-4 shrink-0" aria-hidden="true" />
          ) : (
            <AlertTriangle className="h-4 w-4 shrink-0" aria-hidden="true" />
          )}
          <span>{actionBanner.text}</span>
        </div>
      ) : null}

      {/* Stats grid */}
      {stats ? (
        <section
          aria-label="Статистика базы данных"
          className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6"
        >
          {[
            { label: 'Услуг в каталоге', value: stats.catalog_services },
            { label: 'Клиник', value: stats.clinics },
            { label: 'Активных цен', value: stats.offers_active },
            { label: 'Всего предложений', value: stats.offers_total },
            { label: 'Точек истории', value: stats.price_history_points },
            { label: 'Очередь unmatched', value: stats.unmatched_pending },
          ].map((card) => (
            <div
              key={card.label}
              className="rounded-xl border border-border bg-surface p-4"
            >
              <p className="text-xs text-ink-subtle">{card.label}</p>
              <p className="mt-1 text-2xl font-bold text-ink tabular-nums">{card.value}</p>
            </div>
          ))}
        </section>
      ) : null}

      {/* Manual Scrape Trigger */}
      <section className="rounded-2xl border border-border bg-surface p-5">
        <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
          <div>
            <h2 className="flex items-center gap-2 text-base font-semibold text-ink">
              <Database className="h-4 w-4 text-brand" aria-hidden="true" />
              Ручной запуск парсинга и нормализации
            </h2>
            <p className="mt-1 text-xs text-ink-muted">
              Защищено серверной блокировкой от дублей (409 SCRAPE_IN_PROGRESS).
            </p>
          </div>

          <div className="flex flex-wrap items-end gap-2.5">
            <div>
              <label htmlFor="admin-source" className="block text-xs text-ink-muted">
                Источник
              </label>
              <select
                id="admin-source"
                value={selectedSource}
                onChange={(e) => setSelectedSource(e.target.value)}
                className="mt-1 h-9 rounded-lg border border-border-strong bg-surface px-3 text-sm text-ink"
              >
                <option value="">Все источники ({sources.length})</option>
                {sources.map((src) => (
                  <option key={src.source_id} value={src.source_id}>
                    {src.display_name} ({src.source_id})
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label htmlFor="admin-limit" className="block text-xs text-ink-muted">
                Лимит записей
              </label>
              <input
                id="admin-limit"
                type="number"
                min={1}
                max={5000}
                value={scrapeLimit}
                onChange={(e) => setScrapeLimit(e.target.value)}
                className="mt-1 h-9 w-28 rounded-lg border border-border-strong bg-surface px-3 text-sm tabular-nums text-ink"
              />
            </div>

            <button
              type="button"
              disabled={scrapeRunning}
              onClick={() => void handleTriggerScrape()}
              className="inline-flex h-9 items-center gap-1.5 rounded-lg bg-brand px-4 text-sm font-medium text-white transition hover:bg-brand-hover disabled:opacity-60"
            >
              <Play className="h-4 w-4" aria-hidden="true" />
              {scrapeRunning ? 'Выполняется…' : 'Запустить парсинг'}
            </button>
          </div>
        </div>
      </section>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-border">
        {[
          { id: 'unmatched' as const, label: `Очередь unmatched (${stats?.unmatched_pending ?? 0})` },
          { id: 'runs' as const, label: `История запусков (${runs.length})` },
          { id: 'errors' as const, label: `Ошибки парсинга (${errors.length})` },
        ].map((tab) => (
          <button
            key={tab.id}
            type="button"
            onClick={() => setActiveTab(tab.id)}
            className={`border-b-2 px-4 py-2.5 text-sm font-medium transition ${
              activeTab === tab.id
                ? 'border-brand text-brand'
                : 'border-transparent text-ink-muted hover:text-ink'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {loading && !unmatched ? (
        <CardListSkeleton count={3} />
      ) : loadError ? (
        <ErrorState message={loadError} onRetry={() => void loadDashboard(token, page)} />
      ) : activeTab === 'unmatched' ? (
        <section aria-label="Очередь нераспознанных услуг" className="space-y-3">
          {!unmatched || unmatched.items.length === 0 ? (
            <EmptyState
              title="Очередь разметки пуста"
              description="Все собранные услуги уже сопоставлены со справочником или отмечены как игнорируемые."
            />
          ) : (
            <>
              <div className="space-y-2.5">
                {unmatched.items.map((item) => {
                  const isBusy = busyId === item.id;
                  return (
                    <article
                      key={item.id}
                      className="flex flex-col justify-between gap-3 rounded-xl border border-border bg-surface p-4 sm:flex-row sm:items-center"
                    >
                      <div className="min-w-0 space-y-1">
                        <p className="font-semibold text-ink">{item.service_name_raw}</p>
                        <p className="text-xs text-ink-muted">
                          {item.clinic_name_raw} · {item.city_raw} · {item.source_id} ·{' '}
                          <strong className="text-ink tabular-nums">
                            {formatPriceKzt(item.price_kzt)}
                          </strong>
                        </p>
                        {item.suggested_service_name ? (
                          <p className="text-xs text-brand">
                            Подсказка: <strong>{item.suggested_service_name}</strong>{' '}
                            {item.suggested_score !== null
                              ? `(${item.suggested_score.toFixed(1)}%)`
                              : ''}
                          </p>
                        ) : (
                          <p className="text-xs text-ink-subtle">Автоматическая подсказка не найдена</p>
                        )}
                      </div>

                      <div className="flex shrink-0 flex-wrap items-center gap-2">
                        {item.suggested_service_id && item.suggested_service_name ? (
                          <button
                            type="button"
                            disabled={isBusy}
                            onClick={() =>
                              void handleResolve(
                                item.id,
                                item.suggested_service_id!,
                                item.suggested_service_name!,
                              )
                            }
                            className="inline-flex items-center gap-1 rounded-lg bg-brand px-3 py-1.5 text-xs font-medium text-white hover:bg-brand-hover disabled:opacity-50"
                          >
                            <CheckCircle2 className="h-3.5 w-3.5" aria-hidden="true" />
                            Привязать
                          </button>
                        ) : null}
                        <button
                          type="button"
                          disabled={isBusy}
                          onClick={() => void handleIgnore(item.id)}
                          className="inline-flex items-center gap-1 rounded-lg border border-border px-3 py-1.5 text-xs font-medium text-ink-muted hover:bg-surface-subtle hover:text-ink disabled:opacity-50"
                        >
                          <Ban className="h-3.5 w-3.5" aria-hidden="true" />
                          Игнорировать
                        </button>
                      </div>
                    </article>
                  );
                })}
              </div>

              {unmatched.pagination.total_pages > 1 ? (
                <div className="flex items-center justify-between rounded-xl border border-border bg-surface px-4 py-3 text-xs">
                  <button
                    type="button"
                    disabled={page <= 1}
                    onClick={() => setPage((p) => Math.max(1, p - 1))}
                    className="rounded-lg border border-border px-3 py-1.5 font-medium disabled:opacity-40"
                  >
                    Назад
                  </button>
                  <span className="text-ink-muted tabular-nums">
                    Стр. {unmatched.pagination.page} из {unmatched.pagination.total_pages}
                  </span>
                  <button
                    type="button"
                    disabled={page >= unmatched.pagination.total_pages}
                    onClick={() => setPage((p) => p + 1)}
                    className="rounded-lg border border-border px-3 py-1.5 font-medium disabled:opacity-40"
                  >
                    Вперёд
                  </button>
                </div>
              ) : null}
            </>
          )}
        </section>
      ) : activeTab === 'runs' ? (
        <div
          tabIndex={0}
          role="region"
          aria-label="История запусков парсера"
          className="overflow-x-auto rounded-xl border border-border bg-surface"
        >
          <table className="w-full min-w-[640px] border-separate border-spacing-0 text-left text-xs">
            <thead className="bg-surface-subtle text-ink-muted">
              <tr>
                <th className="px-4 py-3 font-semibold">Источник</th>
                <th className="px-4 py-3 font-semibold">Статус</th>
                <th className="px-4 py-3 font-semibold">Старт</th>
                <th className="px-4 py-3 text-right font-semibold">Собрано</th>
                <th className="px-4 py-3 text-right font-semibold">Новых / Обновл.</th>
                <th className="px-4 py-3 text-right font-semibold">Ошибок</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {runs.map((run) => (
                <tr key={run.id} className="bg-surface">
                  <td className="px-4 py-3 font-medium text-ink">{run.source_id}</td>
                  <td className="px-4 py-3">
                    <span className="rounded bg-surface-subtle px-2 py-0.5 font-medium">
                      {run.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-ink-muted tabular-nums">
                    {formatExactDate(run.started_at)}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">{run.records_fetched}</td>
                  <td className="px-4 py-3 text-right tabular-nums">
                    {run.records_inserted} / {run.records_updated}
                  </td>
                  <td className="px-4 py-3 text-right tabular-nums">{run.errors_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="space-y-2">
          {errors.length === 0 ? (
            <EmptyState
              title="Ошибок парсинга не зафиксировано"
              description="Последние запуски отработали штатно."
            />
          ) : (
            errors.map((err) => (
              <div
                key={err.id}
                className="rounded-xl border border-border bg-surface p-4 text-xs"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-danger">
                    {err.source_id} · {err.error_type}
                  </span>
                  <span className="text-ink-subtle tabular-nums">
                    {formatExactDate(err.occurred_at)}
                  </span>
                </div>
                <p className="mt-1 text-ink">{err.message}</p>
                {err.url ? <p className="mt-0.5 truncate text-ink-subtle">{err.url}</p> : null}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}

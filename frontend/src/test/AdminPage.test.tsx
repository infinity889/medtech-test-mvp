import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { AdminPage } from '../pages/AdminPage';

const MOCK_STATS = {
  catalog_services: 88,
  clinics: 64,
  offers_total: 499,
  offers_active: 499,
  price_history_points: 499,
  unmatched_pending: 2,
};

const MOCK_SOURCES = [
  {
    source_id: 'kdlolymp',
    display_name: 'КДЛ Олимп',
    supported_format: 'html',
    cities: ['Алматы', 'Астана'],
    enabled: true,
  },
];

const MOCK_UNMATCHED = {
  items: [
    {
      id: 'u-111',
      raw_record_id: 'r-111',
      source_id: 'doq',
      clinic_name_raw: 'МедЦентр',
      city_raw: 'Алматы',
      service_name_raw: 'УЗИ молочных желез детям',
      category_hint: 'Диагностика',
      price_kzt: 8000,
      suggested_service_id: 'svc-uzi-1',
      suggested_service_name: 'УЗИ молочных желез',
      suggested_score: 85.7,
      status: 'pending',
      resolved_service_id: null,
      resolved_at: null,
      created_at: new Date().toISOString(),
    },
  ],
  pagination: { page: 1, page_size: 20, total_items: 1, total_pages: 1 },
};

function jsonResp(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('AdminPage', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows error on 401 unauthorized token', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        jsonResp(
          { error: { code: 'UNAUTHORIZED', message: 'Invalid token', details: null } },
          401,
        ),
      ),
    );

    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <AdminPage />
      </MemoryRouter>,
    );

    await user.type(screen.getByLabelText(/Токен администратора/i), 'wrong');
    await user.click(screen.getByRole('button', { name: /Войти/i }));

    expect(await screen.findByText(/Неверный токен администратора/i)).toBeInTheDocument();
  });

  it('loads stats and unmatched queue, resolves item, and handles 409 scrape lock', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes('/admin/stats')) return Promise.resolve(jsonResp(MOCK_STATS));
      if (url.includes('/admin/sources')) return Promise.resolve(jsonResp(MOCK_SOURCES));
      if (url.includes('/admin/scrape-runs') && init?.method === 'POST') {
        return Promise.resolve(
          jsonResp(
            {
              error: {
                code: 'SCRAPE_IN_PROGRESS',
                message: 'A scrape run is already in progress',
                details: null,
              },
            },
            409,
          ),
        );
      }
      if (url.includes('/admin/scrape-runs')) return Promise.resolve(jsonResp([]));
      if (url.includes('/admin/scrape-errors')) return Promise.resolve(jsonResp([]));
      if (url.includes('/admin/unmatched/u-111/resolve')) {
        return Promise.resolve(
          jsonResp({
            offer_id: 'off-1',
            clinic_id: 'c-1',
            service_id: 'svc-uzi-1',
            price_kzt: 8000,
            is_active: true,
          }),
        );
      }
      if (url.includes('/admin/unmatched')) return Promise.resolve(jsonResp(MOCK_UNMATCHED));
      return Promise.resolve(jsonResp({}));
    });
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <AdminPage />
      </MemoryRouter>,
    );

    await user.type(screen.getByLabelText(/Токен администратора/i), 'valid-token');
    await user.click(screen.getByRole('button', { name: /Войти/i }));

    expect(await screen.findByText('УЗИ молочных желез детям')).toBeInTheDocument();
    expect(screen.getByText('88')).toBeInTheDocument();
    expect(screen.getAllByText('499')).toHaveLength(3);

    // 1-click resolve to suggested canonical service
    await user.click(screen.getByRole('button', { name: /Привязать/i }));
    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some((call) => String(call[0]).includes('/admin/unmatched/u-111/resolve')),
      ).toBe(true);
    });

    // Trigger scrape -> 409 handled cleanly
    await user.click(screen.getByRole('button', { name: /Запустить парсинг/i }));
    expect(await screen.findByText(/Парсинг уже выполняется/i)).toBeInTheDocument();
  });
});

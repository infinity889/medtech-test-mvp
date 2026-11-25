import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CompareDock } from '../components/CompareDock';
import { CompareProvider } from '../context/CompareContext';
import { SearchPage } from '../pages/SearchPage';

const MOCK_META = {
  cities: [
    { name: 'Алматы', clinics_count: 25, offers_count: 220 },
    { name: 'Астана', clinics_count: 18, offers_count: 140 },
  ],
  categories: [
    { code: 'lab', label_ru: 'Анализы', offers_count: 300 },
    { code: 'doctor', label_ru: 'Приём врачей', offers_count: 120 },
    { code: 'diagnostics', label_ru: 'Диагностика', offers_count: 79 },
    { code: 'procedure', label_ru: 'Процедуры', offers_count: 0 },
  ],
  price_min_kzt: 480,
  price_max_kzt: 30000,
  last_updated_at: new Date().toISOString(),
};

const MOCK_AUTOCOMPLETE = {
  items: [
    {
      service_id: '3d5d033b-7222-455b-ba6a-a11ab0161d81',
      code: 'lab_oak',
      canonical_name: 'Общий анализ крови (ОАК)',
      category: 'lab',
      matched_synonym: 'ОАК',
      offers_count: 9,
      min_price_kzt: 1880,
    },
  ],
};

const MOCK_OFFERS = {
  items: [
    {
      offer_id: '11111111-1111-1111-1111-111111111111',
      service_id: '3d5d033b-7222-455b-ba6a-a11ab0161d81',
      service_code: 'lab_oak',
      canonical_name: 'Общий анализ крови (ОАК)',
      service_name_raw: 'Общий анализ крови (ОАК без СОЭ)',
      category: 'lab',
      price_kzt: 1880,
      original_price: 1880,
      currency: 'KZT',
      duration_days: 1,
      parsed_at: new Date(Date.now() - 3 * 60 * 60 * 1000).toISOString(),
      source_id: 'kdlolymp',
      source_url: 'https://www.kdlolymp.kz/pricelist/almaty',
      distance_km: null,
      clinic: {
        id: '42efc8d8-0552-4338-b263-4744b0a7acbb',
        source_id: 'kdlolymp',
        clinic_name: 'КДЛ Олимп',
        city: 'Алматы',
        address: 'ул. Толе би, 120',
        phone: '+7 (727) 259-79-69',
        working_hours: 'Пн-Сб 07:30-15:00',
        latitude: 43.237163,
        longitude: 76.945654,
        rating: 4.6,
        has_online_booking: true,
        website_url: 'https://www.kdlolymp.kz',
        route_2gis_url: 'https://2gis.kz/geo/76.945654,43.237163',
        route_google_maps_url: 'https://www.google.com/maps/dir/?api=1&destination=43.237163,76.945654',
      },
    },
  ],
  summary: {
    min_price_kzt: 1880,
    max_price_kzt: 2500,
    avg_price_kzt: 2190,
  },
  pagination: {
    page: 1,
    page_size: 20,
    total_items: 1,
    total_pages: 1,
  },
};

function makeJsonResponse(payload: unknown): Response {
  return new Response(JSON.stringify(payload), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('SearchPage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('loads offers with freshness and source link, supports autocomplete and compare toggle', async () => {
    const fetchMock = vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/meta/filters')) return Promise.resolve(makeJsonResponse(MOCK_META));
      if (url.includes('/services/autocomplete')) {
        return Promise.resolve(makeJsonResponse(MOCK_AUTOCOMPLETE));
      }
      if (url.includes('/offers')) return Promise.resolve(makeJsonResponse(MOCK_OFFERS));
      return Promise.resolve(makeJsonResponse({}));
    });
    vi.stubGlobal('fetch', fetchMock);

    const user = userEvent.setup();
    render(
      <MemoryRouter initialEntries={['/']}>
        <CompareProvider>
          <SearchPage />
          <CompareDock />
        </CompareProvider>
      </MemoryRouter>,
    );

    // Wait for initial offers to render
    expect(await screen.findByText('КДЛ Олимп')).toBeInTheDocument();
    expect(screen.getByText(/Обновлено/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Источник/i })).toHaveAttribute(
      'href',
      'https://www.kdlolymp.kz/pricelist/almaty',
    );

    // Type into autocomplete combobox
    const input = screen.getByRole('combobox', { name: /Поиск медицинской услуги/i });
    await user.type(input, 'ОАК');

    const option = await screen.findByRole('option', { name: /Общий анализ крови \(ОАК\)/i });
    await user.click(option);

    await waitFor(() => {
      const offerCalls = fetchMock.mock.calls
        .map((c) => String(c[0]))
        .filter((u) => u.includes('/api/v1/offers'));
      expect(
        offerCalls.some((u) => u.includes('service_id=3d5d033b-7222-455b-ba6a-a11ab0161d81')),
      ).toBe(true);
    });

    // Toggle online booking filter
    const bookingCheckbox = screen.getByRole('checkbox', { name: /Есть онлайн-запись/i });
    await user.click(bookingCheckbox);
    await waitFor(() => {
      const offerCalls = fetchMock.mock.calls
        .map((c) => String(c[0]))
        .filter((u) => u.includes('/api/v1/offers'));
      expect(offerCalls.some((u) => u.includes('online_booking=true'))).toBe(true);
    });

    // Add clinic to CompareDock from OfferCard
    await user.click(screen.getByRole('button', { name: /В сравнение/i }));
    expect(screen.getByText(/Сравнение \(1\/5\)/i)).toBeInTheDocument();
  });

  it('shows empty state when no offers match filters', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((input: RequestInfo | URL) => {
        const url = String(input);
        if (url.includes('/meta/filters')) return Promise.resolve(makeJsonResponse(MOCK_META));
        return Promise.resolve(
          makeJsonResponse({
            items: [],
            summary: { min_price_kzt: null, max_price_kzt: null, avg_price_kzt: null },
            pagination: { page: 1, page_size: 20, total_items: 0, total_pages: 0 },
          }),
        );
      }),
    );

    render(
      <MemoryRouter initialEntries={['/?q=несуществующаяуслуга']}>
        <CompareProvider>
          <SearchPage />
        </CompareProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText(/Предложений не найдено/i)).toBeInTheDocument();
  });
});

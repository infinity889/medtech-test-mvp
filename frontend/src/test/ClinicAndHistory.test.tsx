import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PriceHistoryDialog } from '../components/PriceHistoryDialog';
import { CompareProvider } from '../context/CompareContext';
import { ClinicDetailPage } from '../pages/ClinicDetailPage';

// Mock ClinicMap in jsdom where canvas/tile layout is absent
vi.mock('../components/ClinicMap', () => ({
  ClinicMap: ({ clinics }: { clinics: Array<{ clinic_name: string }> }) => (
    <div data-testid="clinic-map-mock">Карта: {clinics.length} клиник</div>
  ),
}));

const MOCK_CLINIC_DETAIL = {
  id: '42efc8d8-0552-4338-b263-4744b0a7acbb',
  source_id: 'kdlolymp',
  clinic_name: 'КДЛ Олимп Алматы',
  city: 'Алматы',
  address: 'ул. Толе би, 120',
  phone: '+7 (727) 259-79-69',
  working_hours: 'Пн-Сб 07:30-15:00',
  latitude: 43.237163,
  longitude: 76.945654,
  rating: 4.7,
  has_online_booking: true,
  website_url: 'https://www.kdlolymp.kz',
  updated_at: new Date().toISOString(),
  route_2gis_url: 'https://2gis.kz/geo/76.945654,43.237163',
  route_google_maps_url: 'https://www.google.com/maps/dir/?api=1&destination=43.237163,76.945654',
  offers: [
    {
      offer_id: '11111111-1111-1111-1111-111111111111',
      service_id: '3d5d033b-7222-455b-ba6a-a11ab0161d81',
      service_code: 'lab_oak',
      canonical_name: 'Общий анализ крови (ОАК)',
      service_name_raw: 'ОАК без СОЭ',
      category: 'lab',
      price_kzt: 1880,
      duration_days: 1,
      parsed_at: new Date().toISOString(),
      source_url: 'https://www.kdlolymp.kz/pricelist/almaty',
    },
  ],
};

const MOCK_PRICE_HISTORY = {
  service_id: '3d5d033b-7222-455b-ba6a-a11ab0161d81',
  service_code: 'lab_oak',
  canonical_name: 'Общий анализ крови (ОАК)',
  points: [
    {
      recorded_at: new Date(Date.now() - 20 * 86_400_000).toISOString(),
      price_kzt: 1700,
      clinic_id: '42efc8d8-0552-4338-b263-4744b0a7acbb',
      clinic_name: 'КДЛ Олимп Алматы',
      city: 'Алматы',
    },
    {
      recorded_at: new Date(Date.now() - 2 * 86_400_000).toISOString(),
      price_kzt: 1880,
      clinic_id: '42efc8d8-0552-4338-b263-4744b0a7acbb',
      clinic_name: 'КДЛ Олимп Алматы',
      city: 'Алматы',
    },
  ],
};

function jsonResp(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

describe('ClinicDetailPage & PriceHistoryDialog', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders clinic contacts, 2GIS/Google Maps route links, offers table, and map', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((url: RequestInfo | URL) => {
        if (String(url).includes('/clinics/')) return Promise.resolve(jsonResp(MOCK_CLINIC_DETAIL));
        return Promise.resolve(jsonResp(MOCK_PRICE_HISTORY));
      }),
    );

    const onOpenHistory = vi.fn();
    render(
      <MemoryRouter initialEntries={['/clinics/42efc8d8-0552-4338-b263-4744b0a7acbb']}>
        <CompareProvider>
          <Routes>
            <Route
              path="/clinics/:clinicId"
              element={<ClinicDetailPage onOpenPriceHistory={onOpenHistory} />}
            />
          </Routes>
        </CompareProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByRole('heading', { name: 'КДЛ Олимп Алматы' })).toBeInTheDocument();
    expect(screen.getByText('Пн-Сб 07:30-15:00')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Маршрут в 2GIS/i })).toHaveAttribute(
      'href',
      MOCK_CLINIC_DETAIL.route_2gis_url,
    );
    expect(screen.getByRole('link', { name: /Google Maps/i })).toHaveAttribute(
      'href',
      MOCK_CLINIC_DETAIL.route_google_maps_url,
    );
    expect(screen.getByTestId('clinic-map-mock')).toBeInTheDocument();
    expect(screen.getByText('Общий анализ крови (ОАК)')).toBeInTheDocument();

    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: /История цен/i }));
    expect(onOpenHistory).toHaveBeenCalledWith(
      '3d5d033b-7222-455b-ba6a-a11ab0161d81',
      'Общий анализ крови (ОАК)',
    );
  });

  it('opens native dialog with SVG price history chart and switches period', async () => {
    const fetchMock = vi.fn().mockResolvedValue(jsonResp(MOCK_PRICE_HISTORY));
    vi.stubGlobal('fetch', fetchMock);

    const onClose = vi.fn();
    render(
      <PriceHistoryDialog
        serviceId="3d5d033b-7222-455b-ba6a-a11ab0161d81"
        serviceName="Общий анализ крови (ОАК)"
        onClose={onClose}
      />,
    );

    expect(await screen.findByTestId('price-history-svg')).toBeInTheDocument();
    const user = userEvent.setup();
    await user.click(screen.getByRole('button', { name: '365 дней' }));

    await waitFor(() => {
      expect(
        fetchMock.mock.calls.some((call) => String(call[0]).includes('days=365')),
      ).toBe(true);
    });

    await user.click(screen.getByRole('button', { name: /Закрыть окно истории цен/i }));
    expect(onClose).toHaveBeenCalled();
  });
});

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { CompareProvider } from '../context/CompareContext';
import { ComparePage } from '../pages/ComparePage';

const C1 = '42efc8d8-0552-4338-b263-4744b0a7acbb';
const C2 = '77777777-7777-7777-7777-777777777777';

const MOCK_COMPARE = {
  clinics: [
    {
      id: C1,
      source_id: 'kdlolymp',
      clinic_name: 'КДЛ Олимп',
      city: 'Алматы',
      address: 'ул. Толе би, 120',
      phone: '+7 727 259-79-69',
      working_hours: '07:30-15:00',
      latitude: 43.237,
      longitude: 76.945,
      rating: 4.6,
      has_online_booking: true,
      website_url: 'https://www.kdlolymp.kz',
      route_2gis_url: 'https://2gis.kz/geo/76.945,43.237',
      route_google_maps_url: 'https://www.google.com/maps/dir/?api=1&destination=43.237,76.945',
    },
    {
      id: C2,
      source_id: 'invivo',
      clinic_name: 'Лаборатория INVIVO',
      city: 'Алматы',
      address: 'пр. Назарбаева, 187',
      phone: '+7 727 339-04-80',
      working_hours: '08:00-17:00',
      latitude: 43.24,
      longitude: 76.95,
      rating: 4.8,
      has_online_booking: false,
      website_url: 'https://invivo.kz',
      route_2gis_url: 'https://2gis.kz/geo/76.95,43.24',
      route_google_maps_url: 'https://www.google.com/maps/dir/?api=1&destination=43.24,76.95',
    },
  ],
  rows: [
    {
      service_id: '3d5d033b-7222-455b-ba6a-a11ab0161d81',
      service_code: 'lab_oak',
      canonical_name: 'Общий анализ крови (ОАК)',
      category: 'lab',
      cheapest_clinic_id: C1,
      cells: {
        [C1]: {
          offer_id: 'o1',
          price_kzt: 1880,
          duration_days: 1,
          parsed_at: new Date().toISOString(),
          source_url: 'https://www.kdlolymp.kz/pricelist/almaty',
        },
        [C2]: {
          offer_id: 'o2',
          price_kzt: 2500,
          duration_days: 1,
          parsed_at: new Date().toISOString(),
          source_url: 'https://invivo.kz/ru/almaty',
        },
      },
    },
  ],
};

describe('ComparePage', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('shows empty guidance state when fewer than 2 clinics are selected', () => {
    render(
      <MemoryRouter initialEntries={['/compare']}>
        <CompareProvider>
          <ComparePage />
        </CompareProvider>
      </MemoryRouter>,
    );

    expect(screen.getByText(/Выберите от 2 до 5 клиник/i)).toBeInTheDocument();
  });

  it('renders comparison matrix with cheapest badge and category filter', async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(MOCK_COMPARE), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    vi.stubGlobal('fetch', fetchMock);

    render(
      <MemoryRouter initialEntries={[`/compare?clinic_ids=${C1},${C2}`]}>
        <CompareProvider>
          <ComparePage />
        </CompareProvider>
      </MemoryRouter>,
    );

    expect(await screen.findByText('Общий анализ крови (ОАК)')).toBeInTheDocument();
    expect(screen.getByText('КДЛ Олимп')).toBeInTheDocument();
    expect(screen.getByText('Лаборатория INVIVO')).toBeInTheDocument();
    expect(screen.getByText(/Выгоднее/i)).toBeInTheDocument();

    const user = userEvent.setup();
    await user.selectOptions(screen.getByLabelText(/Категория сравнения/i), 'lab');
    await waitFor(() => {
      expect(fetchMock.mock.calls.some((call) => String(call[0]).includes('category=lab'))).toBe(
        true,
      );
    });
  });
});

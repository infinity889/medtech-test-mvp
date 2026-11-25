import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { ApiClientError, fetchFiltersMeta } from '../api/client';
import { CompareDock } from '../components/CompareDock';
import { CompareProvider, useCompare } from '../context/CompareContext';
import {
  categoryLabelRu,
  formatDistanceKm,
  formatDurationDays,
  formatFreshness,
  formatPriceKzt,
} from '../utils/format';

function CompareHarness() {
  const { clinics, addClinic, removeClinic, clearAll, maxClinics } = useCompare();
  return (
    <div>
      <span data-testid="count">{clinics.length}</span>
      <span data-testid="max">{maxClinics}</span>
      {[1, 2, 3, 4, 5, 6].map((n) => (
        <button
          key={n}
          type="button"
          onClick={() =>
            addClinic({
              id: `00000000-0000-0000-0000-00000000000${n}`,
              clinic_name: `Клиника ${n}`,
              city: 'Алматы',
            })
          }
        >
          Add {n}
        </button>
      ))}
      <button
        type="button"
        onClick={() => removeClinic('00000000-0000-0000-0000-000000000001')}
      >
        Remove 1
      </button>
      <button type="button" onClick={clearAll}>
        Clear
      </button>
      <CompareDock />
    </div>
  );
}

describe('format utilities', () => {
  it('formats KZT prices, durations, distances, categories, and freshness timestamps', () => {
    expect(formatPriceKzt(2850)).toMatch(/2[\s\u00a0]850\s?₸/);
    expect(formatPriceKzt(1880.5)).toMatch(/1[\s\u00a0]880[.,]50\s?₸/);
    expect(formatDurationDays(0)).toBe('В день обращения');
    expect(formatDurationDays(1)).toBe('1 день');
    expect(formatDurationDays(3)).toBe('3 дня');
    expect(formatDurationDays(7)).toBe('7 дней');
    expect(formatDurationDays(null)).toBe('Уточняйте в клинике');
    expect(formatDistanceKm(0.35)).toBe('350 м');
    expect(formatDistanceKm(2.4)).toBe('2.4 км');
    expect(categoryLabelRu('lab')).toBe('Анализы');
    expect(categoryLabelRu('doctor')).toBe('Приём врачей');

    const recent = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
    expect(formatFreshness(recent)).toContain('ч назад');
  });
});

describe('API client error handling', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('parses unified APIError responses into ApiClientError', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            error: {
              code: 'SCRAPE_IN_PROGRESS',
              message: 'A scrape run is already in progress',
              details: null,
            },
          }),
          { status: 409, headers: { 'Content-Type': 'application/json' } },
        ),
      ),
    );

    await expect(fetchFiltersMeta()).rejects.toMatchObject({
      name: 'ApiClientError',
      status: 409,
      code: 'SCRAPE_IN_PROGRESS',
      message: 'A scrape run is already in progress',
    } satisfies Partial<ApiClientError>);
  });
});

describe('CompareContext & CompareDock', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('stores up to 5 clinics in localStorage and builds /compare link', async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <CompareProvider>
          <CompareHarness />
        </CompareProvider>
      </MemoryRouter>,
    );

    await user.click(screen.getByRole('button', { name: 'Add 1' }));
    await user.click(screen.getByRole('button', { name: 'Add 2' }));
    expect(screen.getByTestId('count')).toHaveTextContent('2');

    const compareLink = screen.getByRole('link', { name: /Сравнить \(2\)/i });
    expect(compareLink).toHaveAttribute(
      'href',
      '/compare?clinic_ids=00000000-0000-0000-0000-000000000001%2C00000000-0000-0000-0000-000000000002',
    );

    // Add 3, 4, 5, and try 6th (capped at 5)
    for (const n of [3, 4, 5, 6]) {
      await user.click(screen.getByRole('button', { name: `Add ${n}` }));
    }
    expect(screen.getByTestId('count')).toHaveTextContent('5');

    await user.click(screen.getByRole('button', { name: 'Remove 1' }));
    await waitFor(() => expect(screen.getByTestId('count')).toHaveTextContent('4'));
    expect(JSON.parse(localStorage.getItem('medprice_compare_clinics_v1') || '[]')).toHaveLength(4);
  });
});

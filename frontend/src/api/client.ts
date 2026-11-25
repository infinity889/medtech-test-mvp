import type {
  AdminResolveUnmatchedResponse,
  AdminStatsResponse,
  AdminTriggerScrapeResponse,
  AdminUnmatchedItem,
  AdminUnmatchedListResponse,
  ApiErrorBody,
  ClinicDetail,
  ClinicListResponse,
  CompareMatrixResponse,
  FiltersMetaResponse,
  OfferSearchResponse,
  OfferSortBy,
  PriceHistoryResponse,
  ScrapeErrorDTO,
  ScrapeRunDTO,
  ServiceAutocompleteResponse,
  ServiceCategory,
  SourceInfo,
  UnmatchedStatus,
} from './types';

const API_BASE = '/api/v1';

export class ApiClientError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: unknown;

  constructor(status: number, code: string, message: string, details: unknown = null) {
    super(message);
    this.name = 'ApiClientError';
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function buildQuery(params: Record<string, string | number | boolean | undefined | null>): string {
  const sp = new URLSearchParams();
  for (const [key, val] of Object.entries(params)) {
    if (val === undefined || val === null || val === '') continue;
    sp.set(key, String(val));
  }
  const qs = sp.toString();
  return qs ? `?${qs}` : '';
}

async function requestJson<T>(
  path: string,
  options: {
    method?: 'GET' | 'POST';
    body?: unknown;
    adminToken?: string;
    signal?: AbortSignal;
  } = {},
): Promise<T> {
  const headers: Record<string, string> = {
    Accept: 'application/json',
  };
  if (options.body !== undefined) {
    headers['Content-Type'] = 'application/json';
  }
  if (options.adminToken) {
    headers['X-Admin-Token'] = options.adminToken;
  }

  const response = await fetch(`${API_BASE}${path}`, {
    method: options.method ?? 'GET',
    headers,
    body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
    signal: options.signal,
  });

  if (!response.ok) {
    let code = 'HTTP_ERROR';
    let message = `Ошибка сервера (${response.status})`;
    let details: unknown = null;
    try {
      const parsed = (await response.json()) as Partial<ApiErrorBody>;
      if (parsed.error) {
        code = parsed.error.code || code;
        message = parsed.error.message || message;
        details = parsed.error.details ?? null;
      }
    } catch {
      // Ignore non-JSON error body
    }
    throw new ApiClientError(response.status, code, message, details);
  }

  return (await response.json()) as T;
}

export function fetchFiltersMeta(signal?: AbortSignal): Promise<FiltersMetaResponse> {
  return requestJson<FiltersMetaResponse>('/meta/filters', { signal });
}

export function fetchAutocomplete(
  params: {
    q: string;
    category?: ServiceCategory;
    city?: string;
    limit?: number;
  },
  signal?: AbortSignal,
): Promise<ServiceAutocompleteResponse> {
  return requestJson<ServiceAutocompleteResponse>(
    `/services/autocomplete${buildQuery(params)}`,
    { signal },
  );
}

export interface SearchOffersParams {
  service_id?: string;
  q?: string;
  city?: string;
  category?: ServiceCategory;
  min_price?: number;
  max_price?: number;
  min_rating?: number;
  online_booking?: boolean;
  lat?: number;
  lng?: number;
  sort_by?: OfferSortBy;
  page?: number;
  page_size?: number;
}

export function fetchOffers(
  params: SearchOffersParams,
  signal?: AbortSignal,
): Promise<OfferSearchResponse> {
  return requestJson<OfferSearchResponse>(`/offers${buildQuery({ ...params })}`, { signal });
}

export interface ListClinicsParams {
  city?: string;
  q?: string;
  min_rating?: number;
  online_booking?: boolean;
  has_geo?: boolean;
  page?: number;
  page_size?: number;
}

export function fetchClinics(
  params: ListClinicsParams,
  signal?: AbortSignal,
): Promise<ClinicListResponse> {
  return requestJson<ClinicListResponse>(`/clinics${buildQuery({ ...params })}`, { signal });
}

export function fetchClinicDetail(
  clinicId: string,
  signal?: AbortSignal,
): Promise<ClinicDetail> {
  return requestJson<ClinicDetail>(`/clinics/${encodeURIComponent(clinicId)}`, { signal });
}

export function fetchCompareMatrix(
  params: {
    clinicIds: string[];
    category?: ServiceCategory;
  },
  signal?: AbortSignal,
): Promise<CompareMatrixResponse> {
  return requestJson<CompareMatrixResponse>(
    `/compare${buildQuery({
      clinic_ids: params.clinicIds.join(','),
      category: params.category,
    })}`,
    { signal },
  );
}

export function fetchPriceHistory(
  serviceId: string,
  params: { clinic_id?: string; city?: string; days?: number } = {},
  signal?: AbortSignal,
): Promise<PriceHistoryResponse> {
  return requestJson<PriceHistoryResponse>(
    `/services/${encodeURIComponent(serviceId)}/price-history${buildQuery(params)}`,
    { signal },
  );
}

// --- Admin endpoints ---

export function fetchAdminStats(
  adminToken: string,
  signal?: AbortSignal,
): Promise<AdminStatsResponse> {
  return requestJson<AdminStatsResponse>('/admin/stats', { adminToken, signal });
}

export function fetchAdminSources(
  adminToken: string,
  signal?: AbortSignal,
): Promise<SourceInfo[]> {
  return requestJson<SourceInfo[]>('/admin/sources', { adminToken, signal });
}

export function fetchAdminRuns(
  adminToken: string,
  limit = 20,
  signal?: AbortSignal,
): Promise<ScrapeRunDTO[]> {
  return requestJson<ScrapeRunDTO[]>(`/admin/scrape-runs${buildQuery({ limit })}`, {
    adminToken,
    signal,
  });
}

export function fetchAdminErrors(
  adminToken: string,
  limit = 50,
  signal?: AbortSignal,
): Promise<ScrapeErrorDTO[]> {
  return requestJson<ScrapeErrorDTO[]>(`/admin/scrape-errors${buildQuery({ limit })}`, {
    adminToken,
    signal,
  });
}

export function fetchAdminUnmatched(
  adminToken: string,
  params: { status?: UnmatchedStatus; page?: number; page_size?: number } = {},
  signal?: AbortSignal,
): Promise<AdminUnmatchedListResponse> {
  return requestJson<AdminUnmatchedListResponse>(
    `/admin/unmatched${buildQuery({
      status: params.status ?? 'pending',
      page: params.page ?? 1,
      page_size: params.page_size ?? 20,
    })}`,
    { adminToken, signal },
  );
}

export function triggerAdminScrape(
  adminToken: string,
  body: { source_ids?: string[] | null; limit?: number | null; normalize?: boolean },
): Promise<AdminTriggerScrapeResponse> {
  return requestJson<AdminTriggerScrapeResponse>('/admin/scrape-runs', {
    method: 'POST',
    adminToken,
    body,
  });
}

export function resolveAdminUnmatched(
  adminToken: string,
  unmatchedId: string,
  serviceId: string,
  addAsSynonym = true,
): Promise<AdminResolveUnmatchedResponse> {
  return requestJson<AdminResolveUnmatchedResponse>(
    `/admin/unmatched/${encodeURIComponent(unmatchedId)}/resolve`,
    {
      method: 'POST',
      adminToken,
      body: { service_id: serviceId, add_as_synonym: addAsSynonym },
    },
  );
}

export function ignoreAdminUnmatched(
  adminToken: string,
  unmatchedId: string,
): Promise<AdminUnmatchedItem> {
  return requestJson<AdminUnmatchedItem>(
    `/admin/unmatched/${encodeURIComponent(unmatchedId)}/ignore`,
    {
      method: 'POST',
      adminToken,
    },
  );
}

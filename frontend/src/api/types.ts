export type ServiceCategory = 'lab' | 'doctor' | 'diagnostics' | 'procedure';

export type OfferSortBy =
  | 'price_asc'
  | 'price_desc'
  | 'distance_asc'
  | 'updated_desc'
  | 'rating_desc';

export type UnmatchedStatus = 'pending' | 'mapped' | 'ignored';

export interface ApiErrorBody {
  error: {
    code: string;
    message: string;
    details: unknown;
  };
}

export interface PaginationMeta {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
}

export interface HealthResponse {
  status: string;
  database: string;
}

export interface CityFilterMeta {
  name: string;
  clinics_count: number;
  offers_count: number;
}

export interface CategoryFilterMeta {
  code: ServiceCategory;
  label_ru: string;
  offers_count: number;
}

export interface FiltersMetaResponse {
  cities: CityFilterMeta[];
  categories: CategoryFilterMeta[];
  price_min_kzt: number | null;
  price_max_kzt: number | null;
  last_updated_at: string | null;
}

export interface ServiceAutocompleteItem {
  service_id: string;
  code: string;
  canonical_name: string;
  category: ServiceCategory;
  matched_synonym: string | null;
  offers_count: number;
  min_price_kzt: number | null;
}

export interface ServiceAutocompleteResponse {
  items: ServiceAutocompleteItem[];
}

export interface ClinicSummary {
  id: string;
  source_id: string;
  clinic_name: string;
  city: string;
  address: string | null;
  phone: string | null;
  working_hours: string | null;
  latitude: number | null;
  longitude: number | null;
  rating: number | null;
  has_online_booking: boolean;
  website_url: string | null;
  route_2gis_url: string;
  route_google_maps_url: string;
}

export interface OfferSearchItem {
  offer_id: string;
  service_id: string;
  service_code: string;
  canonical_name: string;
  service_name_raw: string;
  category: ServiceCategory;
  price_kzt: number;
  original_price: number;
  currency: 'KZT' | 'USD';
  duration_days: number | null;
  parsed_at: string;
  source_id: string;
  source_url: string;
  distance_km: number | null;
  clinic: ClinicSummary;
}

export interface OfferSearchSummary {
  min_price_kzt: number | null;
  max_price_kzt: number | null;
  avg_price_kzt: number | null;
}

export interface OfferSearchResponse {
  items: OfferSearchItem[];
  summary: OfferSearchSummary;
  pagination: PaginationMeta;
}

export interface ClinicListItem extends ClinicSummary {
  offers_count: number;
  min_price_kzt: number | null;
}

export interface ClinicListResponse {
  items: ClinicListItem[];
  pagination: PaginationMeta;
}

export interface ClinicOfferItem {
  offer_id: string;
  service_id: string;
  service_code: string;
  canonical_name: string;
  service_name_raw: string;
  category: ServiceCategory;
  price_kzt: number;
  duration_days: number | null;
  parsed_at: string;
  source_url: string;
}

export interface ClinicDetail extends ClinicSummary {
  updated_at: string;
  offers: ClinicOfferItem[];
}

export interface CompareCell {
  offer_id: string;
  price_kzt: number;
  duration_days: number | null;
  parsed_at: string;
  source_url: string;
}

export interface CompareRow {
  service_id: string;
  service_code: string;
  canonical_name: string;
  category: ServiceCategory;
  cheapest_clinic_id: string | null;
  cells: Record<string, CompareCell | null>;
}

export interface CompareMatrixResponse {
  clinics: ClinicSummary[];
  rows: CompareRow[];
}

export interface PriceHistoryPointItem {
  recorded_at: string;
  price_kzt: number;
  clinic_id: string;
  clinic_name: string;
  city: string;
}

export interface PriceHistoryResponse {
  service_id: string;
  service_code: string;
  canonical_name: string;
  points: PriceHistoryPointItem[];
}

export interface SourceInfo {
  source_id: string;
  display_name: string;
  supported_format: string;
  cities: string[];
  enabled: boolean;
}

export interface ScrapeRunDTO {
  id: string;
  source_id: string;
  triggered_by: 'manual' | 'cron';
  status: 'running' | 'success' | 'partial' | 'failed';
  started_at: string;
  finished_at: string | null;
  records_fetched: number;
  records_inserted: number;
  records_updated: number;
  errors_count: number;
}

export interface ScrapeErrorDTO {
  id: string;
  run_id: string;
  source_id: string;
  url: string | null;
  error_type: string;
  message: string;
  details: Record<string, unknown> | null;
  occurred_at: string;
}

export interface AdminStatsResponse {
  catalog_services: number;
  clinics: number;
  offers_total: number;
  offers_active: number;
  price_history_points: number;
  unmatched_pending: number;
}

export interface AdminUnmatchedItem {
  id: string;
  raw_record_id: string;
  source_id: string;
  clinic_name_raw: string;
  city_raw: string;
  service_name_raw: string;
  category_hint: string | null;
  price_kzt: number;
  suggested_service_id: string | null;
  suggested_service_name: string | null;
  suggested_score: number | null;
  status: UnmatchedStatus;
  resolved_service_id: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface AdminUnmatchedListResponse {
  items: AdminUnmatchedItem[];
  pagination: PaginationMeta;
}

export interface NormalizationSummary {
  records_processed: number;
  matched_count: number;
  unmatched_count: number;
  clinics_upserted: number;
  offers_inserted: number;
  offers_updated: number;
  price_history_points_added: number;
  skipped_errors: number;
}

export interface AdminTriggerScrapeResponse {
  runs: ScrapeRunDTO[];
  normalization_summary: NormalizationSummary | null;
}

export interface AdminResolveUnmatchedResponse {
  offer_id: string;
  clinic_id: string;
  service_id: string;
  price_kzt: number;
  is_active: boolean;
}

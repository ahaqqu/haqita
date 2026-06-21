/**
 * Shared TypeScript type definitions for the Haqita Cloudflare Pages API.
 *
 * All types are explicit — no `any` is used anywhere in this file.
 */

/** D1 / R2 bindings available in every Hono request context. */
export interface Bindings {
  DB: D1Database;
  IMAGES: R2Bucket;
  SCRAPER_SECRET: string;
}

/** Product payload returned by the public API. */
export interface ProductResponse {
  key: string;
  name: string;
  brand: string | null;
  unit: string;
  unit_type: string | null;
  unit_value_g: number | null;
  stores: StoreEntry[];
  price_min: number;
  price_max: number;
  cheapest_store: string | null;
  price_gap: number;
  has_promo: boolean;
  valid_until: string | null;
}

/** A single store pricing entry embedded inside a ProductResponse. */
export interface StoreEntry {
  store: string;
  price: number;
  effective_unit_price: number;
  bundle_size: number;
  promo: string[] | null;
  promo_type: string | null;
  valid_from: string | null;
  valid_until: string | null;
  image_path: string | null;
  image_r2_url: string | null;
  standardized_promo: StandardizedPromo | null;
}

/** Normalized promo metadata produced by the consolidation pipeline. */
export interface StandardizedPromo {
  normalized: string[];
  types: string[];
  best_type: string;
  discount_pct: number | null;
  max_qty: number | null;
  display_summary: string;
}

/** Generic paginated envelope used across list endpoints. */
export interface PaginatedResponse<T> {
  data: T[];
  pagination: {
    limit: number;
    cursor: string | null;
    has_more: boolean;
  };
}

/** Standard JSON error body. */
export interface ErrorResponse {
  error: string;
  message: string;
}

/** Store metadata returned by the stores endpoint. */
export interface StoreResponse {
  name: string;
  color: string | null;
}

/** Promo catalog entry returned by the promos endpoint. */
export interface PromoResponse {
  key: string;
  display: string;
  type: string | null;
  discount_pct: number | null;
  product_count: number;
  stores: Record<string, number>;
  example_products: string[];
}

/** Brochure metadata derived from price rows that link to an image. */
export interface BrochureResponse {
  image_path: string;
  store: string;
  date: string;
  product_count: number;
  product_keys: string[];
}

/** Summary statistics returned by the stats endpoint. */
export interface StatsResponse {
  total_products_lotte: number;
  total_products_superindo: number;
  matched_across_stores: number;
  lotte_only: number;
  superindo_only: number;
  total_products: number;
}

/** Price row response returned by the prices endpoint. */
export interface PriceResponse {
  product_key: string;
  store: string;
  price: number;
  effective_unit_price: number;
  bundle_size: number;
  promo: string[] | null;
  promo_type: string | null;
  valid_from: string | null;
  valid_until: string | null;
  image_path: string | null;
  image_r2_url: string | null;
  date: string;
  scrape_time: string;
  match_method: string | null;
  match_confidence: number | null;
  standardized_promo: StandardizedPromo | null;
}

/** A single historical price snapshot for the history endpoint. */
export interface HistorySnapshot {
  store: string;
  price: number;
  effective_unit_price: number;
  bundle_size: number;
  promo: string[] | null;
  promo_type: string | null;
  valid_from: string | null;
  valid_until: string | null;
  image_path: string | null;
  image_r2_url: string | null;
  date: string;
  scrape_time: string;
  match_method: string | null;
  match_confidence: number | null;
  standardized_promo: StandardizedPromo | null;
}

/** Price history response for a single product. */
export interface HistoryResponse {
  product_key: string;
  snapshots: HistorySnapshot[];
}

/** Search results response. */
export interface SearchResponse {
  data: ProductResponse[];
  query: string;
  count: number;
}

/** Per-table upsert counts reported by the sync batch endpoint. */
export interface SyncBatchTableCounts {
  inserted: number;
  updated: number;
  skipped: number;
}

/** Response body returned by POST /api/v1/sync/batch. */
export interface SyncBatchResponse {
  sync_run_id: string;
  counts: {
    stores: SyncBatchTableCounts;
    products: SyncBatchTableCounts;
    prices: SyncBatchTableCounts;
    promos: SyncBatchTableCounts;
  };
}

/** Response body returned by POST /api/v1/sync/images. */
export interface SyncImagesResponse {
  updated: number;
  skipped: number;
}

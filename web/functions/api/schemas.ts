import { z } from 'zod';

/**
 * Shared Zod schemas for query parameter validation.
 *
 * Query parameters arrive as strings, so numeric params use `z.coerce.number()`.
 */

/** Pagination helpers shared by most list endpoints. */
export const paginationSchema = z.object({
  limit: z.coerce.number().int().min(1).max(100).default(20),
  cursor: z.string().optional(),
});

/** GET /api/v1/products query parameters. */
export const productsQuerySchema = z.object({
  limit: z.coerce.number().int().min(1).max(100).default(20),
  cursor: z.string().optional(),
  store: z.string().optional(),
  category: z.string().optional(),
  has_promo: z.enum(['true', 'false']).optional(),
  sort: z.enum(['name', 'cheapest', 'savings', 'expiry']).default('name'),
});

/** GET /api/v1/products/:key/history query parameters. */
export const historyQuerySchema = z.object({
  from: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  to: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  store: z.string().optional(),
});

/** GET /api/v1/prices query parameters. */
export const pricesQuerySchema = z.object({
  limit: z.coerce.number().int().min(1).max(100).default(20),
  cursor: z.string().optional(),
  product_key: z.string().optional(),
  store: z.string().optional(),
});

/** GET /api/v1/search query parameters. */
export const searchQuerySchema = z.object({
  q: z.string().min(1).max(200),
  limit: z.coerce.number().int().min(1).max(50).default(20),
});

/** Single store payload within a sync batch. */
const syncStoreSchema = z.object({
  name: z.string(),
  color: z.string().nullable().optional(),
});

/** Single product payload within a sync batch. */
const syncProductSchema = z.object({
  key: z.string(),
  name: z.string(),
  brand: z.string().nullable().optional(),
  category: z.string().nullable().optional(),
  unit: z.string(),
  unit_type: z.string().nullable().optional(),
  unit_value_g: z.number().nullable().optional(),
});

/** Single price payload within a sync batch. */
const syncPriceSchema = z.object({
  product_key: z.string(),
  store: z.string(),
  price: z.number(),
  effective_unit_price: z.number(),
  bundle_size: z.number(),
  promo: z.unknown().nullable().optional(),
  promo_type: z.string().nullable().optional(),
  valid_from: z.string().nullable().optional(),
  valid_until: z.string().nullable().optional(),
  image_path: z.string().nullable().optional(),
  scrape_time: z.string(),
  date: z.string(),
  match_method: z.string().nullable().optional(),
  match_confidence: z.number().nullable().optional(),
  standardized_promo: z.unknown().nullable().optional(),
});

/** Single promo catalog payload within a sync batch. */
const syncPromoSchema = z.object({
  key: z.string(),
  display: z.string(),
  type: z.string().nullable().optional(),
  discount_pct: z.number().nullable().optional(),
  max_qty: z.number().nullable().optional(),
  product_count: z.number(),
  stores: z.record(z.number()),
  example_products: z.array(z.string()),
});

/** POST /api/v1/sync/batch request body. */
export const syncBatchSchema = z.object({
  stores: z.array(syncStoreSchema).default([]),
  products: z.array(syncProductSchema).default([]),
  prices: z.array(syncPriceSchema).default([]),
  promos: z.array(syncPromoSchema).default([]),
});

/** Single image mapping payload within a sync images request. */
const syncImageSchema = z.object({
  image_path: z.string(),
  image_r2_url: z.string(),
});

/** POST /api/v1/sync/images request body. */
export const syncImagesSchema = z.object({
  images: z.array(syncImageSchema).min(1),
});

/**
 * Decode a base64-encoded JSON cursor into a numeric offset.
 * Returns 0 if the cursor is malformed.
 */
export function decodeCursor(cursor: string): number {
  try {
    const decoded = atob(cursor);
    const parsed = JSON.parse(decoded) as { offset?: unknown };
    if (typeof parsed.offset === 'number') return parsed.offset;
    return 0;
  } catch {
    return 0;
  }
}

/**
 * Encode a numeric offset into a base64 JSON cursor.
 */
export function encodeCursor(offset: number): string {
  return btoa(JSON.stringify({ offset }));
}

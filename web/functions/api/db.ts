/**
 * D1 query helpers for the Haqita API.
 *
 * Every query uses `db.prepare().bind()` for parameterization.
 * No user-supplied values are ever interpolated into SQL strings.
 */

import type { StatsResponse } from './types';

/**
 * Build the WHERE clause fragment for dummy_data filtering.
 * When showDummy is false/undefined, return only real data (dummy_data=0).
 * When showDummy is true, return only dummy data (dummy_data=1).
 */
function dummyDataClause(showDummy: boolean | undefined, tableAlias: string): string {
  if (showDummy === true) return `${tableAlias}.dummy_data = 1`;
  return `${tableAlias}.dummy_data = 0`;
}

/** Raw price row as stored in the `prices` table. */
export interface PriceRow {
  product_key: string;
  store: string;
  price: number;
  effective_unit_price: number;
  bundle_size: number;
  promo: string | null;
  promo_type: string | null;
  valid_from: string | null;
  valid_until: string | null;
  image_path: string | null;
  image_r2_url: string | null;
  scrape_time: string;
  date: string;
  match_method: string | null;
  match_confidence: number | null;
  standardized_promo: string | null;
}

/** Raw product row as stored in the `products` table. */
export interface ProductRow {
  key: string;
  name: string;
  brand: string | null;
  unit: string;
  unit_type: string | null;
  unit_value_g: number | null;
  category: string | null;
}

/** Promo catalog row returned by `getPromos`. */
interface PromoCatalogRow {
  key: string;
  display: string;
  type: string | null;
  discount_pct: number | null;
  max_qty: number | null;
  product_count: number;
  stores: Record<string, number>;
  example_products: string[];
}

/** Brochure aggregation row returned by `getBrochures`. */
interface BrochureCatalogRow {
  image_path: string;
  store: string;
  date: string;
  product_count: number;
  product_keys: string[];
}

/** Minimal shape for `db.prepare(...).bind(...).all()` results. */
interface D1AllResult<T> {
  results?: T[];
}

/** Safely parse a JSON string; return null on empty input or parse failure. */
function safeJsonParse<T>(value: string | null): T | null {
  if (value === null || value === undefined || value === '') return null;
  try {
    return JSON.parse(value) as T;
  } catch {
    return null;
  }
}

/**
 * Get a paginated list of products with optional filters and sorting.
 *
 * Sorting options:
 *   - 'name'     → alphabetical by product name
 *   - 'cheapest' → lowest current price first
 *   - 'savings'  → largest price gap first
 *   - 'expiry'   → earliest promo expiry first
 */
export async function getProducts(
  db: D1Database,
  opts: {
    limit: number;
    offset: number;
    sort: string;
    store?: string;
    category?: string;
    has_promo?: boolean;
    showDummy?: boolean;
  }
): Promise<{ products: ProductRow[]; total: number }> {
  const params: (string | number | boolean)[] = [];
  const countParams: (string | number | boolean)[] = [];
  const conditions: string[] = [];
  const countConditions: string[] = [];

  if (opts.store !== undefined && opts.store !== '') {
    const clause = 'EXISTS (SELECT 1 FROM prices WHERE product_key = p.key AND store = ?)';
    conditions.push(clause);
    countConditions.push(clause);
    params.push(opts.store);
    countParams.push(opts.store);
  }

  if (opts.category !== undefined && opts.category !== '') {
    conditions.push('p.category = ?');
    countConditions.push('p.category = ?');
    params.push(opts.category);
    countParams.push(opts.category);
  }

  if (opts.has_promo === true) {
    const clause = `EXISTS (SELECT 1 FROM prices WHERE product_key = p.key AND promo IS NOT NULL${opts.showDummy !== undefined ? ` AND ${dummyDataClause(opts.showDummy, '')}` : ''})`;
    conditions.push(clause);
    countConditions.push(clause);
  } else if (opts.has_promo === false) {
    const clause = `NOT EXISTS (SELECT 1 FROM prices WHERE product_key = p.key AND promo IS NOT NULL${opts.showDummy !== undefined ? ` AND ${dummyDataClause(opts.showDummy, '')}` : ''})`;
    conditions.push(clause);
    countConditions.push(clause);
  }

  // Filter by dummy_data
  conditions.push(dummyDataClause(opts.showDummy, 'p'));
  countConditions.push(dummyDataClause(opts.showDummy, 'p'));

  const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
  const countWhere = countConditions.length > 0 ? `WHERE ${countConditions.join(' AND ')}` : '';

  const orderByMap: Record<string, string> = {
    name: 'p.name ASC',
    cheapest: 'CASE WHEN price_min IS NULL THEN 1 ELSE 0 END, price_min ASC',
    savings: 'CASE WHEN price_gap IS NULL THEN 1 ELSE 0 END, price_gap DESC',
    expiry: 'CASE WHEN earliest_valid_until IS NULL THEN 1 ELSE 0 END, earliest_valid_until ASC',
  };
  const orderBy = orderByMap[opts.sort] ?? orderByMap.name;

  const selectSql = `
    SELECT
      p.*,
      (SELECT MIN(price) FROM prices WHERE product_key = p.key) AS price_min,
      (SELECT MAX(price) - MIN(price) FROM prices WHERE product_key = p.key) AS price_gap,
      (SELECT MIN(valid_until) FROM prices WHERE product_key = p.key AND valid_until IS NOT NULL) AS earliest_valid_until
    FROM products p
    ${where}
    ORDER BY ${orderBy}
    LIMIT ? OFFSET ?
  `;

  const countSql = `SELECT COUNT(*) AS total FROM products p ${countWhere}`;

  params.push(opts.limit, opts.offset);

  const [productsResult, countResult] = await Promise.all([
    db.prepare(selectSql).bind(...params).all() as Promise<D1AllResult<ProductRow>>,
    db.prepare(countSql).bind(...countParams).all() as Promise<D1AllResult<{ total: number }>>,
  ]);

  const products = productsResult.results ?? [];
  const countRow = countResult.results?.[0];
  const total = countRow?.total ?? 0;

  return { products, total };
}

/**
 * Fetch the latest price row for each store for a set of product keys.
 */
export async function getLatestPricesForProducts(
  db: D1Database,
  productKeys: string[],
  showDummy?: boolean
): Promise<PriceRow[]> {
  if (productKeys.length === 0) return [];

  const placeholders = productKeys.map(() => '?').join(',');
  const sql = `
    SELECT pr.*
    FROM prices pr
    WHERE pr.product_key IN (${placeholders})
      AND pr.date = (
        SELECT MAX(date)
        FROM prices
        WHERE product_key = pr.product_key AND store = pr.store
      )
      AND ${dummyDataClause(showDummy, 'pr')}
  `;

  const result = await db
    .prepare(sql)
    .bind(...productKeys)
    .all() as D1AllResult<PriceRow>;

  return result.results ?? [];
}

/** Fetch a single product by its unique key. */
export async function getProductByKey(
  db: D1Database,
  key: string
): Promise<ProductRow | null> {
  const row = await db
    .prepare('SELECT key, name, brand, unit, unit_type, unit_value_g, category FROM products WHERE key = ? LIMIT 1')
    .bind(key)
    .first() as ProductRow | null;
  return row;
}

/**
 * Get historical price rows for a product, optionally filtered by date range and store.
 */
export async function getPriceHistory(
  db: D1Database,
  productKey: string,
  opts: { from?: string; to?: string; store?: string }
): Promise<PriceRow[]> {
  const sql = `
    SELECT product_key, store, price, effective_unit_price, bundle_size, promo, promo_type,
           valid_from, valid_until, image_path, image_r2_url, scrape_time, date,
           match_method, match_confidence, standardized_promo
    FROM prices
    WHERE product_key = ?
      AND (? IS NULL OR date >= ?)
      AND (? IS NULL OR date <= ?)
      AND (? IS NULL OR store = ?)
    ORDER BY date ASC
  `;

  const result = await db
    .prepare(sql)
    .bind(
      productKey,
      opts.from ?? null,
      opts.from ?? null,
      opts.to ?? null,
      opts.to ?? null,
      opts.store ?? null,
      opts.store ?? null
    )
    .all() as D1AllResult<PriceRow>;

  return result.results ?? [];
}

/** Get all configured stores. */
export async function getStores(
  db: D1Database,
  showDummy?: boolean
): Promise<{ name: string; color: string | null }[]> {
  const result = await db
    .prepare(`SELECT name, color FROM stores WHERE ${dummyDataClause(showDummy, '')} ORDER BY name`)
    .all() as D1AllResult<{ name: string; color: string | null }>;

  return result.results ?? [];
}

/** Get all non-null product categories in alphabetical order. */
export async function getCategories(db: D1Database): Promise<string[]> {
  const result = await db
    .prepare('SELECT DISTINCT category FROM products WHERE category IS NOT NULL ORDER BY category')
    .all() as D1AllResult<{ category: string }>;

  const rows = result.results ?? [];
  return rows.map((row) => row.category);
}

/** Search products by name, brand, or unit. */
export async function searchProducts(
  db: D1Database,
  query: string,
  limit: number
): Promise<ProductRow[]> {
  const pattern = `%${query}%`;
  const result = await db
    .prepare('SELECT key, name, brand, unit, unit_type, unit_value_g, category FROM products WHERE name LIKE ? OR brand LIKE ? OR unit LIKE ? ORDER BY name LIMIT ?')
    .bind(pattern, pattern, pattern, limit)
    .all() as D1AllResult<ProductRow>;

  return result.results ?? [];
}

/** Get the promo catalog with parsed JSON columns. */
export async function getPromos(db: D1Database, showDummy?: boolean): Promise<PromoCatalogRow[]> {
  const result = await db
    .prepare(`SELECT key, display, type, discount_pct, max_qty, product_count, stores, example_products FROM promos WHERE ${dummyDataClause(showDummy, '')} ORDER BY product_count DESC`)
    .all() as D1AllResult<{
      key: string;
      display: string;
      type: string | null;
      discount_pct: number | null;
      max_qty: number | null;
      product_count: number;
      stores: string | null;
      example_products: string | null;
    }>;

  const rows = result.results ?? [];
  return rows.map((row) => ({
    key: row.key,
    display: row.display,
    type: row.type,
    discount_pct: row.discount_pct,
    max_qty: row.max_qty,
    product_count: row.product_count,
    stores: safeJsonParse<Record<string, number>>(row.stores) ?? {},
    example_products: safeJsonParse<string[]>(row.example_products) ?? [],
  }));
}

/** Get brochure metadata grouped by image path, store, and date. */
export async function getBrochures(db: D1Database, showDummy?: boolean): Promise<BrochureCatalogRow[]> {
  const result = await db
    .prepare(
      `SELECT image_path, store, date, COUNT(*) AS product_count, GROUP_CONCAT(product_key) AS product_keys
       FROM prices
       WHERE image_path IS NOT NULL AND ${dummyDataClause(showDummy, '')}
       GROUP BY image_path, store, date
       ORDER BY store, date DESC`
    )
    .all() as D1AllResult<{
      image_path: string;
      store: string;
      date: string;
      product_count: number;
      product_keys: string | null;
    }>;

  const rows = result.results ?? [];
  return rows.map((row) => ({
    image_path: row.image_path,
    store: row.store,
    date: row.date,
    product_count: row.product_count,
    product_keys: row.product_keys?.split(',') ?? [],
  }));
}

/** Get summary statistics across products and prices. */
export async function getStats(db: D1Database, showDummy?: boolean): Promise<StatsResponse> {
  const sql = `
    SELECT
      (SELECT COUNT(DISTINCT product_key) FROM prices WHERE store = 'Lotte' AND ${dummyDataClause(showDummy, '')}) AS total_products_lotte,
      (SELECT COUNT(DISTINCT product_key) FROM prices WHERE store = 'Superindo' AND ${dummyDataClause(showDummy, '')}) AS total_products_superindo,
      (SELECT COUNT(*) FROM (
        SELECT product_key FROM prices WHERE ${dummyDataClause(showDummy, '')} GROUP BY product_key HAVING COUNT(DISTINCT store) >= 2
      )) AS matched_across_stores,
      (SELECT COUNT(*) FROM products p
       WHERE ${dummyDataClause(showDummy, 'p')}
         AND EXISTS (SELECT 1 FROM prices WHERE product_key = p.key AND store = 'Lotte' AND ${dummyDataClause(showDummy, '')})
         AND NOT EXISTS (SELECT 1 FROM prices WHERE product_key = p.key AND store = 'Superindo' AND ${dummyDataClause(showDummy, '')})
      ) AS lotte_only,
      (SELECT COUNT(*) FROM products p
       WHERE ${dummyDataClause(showDummy, 'p')}
         AND EXISTS (SELECT 1 FROM prices WHERE product_key = p.key AND store = 'Superindo' AND ${dummyDataClause(showDummy, '')})
         AND NOT EXISTS (SELECT 1 FROM prices WHERE product_key = p.key AND store = 'Lotte' AND ${dummyDataClause(showDummy, '')})
      ) AS superindo_only,
      (SELECT COUNT(*) FROM products WHERE ${dummyDataClause(showDummy, '')}) AS total_products
  `;

  const row = await db.prepare(sql).first() as {
    total_products_lotte: number;
    total_products_superindo: number;
    matched_across_stores: number;
    lotte_only: number;
    superindo_only: number;
    total_products: number;
  } | null;

  return {
    total_products_lotte: row?.total_products_lotte ?? 0,
    total_products_superindo: row?.total_products_superindo ?? 0,
    matched_across_stores: row?.matched_across_stores ?? 0,
    lotte_only: row?.lotte_only ?? 0,
    superindo_only: row?.superindo_only ?? 0,
    total_products: row?.total_products ?? 0,
  };
}

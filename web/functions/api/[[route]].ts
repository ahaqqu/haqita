import { Hono } from 'hono';
import { handle } from 'hono/cloudflare-pages';
import type { Context } from 'hono';
import type { ContentfulStatusCode } from 'hono/utils/http-status';

import {
  productsQuerySchema,
  historyQuerySchema,
  pricesQuerySchema,
  searchQuerySchema,
  syncBatchSchema,
  syncImagesSchema,
  decodeCursor,
  encodeCursor,
} from './schemas';
import {
  getProducts,
  getLatestPricesForProducts,
  getProductByKey,
  getPriceHistory,
  getStores,
  getCategories,
  searchProducts,
  getPromos,
  getBrochures,
  getStats,
  type PriceRow,
  type ProductRow,
} from './db';
import { authMiddleware } from './middleware/auth';
import { securityHeadersMiddleware } from './middleware/security';
import type {
  Bindings,
  ProductResponse,
  StoreEntry,
  StandardizedPromo,
  PaginatedResponse,
  ErrorResponse,
  PriceResponse,
  HistoryResponse,
  SearchResponse,
  SyncBatchResponse,
  SyncImagesResponse,
  SyncImagesError,
} from './types';

const app = new Hono<{ Bindings: Bindings }>().basePath('/api');

// Apply security headers to all responses
app.use('*', securityHeadersMiddleware);

/** Safely parse a JSON column; return null on empty input or parse failure. */
function safeJsonParse<T>(value: string | null): T | null {
  if (value === null || value === undefined || value === '') return null;
  try {
    return JSON.parse(value) as T;
  } catch {
    return null;
  }
}

/** Build a ProductResponse from a product row and its latest price rows. */
function buildProductResponse(product: ProductRow, prices: PriceRow[]): ProductResponse {
  const stores: StoreEntry[] = prices.map((price) => {
    const promo = safeJsonParse<string[]>(price.promo);
    const standardizedPromo = safeJsonParse<StandardizedPromo>(price.standardized_promo);

    return {
      store: price.store,
      price: price.price,
      effective_unit_price: price.effective_unit_price,
      bundle_size: price.bundle_size,
      promo,
      promo_type: price.promo_type,
      valid_from: price.valid_from,
      valid_until: price.valid_until,
      image_path: price.image_path,
      image_r2_url: price.image_r2_url,
      standardized_promo: standardizedPromo,
    };
  });

  const priceValues = prices.map((price) => price.price);
  const price_min = priceValues.length > 0 ? Math.min(...priceValues) : 0;
  const price_max = priceValues.length > 0 ? Math.max(...priceValues) : 0;
  const cheapestStoreRow = prices.find((price) => price.price === price_min);
  const cheapest_store = cheapestStoreRow?.store ?? null;
  const price_gap = price_max - price_min;
  const has_promo = prices.some((price) => price.promo !== null);

  const valid_until = prices.reduce<string | null>((earliest, price) => {
    if (price.valid_until === null) return earliest;
    if (earliest === null || price.valid_until < earliest) return price.valid_until;
    return earliest;
  }, null);

  return {
    key: product.key,
    name: product.name,
    brand: product.brand,
    unit: product.unit,
    unit_type: product.unit_type,
    unit_value_g: product.unit_value_g,
    stores,
    price_min,
    price_max,
    cheapest_store,
    price_gap,
    has_promo,
    valid_until,
  };
}

/** Return a consistent JSON error response. */
function errorResponse(c: Context, status: number, error: string, message: string) {
  return c.json<ErrorResponse>({ error, message }, status as ContentfulStatusCode);
}

/** Group latest price rows by their product key. */
function groupPricesByProductKey(prices: PriceRow[]): Map<string, PriceRow[]> {
  const map = new Map<string, PriceRow[]>();
  for (const price of prices) {
    const arr = map.get(price.product_key);
    if (arr === undefined) {
      map.set(price.product_key, [price]);
    } else {
      arr.push(price);
    }
  }
  return map;
}

/** Build a PriceResponse from a raw price row with JSON-decoded promo columns. */
function buildPriceResponse(row: PriceRow): PriceResponse {
  return {
    product_key: row.product_key,
    store: row.store,
    price: row.price,
    effective_unit_price: row.effective_unit_price,
    bundle_size: row.bundle_size,
    promo: safeJsonParse<string[]>(row.promo),
    promo_type: row.promo_type,
    valid_from: row.valid_from,
    valid_until: row.valid_until,
    image_path: row.image_path,
    image_r2_url: row.image_r2_url,
    date: row.date,
    scrape_time: row.scrape_time,
    match_method: row.match_method,
    match_confidence: row.match_confidence,
    standardized_promo: safeJsonParse<StandardizedPromo>(row.standardized_promo),
  };
}

/** Build a HistoryResponse snapshot from a raw price row. */
function buildHistorySnapshot(row: PriceRow): HistoryResponse['snapshots'][number] {
  return {
    store: row.store,
    price: row.price,
    effective_unit_price: row.effective_unit_price,
    bundle_size: row.bundle_size,
    promo: safeJsonParse<string[]>(row.promo),
    promo_type: row.promo_type,
    valid_from: row.valid_from,
    valid_until: row.valid_until,
    image_path: row.image_path,
    image_r2_url: row.image_r2_url,
    date: row.date,
    scrape_time: row.scrape_time,
    match_method: row.match_method,
    match_confidence: row.match_confidence,
    standardized_promo: safeJsonParse<StandardizedPromo>(row.standardized_promo),
  };
}

// Health check (from Phase 1)
app.get('/health', (c) => {
  return c.json({ status: 'ok', timestamp: new Date().toISOString() });
});

// Read endpoints (Phase 3)

app.get('/v1/stores', async (c) => {
  const showDummy = c.req.query('show_dummy') === 'true';
  const stores = await getStores(c.env.DB, showDummy);
  return c.json({ data: stores });
});

app.get('/v1/categories', async (c) => {
  const categories = await getCategories(c.env.DB);
  return c.json({ data: categories });
});

app.get('/v1/stats', async (c) => {
  const showDummy = c.req.query('show_dummy') === 'true';
  const stats = await getStats(c.env.DB, showDummy);
  return c.json(stats);
});

app.get('/v1/products', async (c) => {
  const parseResult = productsQuerySchema.safeParse(c.req.query());
  if (!parseResult.success) {
    return errorResponse(c, 400, 'Invalid query', parseResult.error.message);
  }

  const query = parseResult.data;
  const offset = decodeCursor(query.cursor ?? '');
  const hasPromo =
    query.has_promo === 'true' ? true : query.has_promo === 'false' ? false : undefined;
  const showDummy = query.show_dummy === 'true' ? true : undefined;

  const { products, total } = await getProducts(c.env.DB, {
    limit: query.limit,
    offset,
    sort: query.sort,
    store: query.store,
    category: query.category,
    has_promo: hasPromo,
    showDummy,
  });

  const productKeys = products.map((product) => product.key);
  const priceRows = await getLatestPricesForProducts(c.env.DB, productKeys, showDummy);
  const priceMap = groupPricesByProductKey(priceRows);

  const data = products.map((product) =>
    buildProductResponse(product, priceMap.get(product.key) ?? [])
  );

  const hasMore = offset + products.length < total;
  const nextCursor = hasMore ? encodeCursor(offset + products.length) : null;

  return c.json<PaginatedResponse<ProductResponse>>({
    data,
    pagination: { limit: query.limit, cursor: nextCursor, has_more: hasMore },
  });
});

app.get('/v1/products/:key', async (c) => {
  const key = c.req.param('key') ?? '';
  if (key === '') {
    return errorResponse(c, 404, 'Not found', 'Product key is required');
  }

  const product = await getProductByKey(c.env.DB, key);
  if (product === null) {
    return errorResponse(c, 404, 'Not found', `Product ${key} not found`);
  }

  const showDummy = c.req.query('show_dummy') === 'true' || undefined;
  const prices = await getLatestPricesForProducts(c.env.DB, [key], showDummy);
  return c.json(buildProductResponse(product, prices));
});

app.get('/v1/products/:key/history', async (c) => {
  const key = c.req.param('key') ?? '';
  if (key === '') {
    return errorResponse(c, 404, 'Not found', 'Product key is required');
  }

  const product = await getProductByKey(c.env.DB, key);
  if (product === null) {
    return errorResponse(c, 404, 'Not found', `Product ${key} not found`);
  }

  const parseResult = historyQuerySchema.safeParse(c.req.query());
  if (!parseResult.success) {
    return errorResponse(c, 400, 'Invalid query', parseResult.error.message);
  }

  const query = parseResult.data;
  const rows = await getPriceHistory(c.env.DB, key, {
    from: query.from,
    to: query.to,
    store: query.store,
  });

  const snapshots = rows.map(buildHistorySnapshot);
  return c.json<HistoryResponse>({ product_key: key, snapshots });
});

app.get('/v1/prices', async (c) => {
  const parseResult = pricesQuerySchema.safeParse(c.req.query());
  if (!parseResult.success) {
    return errorResponse(c, 400, 'Invalid query', parseResult.error.message);
  }

  const query = parseResult.data;
  const limit = query.limit;
  const offset = decodeCursor(query.cursor ?? '');

  const baseParams: (string | number | null)[] = [];
  const conditions: string[] = [];

  if (query.product_key !== undefined && query.product_key !== '') {
    conditions.push('product_key = ?');
    baseParams.push(query.product_key);
  }

  if (query.store !== undefined && query.store !== '') {
    conditions.push('store = ?');
    baseParams.push(query.store);
  }

  const where = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';
  const countSql = `SELECT COUNT(*) AS total FROM prices ${where}`;
  const selectSql = `SELECT * FROM prices ${where} ORDER BY date DESC, product_key, store LIMIT ? OFFSET ?`;

  const countParams = [...baseParams];
  const selectParams = [...baseParams, limit, offset];

  const [countResult, rowsResult] = await Promise.all([
    c.env.DB.prepare(countSql).bind(...countParams).all() as Promise<{
      results?: { total: number }[];
    }>,
    c.env.DB.prepare(selectSql).bind(...selectParams).all() as Promise<{
      results?: PriceRow[];
    }>,
  ]);

  const rows = rowsResult.results ?? [];
  const total = countResult.results?.[0]?.total ?? 0;
  const hasMore = offset + rows.length < total;
  const nextCursor = hasMore ? encodeCursor(offset + rows.length) : null;

  const data = rows.map(buildPriceResponse);

  return c.json<PaginatedResponse<PriceResponse>>({
    data,
    pagination: { limit, cursor: nextCursor, has_more: hasMore },
  });
});

app.get('/v1/search', async (c) => {
  const parseResult = searchQuerySchema.safeParse(c.req.query());
  if (!parseResult.success) {
    return errorResponse(c, 400, 'Invalid query', parseResult.error.message);
  }

  const query = parseResult.data;
  const showDummy = c.req.query('show_dummy') === 'true' || undefined;
  const products = await searchProducts(c.env.DB, query.q, query.limit);
  const productKeys = products.map((product) => product.key);
  const priceRows = await getLatestPricesForProducts(c.env.DB, productKeys, showDummy);
  const priceMap = groupPricesByProductKey(priceRows);

  const data = products.map((product) =>
    buildProductResponse(product, priceMap.get(product.key) ?? [])
  );

  return c.json<SearchResponse>({ data, query: query.q, count: data.length });
});

app.get('/v1/promos', async (c) => {
  const showDummy = c.req.query('show_dummy') === 'true';
  const promos = await getPromos(c.env.DB, showDummy);
  return c.json({ data: promos });
});

app.get('/v1/brochures', async (c) => {
  const showDummy = c.req.query('show_dummy') === 'true';
  const brochures = await getBrochures(c.env.DB, showDummy);
  return c.json({ data: brochures });
});

// Sync endpoints (Phase 4)

app.post('/v1/sync/batch', authMiddleware, async (c) => {
  let body: unknown;
  try {
    body = await c.req.json();
  } catch {
    return errorResponse(c, 400, 'Invalid JSON', 'Request body must be valid JSON');
  }

  const parseResult = syncBatchSchema.safeParse(body);
  if (!parseResult.success) {
    return errorResponse(c, 400, 'Invalid body', parseResult.error.message);
  }

  const batch = parseResult.data;
  const syncRunId = batch.sync_run_id;
  const response: SyncBatchResponse = {
    sync_run_id: syncRunId,
    stores: { inserted: 0, updated: 0, skipped: 0 },
    products: { inserted: 0, updated: 0, skipped: 0 },
    prices: { inserted: 0, updated: 0, skipped: 0 },
    promos: { inserted: 0, updated: 0, skipped: 0 },
    errors: [],
  };
  const db = c.env.DB;

  for (const store of batch.stores) {
    try {
      await db
        .prepare('INSERT OR REPLACE INTO stores (name, color, dummy_data) VALUES (?, ?, ?)')
        .bind(store.name, store.color ?? null, batch.dummy_data ? 1 : 0)
        .run();
      response.stores.updated += 1;
    } catch (err) {
      response.stores.skipped += 1;
      response.errors.push({ table: 'stores', key: store.name, error: String(err) });
    }
  }

  for (const product of batch.products) {
    try {
      await db
        .prepare(
          'INSERT OR REPLACE INTO products (key, name, brand, category, unit, unit_type, unit_value_g, dummy_data) VALUES (?, ?, ?, ?, ?, ?, ?, ?)'
        )
        .bind(
          product.key,
          product.name,
          product.brand ?? null,
          product.category ?? null,
          product.unit,
          product.unit_type ?? null,
          product.unit_value_g ?? null,
          batch.dummy_data ? 1 : 0
        )
        .run();
      response.products.updated += 1;
    } catch (err) {
      response.products.skipped += 1;
      response.errors.push({ table: 'products', key: product.key, error: String(err) });
    }
  }

  for (const price of batch.prices) {
    try {
      await db
        .prepare(
          'INSERT OR REPLACE INTO prices (product_key, store, price, effective_unit_price, bundle_size, promo, promo_type, valid_from, valid_until, image_path, scrape_time, date, match_method, match_confidence, standardized_promo, dummy_data) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
        )
        .bind(
          price.product_key,
          price.store,
          price.price,
          price.effective_unit_price,
          price.bundle_size,
          price.promo !== undefined && price.promo !== null ? JSON.stringify(price.promo) : null,
          price.promo_type ?? null,
          price.valid_from ?? null,
          price.valid_until ?? null,
          price.image_path ?? null,
          price.scrape_time,
          price.date,
          price.match_method ?? null,
          price.match_confidence ?? null,
          price.standardized_promo !== undefined && price.standardized_promo !== null
            ? JSON.stringify(price.standardized_promo)
            : null,
          batch.dummy_data ? 1 : 0
        )
        .run();
      response.prices.updated += 1;
    } catch (err) {
      response.prices.skipped += 1;
      response.errors.push({ table: 'prices', key: `${price.product_key}:${price.store}:${price.date}`, error: String(err) });
    }
  }

  for (const promo of batch.promos) {
    try {
      await db
        .prepare(
          'INSERT OR REPLACE INTO promos (key, display, type, discount_pct, max_qty, product_count, stores, example_products, dummy_data) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)'
        )
        .bind(
          promo.key,
          promo.display,
          promo.type ?? null,
          promo.discount_pct ?? null,
          promo.max_qty ?? null,
          promo.product_count,
          promo.stores !== undefined ? JSON.stringify(promo.stores) : null,
          promo.example_products !== undefined ? JSON.stringify(promo.example_products) : null,
          batch.dummy_data ? 1 : 0
        )
        .run();
      response.promos.updated += 1;
    } catch (err) {
      response.promos.skipped += 1;
      response.errors.push({ table: 'promos', key: promo.key, error: String(err) });
    }
  }

  const status = response.errors.length > 0 ? 207 : 200;
  return c.json<SyncBatchResponse>(response, status as ContentfulStatusCode);
});

app.post('/v1/sync/images', authMiddleware, async (c) => {
  let body: unknown;
  try {
    body = await c.req.json();
  } catch {
    return errorResponse(c, 400, 'Invalid JSON', 'Request body must be valid JSON');
  }

  const parseResult = syncImagesSchema.safeParse(body);
  if (!parseResult.success) {
    return errorResponse(c, 400, 'Invalid body', parseResult.error.message);
  }

  const { images } = parseResult.data;
  let updated = 0;
  let skipped = 0;
  const errors: SyncImagesError[] = [];
  const db = c.env.DB;

  for (const image of images) {
    try {
      const r2Url = image.r2_url ?? `${c.env.R2_PUBLIC_URL ?? ''}/${image.r2_key}`;
      const result = await db
        .prepare('UPDATE prices SET image_r2_url = ? WHERE image_path = ?')
        .bind(r2Url, image.local_path)
        .run();
      const changes = (result.meta as { changes?: number }).changes ?? 0;
      if (changes > 0) {
        updated += 1;
      } else {
        skipped += 1;
      }
    } catch (err) {
      errors.push({ image_path: image.local_path, error: String(err) });
      skipped += 1;
    }
  }

  const status = errors.length > 0 ? 207 : 200;
  return c.json<SyncImagesResponse>({ updated, skipped, errors }, status as ContentfulStatusCode);
});

// 404 catch-all for unmatched routes
app.all('*', (c) => {
  return errorResponse(
    c,
    404,
    'Not found',
    `Route ${c.req.method} ${c.req.path} does not exist`
  );
});

export const onRequest = handle(app);

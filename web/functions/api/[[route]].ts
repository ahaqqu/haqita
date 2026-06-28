import { Hono } from "hono";
import { handle } from "hono/cloudflare-pages";
import type { Context } from "hono";
import type { ContentfulStatusCode } from "hono/utils/http-status";

import {
  productsQuerySchema,
  historyQuerySchema,
  pricesQuerySchema,
  searchQuerySchema,
  syncBatchSchema,
  syncImagesSchema,
  decodeCursor,
  encodeCursor,
} from "./schemas";
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
} from "./db";
import { authMiddleware } from "./middleware/auth";
import { securityHeadersMiddleware } from "./middleware/security";
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
} from "./types";

const app = new Hono<{ Bindings: Bindings }>().basePath("/api");

// Apply security headers to all responses
app.use("*", securityHeadersMiddleware);

/** Safely parse a JSON column; return null on empty input or parse failure. */
function safeJsonParse<T>(value: string | null): T | null {
  if (value === null || value === undefined || value === "") return null;
  try {
    return JSON.parse(value) as T;
  } catch {
    return null;
  }
}

/** Build a ProductResponse from a product row and its latest price rows. */
function buildProductResponse(
  product: ProductRow,
  prices: PriceRow[],
): ProductResponse {
  const stores: StoreEntry[] = prices.map((price) => {
    const promo = safeJsonParse<string[]>(price.promo);
    const standardizedPromo = safeJsonParse<StandardizedPromo>(
      price.standardized_promo,
    );

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
    if (earliest === null || price.valid_until < earliest)
      return price.valid_until;
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
function errorResponse(
  c: Context,
  status: number,
  error: string,
  message: string,
) {
  return c.json<ErrorResponse>(
    { error, message },
    status as ContentfulStatusCode,
  );
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
    standardized_promo: safeJsonParse<StandardizedPromo>(
      row.standardized_promo,
    ),
  };
}

/** Build a HistoryResponse snapshot from a raw price row. */
function buildHistorySnapshot(
  row: PriceRow,
): HistoryResponse["snapshots"][number] {
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
    standardized_promo: safeJsonParse<StandardizedPromo>(
      row.standardized_promo,
    ),
  };
}

/**
 * Upsert rows via db.batch() to stay within Cloudflare's per-Worker subrequest
 * limit. The free Workers plan caps a single invocation at 50 subrequests;
 * the paid plan caps at 1000. Each db.batch() call counts as ONE subrequest
 * regardless of how many prepared statements it contains, so this collapses
 * N individual prepare+bind+run calls (N subrequests) into ceil(N / CHUNK_SIZE)
 * subrequests.
 *
 * D1 batch runs in a single transaction: if any statement in the chunk fails,
 * the whole chunk rolls back and all rows in that chunk are reported as
 * errors with the batch error. We deliberately do NOT fall back to per-row
 * execution because each .run() is its own subrequest — a 100-row fallback
 * would itself exceed the free-tier 50-subrequest cap. The sync is
 * idempotent (INSERT OR REPLACE), so the caller can safely re-run to retry
 * any failed chunk.
 */
const D1_BATCH_CHUNK_SIZE = 100;

interface BatchUpsertResult {
  updated: number;
  skipped: number;
  errors: { table: string; key: string; error: string }[];
}

async function batchUpsert(
  db: D1Database,
  statements: D1PreparedStatement[],
  keys: string[],
  tableName: string,
): Promise<BatchUpsertResult> {
  const result: BatchUpsertResult = { updated: 0, skipped: 0, errors: [] };

  for (let i = 0; i < statements.length; i += D1_BATCH_CHUNK_SIZE) {
    const chunk = statements.slice(i, i + D1_BATCH_CHUNK_SIZE);
    const chunkKeys = keys.slice(i, i + D1_BATCH_CHUNK_SIZE);

    if (chunk.length === 0) continue;

    try {
      await db.batch(chunk);
      result.updated += chunk.length;
    } catch (err) {
      result.skipped += chunk.length;
      const errMsg = String(err);
      for (const key of chunkKeys) {
        result.errors.push({ table: tableName, key, error: errMsg });
      }
    }
  }

  return result;
}

// Health check (from Phase 1)
app.get("/health", (c) => {
  return c.json({ status: "ok", timestamp: new Date().toISOString() });
});

// Version endpoint — used by deploy.py to verify the deployed API is up to date
app.get("/v1/version", (c) => {
  const sha = c.env.COMMIT_SHA || c.env.CF_PAGES_COMMIT_SHA || "unknown";
  return c.json({ version: sha, deployed_at: new Date().toISOString() });
});

// Read endpoints (Phase 3)

app.get("/v1/stores", async (c) => {
  const showDummy = c.req.query("show_dummy") === "true";
  const stores = await getStores(c.env.DB, showDummy);
  return c.json({ data: stores });
});

app.get("/v1/categories", async (c) => {
  const showDummy = c.req.query("show_dummy") === "true";
  const categories = await getCategories(c.env.DB, showDummy);
  return c.json({ data: categories });
});

app.get("/v1/stats", async (c) => {
  const showDummy = c.req.query("show_dummy") === "true";
  const stats = await getStats(c.env.DB, showDummy);
  return c.json(stats);
});

app.get("/v1/products", async (c) => {
  const parseResult = productsQuerySchema.safeParse(c.req.query());
  if (!parseResult.success) {
    return errorResponse(c, 400, "Invalid query", parseResult.error.message);
  }

  const query = parseResult.data;
  const offset = decodeCursor(query.cursor ?? "");
  const hasPromo =
    query.has_promo === "true"
      ? true
      : query.has_promo === "false"
        ? false
        : undefined;
  const showDummy = query.show_dummy === "true" ? true : undefined;

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
  const priceRows = await getLatestPricesForProducts(
    c.env.DB,
    productKeys,
    showDummy,
  );
  const priceMap = groupPricesByProductKey(priceRows);

  const data = products.map((product) =>
    buildProductResponse(product, priceMap.get(product.key) ?? []),
  );

  const hasMore = offset + products.length < total;
  const nextCursor = hasMore ? encodeCursor(offset + products.length) : null;

  return c.json<PaginatedResponse<ProductResponse>>({
    data,
    pagination: { limit: query.limit, cursor: nextCursor, has_more: hasMore },
  });
});

app.get("/v1/products/:key", async (c) => {
  const key = c.req.param("key") ?? "";
  if (key === "") {
    return errorResponse(c, 404, "Not found", "Product key is required");
  }

  const product = await getProductByKey(c.env.DB, key);
  if (product === null) {
    return errorResponse(c, 404, "Not found", `Product ${key} not found`);
  }

  const showDummy = c.req.query("show_dummy") === "true" || undefined;
  const prices = await getLatestPricesForProducts(c.env.DB, [key], showDummy);
  return c.json(buildProductResponse(product, prices));
});

app.get("/v1/products/:key/history", async (c) => {
  const key = c.req.param("key") ?? "";
  if (key === "") {
    return errorResponse(c, 404, "Not found", "Product key is required");
  }

  const product = await getProductByKey(c.env.DB, key);
  if (product === null) {
    return errorResponse(c, 404, "Not found", `Product ${key} not found`);
  }

  const parseResult = historyQuerySchema.safeParse(c.req.query());
  if (!parseResult.success) {
    return errorResponse(c, 400, "Invalid query", parseResult.error.message);
  }

  const query = parseResult.data;
  const showDummy = query.show_dummy === "true" ? true : undefined;
  const rows = await getPriceHistory(
    c.env.DB,
    key,
    {
      from: query.from,
      to: query.to,
      store: query.store,
    },
    showDummy,
  );

  const snapshots = rows.map(buildHistorySnapshot);
  return c.json<HistoryResponse>({ product_key: key, snapshots });
});

app.get("/v1/prices", async (c) => {
  const parseResult = pricesQuerySchema.safeParse(c.req.query());
  if (!parseResult.success) {
    return errorResponse(c, 400, "Invalid query", parseResult.error.message);
  }

  const query = parseResult.data;
  const limit = query.limit;
  const offset = decodeCursor(query.cursor ?? "");
  const showDummy = query.show_dummy === "true" ? true : undefined;

  const baseParams: (string | number | null)[] = [];
  const conditions: string[] = [];

  if (query.product_key !== undefined && query.product_key !== "") {
    conditions.push("product_key = ?");
    baseParams.push(query.product_key);
  }

  if (query.store !== undefined && query.store !== "") {
    conditions.push("store = ?");
    baseParams.push(query.store);
  }

  conditions.push(`dummy_data = ${showDummy === true ? 1 : 0}`);

  const where =
    conditions.length > 0 ? `WHERE ${conditions.join(" AND ")}` : "";
  const countSql = `SELECT COUNT(*) AS total FROM prices ${where}`;
  const selectSql = `SELECT * FROM prices ${where} ORDER BY date DESC, product_key, store LIMIT ? OFFSET ?`;

  const countParams = [...baseParams];
  const selectParams = [...baseParams, limit, offset];

  const [countResult, rowsResult] = await Promise.all([
    c.env.DB.prepare(countSql)
      .bind(...countParams)
      .all() as Promise<{
      results?: { total: number }[];
    }>,
    c.env.DB.prepare(selectSql)
      .bind(...selectParams)
      .all() as Promise<{
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

app.get("/v1/search", async (c) => {
  const parseResult = searchQuerySchema.safeParse(c.req.query());
  if (!parseResult.success) {
    return errorResponse(c, 400, "Invalid query", parseResult.error.message);
  }

  const query = parseResult.data;
  const showDummy = c.req.query("show_dummy") === "true" || undefined;
  const products = await searchProducts(
    c.env.DB,
    query.q,
    query.limit,
    showDummy,
  );
  const productKeys = products.map((product) => product.key);
  const priceRows = await getLatestPricesForProducts(
    c.env.DB,
    productKeys,
    showDummy,
  );
  const priceMap = groupPricesByProductKey(priceRows);

  const data = products.map((product) =>
    buildProductResponse(product, priceMap.get(product.key) ?? []),
  );

  return c.json<SearchResponse>({ data, query: query.q, count: data.length });
});

app.get("/v1/promos", async (c) => {
  const showDummy = c.req.query("show_dummy") === "true";
  const promos = await getPromos(c.env.DB, showDummy);
  return c.json({ data: promos });
});

app.get("/v1/brochures", async (c) => {
  const showDummy = c.req.query("show_dummy") === "true";
  const brochures = await getBrochures(c.env.DB, showDummy);
  return c.json({ data: brochures });
});

// Sync endpoints (Phase 4)

app.post("/v1/sync/batch", authMiddleware, async (c) => {
  let body: unknown;
  try {
    body = await c.req.json();
  } catch {
    return errorResponse(
      c,
      400,
      "Invalid JSON",
      "Request body must be valid JSON",
    );
  }

  const parseResult = syncBatchSchema.safeParse(body);
  if (!parseResult.success) {
    return errorResponse(c, 400, "Invalid body", parseResult.error.message);
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
  const dummyFlag = batch.dummy_data ? 1 : 0;

  // Build prepared statements for each table, then upsert via db.batch()
  // (1 subrequest per chunk) to stay within the free-tier 50-subrequest cap.

  if (batch.stores.length > 0) {
    const stmts = batch.stores.map((s) =>
      db
        .prepare(
          "INSERT OR REPLACE INTO stores (name, color, dummy_data) VALUES (?, ?, ?)",
        )
        .bind(s.name, s.color ?? null, dummyFlag)
    );
    const keys = batch.stores.map((s) => s.name);
    const r = await batchUpsert(db, stmts, keys, "stores");
    response.stores.updated += r.updated;
    response.stores.skipped += r.skipped;
    response.errors.push(...r.errors);
  }

  if (batch.products.length > 0) {
    const stmts = batch.products.map((p) =>
      db
        .prepare(
          "INSERT OR REPLACE INTO products (key, name, brand, category, unit, unit_type, unit_value_g, dummy_data) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        )
        .bind(
          p.key,
          p.name,
          p.brand ?? null,
          p.category ?? null,
          p.unit,
          p.unit_type ?? null,
          p.unit_value_g ?? null,
          dummyFlag,
        )
    );
    const keys = batch.products.map((p) => p.key);
    const r = await batchUpsert(db, stmts, keys, "products");
    response.products.updated += r.updated;
    response.products.skipped += r.skipped;
    response.errors.push(...r.errors);
  }

  if (batch.prices.length > 0) {
    const stmts = batch.prices.map((p) =>
      db
        .prepare(
          "INSERT OR REPLACE INTO prices (product_key, store, price, effective_unit_price, bundle_size, promo, promo_type, valid_from, valid_until, image_path, scrape_time, date, match_method, match_confidence, standardized_promo, dummy_data) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        )
        .bind(
          p.product_key,
          p.store,
          p.price,
          p.effective_unit_price,
          p.bundle_size,
          p.promo !== undefined && p.promo !== null
            ? JSON.stringify(p.promo)
            : null,
          p.promo_type ?? null,
          p.valid_from ?? null,
          p.valid_until ?? null,
          p.image_path ?? null,
          p.scrape_time,
          p.date,
          p.match_method ?? null,
          p.match_confidence ?? null,
          p.standardized_promo !== undefined && p.standardized_promo !== null
            ? JSON.stringify(p.standardized_promo)
            : null,
          dummyFlag,
        )
    );
    const keys = batch.prices.map(
      (p) => `${p.product_key}:${p.store}:${p.date}`,
    );
    const r = await batchUpsert(db, stmts, keys, "prices");
    response.prices.updated += r.updated;
    response.prices.skipped += r.skipped;
    response.errors.push(...r.errors);
  }

  if (batch.promos.length > 0) {
    const stmts = batch.promos.map((p) =>
      db
        .prepare(
          "INSERT OR REPLACE INTO promos (key, display, type, discount_pct, max_qty, product_count, stores, example_products, dummy_data) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        )
        .bind(
          p.key,
          p.display,
          p.type ?? null,
          p.discount_pct ?? null,
          p.max_qty ?? null,
          p.product_count,
          p.stores !== undefined ? JSON.stringify(p.stores) : null,
          p.example_products !== undefined
            ? JSON.stringify(p.example_products)
            : null,
          dummyFlag,
        )
    );
    const keys = batch.promos.map((p) => p.key);
    const r = await batchUpsert(db, stmts, keys, "promos");
    response.promos.updated += r.updated;
    response.promos.skipped += r.skipped;
    response.errors.push(...r.errors);
  }

  const status = response.errors.length > 0 ? 207 : 200;
  return c.json<SyncBatchResponse>(response, status as ContentfulStatusCode);
});

app.post("/v1/sync/images", authMiddleware, async (c) => {
  let body: unknown;
  try {
    body = await c.req.json();
  } catch {
    return errorResponse(
      c,
      400,
      "Invalid JSON",
      "Request body must be valid JSON",
    );
  }

  const parseResult = syncImagesSchema.safeParse(body);
  if (!parseResult.success) {
    return errorResponse(c, 400, "Invalid body", parseResult.error.message);
  }

  const { images } = parseResult.data;
  let updated = 0;
  let skipped = 0;
  const errors: SyncImagesError[] = [];
  const db = c.env.DB;

  for (const image of images) {
    try {
      const r2Url =
        image.r2_url ?? `${c.env.R2_PUBLIC_URL ?? ""}/${image.r2_key}`;
      const result = await db
        .prepare("UPDATE prices SET image_r2_url = ? WHERE image_path = ?")
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
  return c.json<SyncImagesResponse>(
    { updated, skipped, errors },
    status as ContentfulStatusCode,
  );
});

// 404 catch-all for unmatched routes
app.all("*", (c) => {
  return errorResponse(
    c,
    404,
    "Not found",
    `Route ${c.req.method} ${c.req.path} does not exist`,
  );
});

export const onRequest = handle(app);

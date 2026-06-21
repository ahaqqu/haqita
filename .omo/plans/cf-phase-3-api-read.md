# Phase 3: Hono API — Public Read Endpoints

## TL;DR (For humans)

**What you'll get:** All public read API endpoints (`/api/v1/products`, `/prices`, `/stores`, `/categories`, `/search`, `/promos`, `/brochures`, `/stats`) implemented in Hono with TypeScript, Zod query validation, D1 parameterized queries, cursor-based pagination, and unit tests. Endpoints are verified via `curl` against local `wrangler dev`.

**Why this approach:** The read API must serve the same data the static `index.html` already shows, but with server-side pagination, search, and filtering that static JSON cannot do. Building all read endpoints before sync endpoints (Phase 4) lets us validate the D1 schema and query patterns against real data.

**What it will NOT do:** Implement protected sync endpoints (Phase 4), implement the Python sync script (Phase 5), update `index.html` to consume the API (Phase 6), or add security/rate limiting (Phase 7).

**Effort:** High (~6-8 hours: 10 endpoints, types, schemas, query helpers, unit tests, documentation)
**Risk:** Medium — SQL query correctness is critical; wrong joins produce incorrect product/store groupings

---

## Scope

### Must have
1. TypeScript type definitions for all API responses (`web/functions/api/types.ts`)
2. Zod schemas for query parameter validation (`web/functions/api/schemas.ts`)
3. D1 query helper functions (`web/functions/api/db.ts`)
4. All 10 GET endpoints implemented in `web/functions/api/[[route]].ts`
5. Error handling middleware (404 for unknown routes, 400 for validation errors, 500 for server errors)
6. Unit tests for query helpers and validation (`web/tests/` directory with Vitest)
7. Documentation at `docs/staging/api-read-endpoints.md`

### Must NOT have
1. No POST/PUT/DELETE endpoints — that is Phase 4
2. No authentication middleware — read endpoints are public
3. No rate limiting — that is Phase 7
4. No CORS headers — same origin in Phase 1 (plan.md:388)
5. No modifications to `index.html` — that is Phase 6
6. No `any` type — all types must be explicit
7. No raw string interpolation in SQL — all queries must use D1 `bind()` for parameterization

---

## Verification strategy
- **Test decision:** TDD for query helpers and Zod schemas + curl verification for endpoints
- **Evidence:** `curl` command outputs saved for each endpoint
- **Every endpoint** is verified with at least 2 curl commands: happy path (valid params) and failure path (invalid params)
- **Type safety** is verified via `npx tsc --noEmit`

---

## Execution strategy

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
|------|-----------|--------|---------------------|
| 1. Set up app structure (types, schemas, db) | Phase 2 | 2-7 | — |
| 2. Simple endpoints (stores, categories, stats) | 1 | 8 | 3, 4, 5, 6, 7 |
| 3. Products list with pagination | 1 | 8 | 2, 4, 5, 6, 7 |
| 4. Product detail + history | 1 | 8 | 2, 3, 5, 6, 7 |
| 5. Prices endpoint | 1 | 8 | 2, 3, 4, 6, 7 |
| 6. Search endpoint | 1 | 8 | 2, 3, 4, 5, 7 |
| 7. Promos + brochures endpoints | 1 | 8 | 2, 3, 4, 5, 6 |
| 8. Write unit tests | 2-7 | 9, 10 | — |
| 9. Write documentation | 2-7 | 10 | 8 |
| 10. Final verification | 8, 9 | — | — |

---

## Todos

### Todo 1: Set up Hono app structure (types, schemas, db helpers)

**What to do:**

Create three support files that all route handlers will import from:

**1. `web/functions/api/types.ts`** — TypeScript type definitions:
```typescript
// D1 bindings available in the Hono context
interface Bindings {
  DB: D1Database;
  IMAGES: R2Bucket;
}

// Product as returned by the API (matches active_promo.json product shape)
interface ProductResponse {
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

interface StoreEntry {
  store: string;
  price: number;
  effective_unit_price: number;
  bundle_size: number;
  promo: string[] | null;       // JSON-decoded from D1 TEXT column
  promo_type: string | null;
  valid_from: string | null;
  valid_until: string | null;
  image_path: string | null;
  image_r2_url: string | null;
  standardized_promo: StandardizedPromo | null;
}

interface StandardizedPromo {
  normalized: string[];
  types: string[];
  best_type: string;
  discount_pct: number | null;
  max_qty: number | null;
  display_summary: string;
}

interface PaginatedResponse<T> {
  data: T[];
  pagination: {
    limit: number;
    cursor: string | null;
    has_more: boolean;
  };
}

interface ErrorResponse {
  error: string;
  message: string;
}

interface StoreResponse {
  name: string;
  color: string | null;
}

interface PromoResponse {
  key: string;
  display: string;
  type: string | null;
  discount_pct: number | null;
  product_count: number;
  stores: Record<string, number>;
  example_products: string[];
}

interface BrochureResponse {
  image_path: string;
  store: string;
  date: string;
  product_count: number;
  product_keys: string[];
}

interface StatsResponse {
  total_products_lotte: number;
  total_products_superindo: number;
  matched_across_stores: number;
  lotte_only: number;
  superindo_only: number;
  total_products: number;
}
```

**2. `web/functions/api/schemas.ts`** — Zod schemas for query validation:
```typescript
import { z } from 'zod';

// Pagination
export const paginationSchema = z.object({
  limit: z.coerce.number().int().min(1).max(100).default(20),
  cursor: z.string().optional(),
});

// GET /api/v1/products query params
export const productsQuerySchema = z.object({
  limit: z.coerce.number().int().min(1).max(100).default(20),
  cursor: z.string().optional(),
  store: z.string().optional(),
  category: z.string().optional(),
  has_promo: z.enum(['true', 'false']).optional(),
  sort: z.enum(['name', 'cheapest', 'savings', 'expiry']).default('name'),
});

// GET /api/v1/products/:key/history query params
export const historyQuerySchema = z.object({
  from: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  to: z.string().regex(/^\d{4}-\d{2}-\d{2}$/).optional(),
  store: z.string().optional(),
});

// GET /api/v1/prices query params
export const pricesQuerySchema = z.object({
  limit: z.coerce.number().int().min(1).max(100).default(20),
  cursor: z.string().optional(),
  product_key: z.string().optional(),
  store: z.string().optional(),
});

// GET /api/v1/search query params
export const searchQuerySchema = z.object({
  q: z.string().min(1).max(200),
  limit: z.coerce.number().int().min(1).max(50).default(20),
});

// Helper: decode base64 cursor to offset
export function decodeCursor(cursor: string): number {
  try {
    const decoded = atob(cursor);
    const parsed = JSON.parse(decoded);
    if (typeof parsed.offset === 'number') return parsed.offset;
    return 0;
  } catch {
    return 0;
  }
}

// Helper: encode offset to base64 cursor
export function encodeCursor(offset: number): string {
  return btoa(JSON.stringify({ offset }));
}
```

**3. `web/functions/api/db.ts`** — D1 query helper functions:
```typescript
// All functions use D1 prepared statements with bind() for parameterization.
// No string interpolation in SQL — prevents SQL injection.

interface PriceRow {
  product_key: string;
  store: string;
  price: number;
  effective_unit_price: number;
  bundle_size: number;
  promo: string | null;      // JSON string
  promo_type: string | null;
  valid_from: string | null;
  valid_until: string | null;
  image_path: string | null;
  image_r2_url: string | null;
  scrape_time: string;
  date: string;
  match_method: string | null;
  match_confidence: number | null;
  standardized_promo: string | null;  // JSON string
}

interface ProductRow {
  key: string;
  name: string;
  brand: string | null;
  unit: string;
  unit_type: string | null;
  unit_value_g: number | null;
  category: string | null;
}

// Get products with pagination (returns product rows)
export async function getProducts(
  db: D1Database,
  opts: { limit: number; offset: number; sort: string; store?: string; category?: string; has_promo?: boolean }
): Promise<{ products: ProductRow[]; total: number }> {
  // Implementation: build SQL query with bind() parameters
  // ORDER BY depends on sort param:
  //   'name' -> ORDER BY p.name
  //   'cheapest' -> ORDER BY computed price_min (subquery)
  //   'savings' -> ORDER BY computed price_gap DESC
  //   'expiry' -> ORDER BY earliest valid_until
  // Filter by store: EXISTS (SELECT 1 FROM prices WHERE product_key = p.key AND store = ?)
  // Filter by category: p.category = ?
  // Filter by has_promo: EXISTS (SELECT 1 FROM prices WHERE product_key = p.key AND promo IS NOT NULL)
  // Use LIMIT and OFFSET for pagination
  // Also return total count (separate COUNT query)
  // ... implement with db.prepare().bind().all()
}

// Get latest prices for a set of product keys (one price per store per product)
export async function getLatestPricesForProducts(
  db: D1Database,
  productKeys: string[]
): Promise<PriceRow[]> {
  // Implementation: query prices where product_key IN (...) AND date is the latest for that (product_key, store)
  // Use a subquery: date = (SELECT MAX(date) FROM prices WHERE product_key = pr.product_key AND store = pr.store)
  // Return all matching rows
  // ... implement with db.prepare().bind().all()
}

// Get a single product by key
export async function getProductByKey(
  db: D1Database,
  key: string
): Promise<ProductRow | null> {
  // Implementation: SELECT * FROM products WHERE key = ?
  // ... implement with db.prepare().bind().first()
}

// Get price history for a product (optionally filtered by date range and store)
export async function getPriceHistory(
  db: D1Database,
  productKey: string,
  opts: { from?: string; to?: string; store?: string }
): Promise<PriceRow[]> {
  // Implementation: SELECT * FROM prices WHERE product_key = ?
  //   AND (date >= ? OR ? IS NULL) AND (date <= ? OR ? IS NULL)
  //   AND (store = ? OR ? IS NULL)
  // ORDER BY date ASC
  // ... implement with db.prepare().bind().all()
}

// Get all stores
export async function getStores(db: D1Database): Promise<{ name: string; color: string | null }[]> {
  // Implementation: SELECT name, color FROM stores ORDER BY name
  // ... implement with db.prepare().all()
}

// Get all categories
export async function getCategories(db: D1Database): Promise<string[]> {
  // Implementation: SELECT DISTINCT category FROM products WHERE category IS NOT NULL ORDER BY category
  // ... implement with db.prepare().all()
}

// Search products by name, brand, or unit
export async function searchProducts(
  db: D1Database,
  query: string,
  limit: number
): Promise<ProductRow[]> {
  // Implementation: SELECT * FROM products WHERE name LIKE ? OR brand LIKE ? ORDER BY name LIMIT ?
  // Use %query% pattern with bind()
  // ... implement with db.prepare().bind().all()
}

// Get promo catalog
export async function getPromos(db: D1Database): Promise<any[]> {
  // Implementation: SELECT * FROM promos ORDER BY product_count DESC
  // JSON-parse stores and example_products columns
  // ... implement with db.prepare().all()
}

// Get brochure metadata (grouped by image_path)
export async function getBrochures(db: D1Database): Promise<any[]> {
  // Implementation: SELECT image_path, store, date, COUNT(*) as product_count, GROUP_CONCAT(product_key) as product_keys
  // FROM prices WHERE image_path IS NOT NULL GROUP BY image_path ORDER BY store, date DESC
  // ... implement with db.prepare().all()
}

// Get summary stats
export async function getStats(db: D1Database): Promise<any> {
  // Implementation: multiple COUNT queries combined
  // total_products_lotte: COUNT(DISTINCT product_key) FROM prices WHERE store = 'Lotte'
  // total_products_superindo: same for 'Superindo'
  // matched_across_stores: COUNT of products with prices from 2+ stores
  // etc.
  // ... implement with db.prepare().all() for each query
}
```

**4. Update `web/functions/api/[[route]].ts`** — import and mount routes:
```typescript
import { Hono } from 'hono';
import { z } from 'zod';
import { productsQuerySchema, historyQuerySchema, pricesQuerySchema, searchQuerySchema, decodeCursor, encodeCursor } from './schemas';
import { getProducts, getLatestPricesForProducts, getProductByKey, getPriceHistory, getStores, getCategories, searchProducts, getPromos, getBrochures, getStats } from './db';
import type { Bindings, ProductResponse, StoreEntry, PaginatedResponse, ErrorResponse } from './types';

const app = new Hono<{ Bindings: Bindings }>();

// Helper: build a ProductResponse from a ProductRow + its PriceRows
function buildProductResponse(product: ProductRow, prices: PriceRow[]): ProductResponse {
  // ... implementation: JSON-parse promo and standardized_promo from each price row
  // ... compute price_min, price_max, cheapest_store, price_gap, has_promo, valid_until
  // ... return the fully built ProductResponse object
}

// Helper: error response
function errorResponse(c: Context, status: number, error: string, message: string) {
  return c.json({ error, message } as ErrorResponse, status);
}

// Routes will be added in subsequent todos
// ... (see Todo 2-7 for route implementations)

// Health check (from Phase 1)
app.get('/health', (c) => c.json({ status: 'ok', timestamp: new Date().toISOString() }));

// 404 for unmatched routes
app.all('*', (c) => errorResponse(c, 404, 'Not found', `Route ${c.req.method} ${c.req.path} does not exist`));

export default app;
```

**References:** plan.md:108-143 (API endpoint list), plan.md:129-143 (query parameters), web/schema.sql (from Phase 2), web/functions/api/[[route]].ts (from Phase 1), Hono docs: https://hono.dev/docs, Cloudflare Pages Functions docs: https://developers.cloudflare.com/pages/functions/

**Acceptance criteria:**
- `web/functions/api/types.ts` exists with all interfaces shown above
- `web/functions/api/schemas.ts` exists with all Zod schemas and cursor helpers
- `web/functions/api/db.ts` exists with all query function signatures (implementation can be stubs for now — filled in Todos 2-7)
- `web/functions/api/[[route]].ts` imports from all three modules and compiles
- `cd web && npx tsc --noEmit` exits 0
- `cd web && npx wrangler pages dev --local` starts without errors
- `curl http://localhost:8787/api/health` still returns `{"status":"ok"}`
- **Log message clarity:** No console.log statements in production code — Hono's `c.json()` is the response. Errors are returned as JSON, not logged.
- **Failure handling:** The 404 catch-all returns a JSON error response with the method and path, making debugging easy
- **Code quality:**
  - All types are explicit — no `any` anywhere
  - All interfaces are exported for use in route handlers
  - Zod schemas use `z.coerce.number()` for query params (which come as strings)
  - `noUncheckedIndexedAccess` is respected — array access includes null checks
  - SQL queries use `db.prepare().bind()` — never string interpolation
  - `PaginatedResponse<T>` is generic for reuse across endpoints
- **Unit test coverage:** Unit tests for schemas and db helpers are in Todo 8
- **Documentation:** Todo 9 creates `docs/staging/api-read-endpoints.md`

**QA:**
- Happy: `tsc --noEmit` passes, `wrangler dev` starts, `/api/health` works → pass
- Failure: TypeScript errors → fix type definitions until `tsc` passes

**Commit:** Y | feat(api): set up Hono app structure with types, Zod schemas, and D1 query helpers

---

### Todo 2: Implement simple endpoints (stores, categories, stats)

**What to do:**

Add three route handlers to `web/functions/api/[[route]].ts`:

**GET /api/v1/stores:**
```typescript
app.get('/api/v1/stores', async (c) => {
  const stores = await getStores(c.env.DB);
  return c.json({ data: stores });
});
```
Response: `{"data": [{"name": "Lotte", "color": "#0057A8"}, {"name": "Superindo", "color": "#E8211D"}]}`

**GET /api/v1/categories:**
```typescript
app.get('/api/v1/categories', async (c) => {
  const categories = await getCategories(c.env.DB);
  return c.json({ data: categories });
});
```
Response: `{"data": ["Mie Instan", "Minuman", ...]}` (currently empty since category is NULL in seed data)

**GET /api/v1/stats:**
```typescript
app.get('/api/v1/stats', async (c) => {
  const stats = await getStats(c.env.DB);
  return c.json(stats);
});
```
Response: `{"total_products_lotte": 31, "total_products_superindo": 365, "matched_across_stores": 3, ...}`

Implement the `getStores()`, `getCategories()`, and `getStats()` functions in `db.ts`:

- `getStores`: `SELECT name, color FROM stores ORDER BY name` — use `db.prepare('SELECT name, color FROM stores ORDER BY name').all()`
- `getCategories`: `SELECT DISTINCT category FROM products WHERE category IS NOT NULL ORDER BY category` — use `db.prepare(...).all()`, map results to string array
- `getStats`: Run multiple queries:
  - `SELECT COUNT(DISTINCT product_key) as cnt FROM prices WHERE store = 'Lotte'` → total_products_lotte
  - `SELECT COUNT(DISTINCT product_key) as cnt FROM prices WHERE store = 'Superindo'` → total_products_superindo
  - `SELECT COUNT(DISTINCT product_key) as cnt FROM prices WHERE product_key IN (SELECT product_key FROM prices WHERE store = 'Lotte' INTERSECT SELECT product_key FROM prices WHERE store = 'Superindo')` → matched_across_stores
  - `lotte_only` = total_products_lotte - matched_across_stores
  - `superindo_only` = total_products_superindo - matched_across_stores
  - `total_products` = `SELECT COUNT(*) FROM products`

Wrap each query in `try/catch` — on D1 error, throw with a descriptive message.

**References:** plan.md:119 (GET /stores), plan.md:120 (GET /categories), plan.md:124 (GET /stats), web/functions/api/db.ts (from Todo 1)

**Acceptance criteria:**
- `curl http://localhost:8787/api/v1/stores` returns 200 with `{"data": [{"name": "Lotte", "color": "#0057A8"}, {"name": "Superindo", "color": "#E8211D"}]}`
- `curl http://localhost:8787/api/v1/categories` returns 200 with `{"data": []}` (empty until categories are populated)
- `curl http://localhost:8787/api/v1/stats` returns 200 with stats matching `active_promo.json` stats section
- **Log message clarity:** Responses are clean JSON — no extra fields, no debug output
- **Failure handling:** If D1 query fails, Hono's error handler returns `{"error": "Internal error", "message": "<details>"}` with status 500
- **Code quality:**
  - All SQL uses `db.prepare()` — no string interpolation
  - Response shapes are consistent: list endpoints return `{"data": [...]}`, single-object endpoints return the object directly
  - No `any` types — all return values are typed
- **Unit test coverage:** Todo 8 covers query helper tests
- **Documentation:** Todo 9 documents all endpoints

**QA:**
- Happy: All three endpoints return correct data → pass
- Failure: D1 not seeded → endpoints return empty results, not errors

**Commit:** Y | feat(api): add stores, categories, and stats endpoints

---

### Todo 3: Implement products list with pagination, filtering, sorting

**What to do:**

Add the products list endpoint to `web/functions/api/[[route]].ts`:

```typescript
app.get('/api/v1/products', async (c) => {
  // 1. Parse and validate query params with Zod
  const parseResult = productsQuerySchema.safeParse(c.req.query());
  if (!parseResult.success) {
    return errorResponse(c, 400, 'Invalid query', parseResult.error.message);
  }
  const params = parseResult.data;

  // 2. Decode cursor to offset
  const offset = params.cursor ? decodeCursor(params.cursor) : 0;

  // 3. Query products with pagination
  const { products: productRows, total } = await getProducts(c.env.DB, {
    limit: params.limit,
    offset,
    sort: params.sort,
    store: params.store,
    category: params.category,
    has_promo: params.has_promo === 'true',
  });

  // 4. Get latest prices for those products
  const productKeys = productRows.map(p => p.key);
  const priceRows = productKeys.length > 0
    ? await getLatestPricesForProducts(c.env.DB, productKeys)
    : [];

  // 5. Group prices by product_key and build response
  const pricesByKey = new Map<string, PriceRow[]>();
  for (const pr of priceRows) {
    const existing = pricesByKey.get(pr.product_key) ?? [];
    existing.push(pr);
    pricesByKey.set(pr.product_key, existing);
  }

  const data = productRows.map(p => buildProductResponse(p, pricesByKey.get(p.key) ?? []));

  // 6. Build pagination response
  const hasMore = offset + params.limit < total;
  const nextCursor = hasMore ? encodeCursor(offset + params.limit) : null;

  return c.json({
    data,
    pagination: {
      limit: params.limit,
      cursor: nextCursor,
      has_more: hasMore,
    },
  } as PaginatedResponse<ProductResponse>);
});
```

Implement `getProducts()` in `db.ts`:

```typescript
export async function getProducts(
  db: D1Database,
  opts: { limit: number; offset: number; sort: string; store?: string; category?: string; has_promo?: boolean }
): Promise<{ products: ProductRow[]; total: number }> {
  // Build WHERE clauses
  const conditions: string[] = [];
  const binds: (string | number | boolean)[] = [];

  if (opts.store) {
    conditions.push('EXISTS (SELECT 1 FROM prices WHERE product_key = p.key AND store = ?)');
    binds.push(opts.store);
  }
  if (opts.category) {
    conditions.push('p.category = ?');
    binds.push(opts.category);
  }
  if (opts.has_promo !== undefined) {
    if (opts.has_promo) {
      conditions.push('EXISTS (SELECT 1 FROM prices WHERE product_key = p.key AND promo IS NOT NULL)');
    } else {
      conditions.push('NOT EXISTS (SELECT 1 FROM prices WHERE product_key = p.key AND promo IS NOT NULL)');
    }
  }

  const whereClause = conditions.length > 0 ? `WHERE ${conditions.join(' AND ')}` : '';

  // Build ORDER BY
  let orderBy = 'p.name';
  switch (opts.sort) {
    case 'cheapest':
      orderBy = '(SELECT MIN(price) FROM prices WHERE product_key = p.key)';
      break;
    case 'savings':
      orderBy = '(SELECT MAX(price) - MIN(price) FROM prices WHERE product_key = p.key) DESC';
      break;
    case 'expiry':
      orderBy = '(SELECT MIN(valid_until) FROM prices WHERE product_key = p.key AND valid_until IS NOT NULL)';
      break;
  }

  // Query products
  const productSql = `SELECT p.key, p.name, p.brand, p.unit, p.unit_type, p.unit_value_g, p.category
                      FROM products p ${whereClause} ORDER BY ${orderBy} LIMIT ? OFFSET ?`;
  const productStmt = db.prepare(productSql);
  for (const b of binds) productStmt.bind(b);
  productStmt.bind(opts.limit, opts.offset);
  const productResult = await productStmt.all();

  // Query total count
  const countSql = `SELECT COUNT(*) as total FROM products p ${whereClause}`;
  const countStmt = db.prepare(countSql);
  for (const b of binds) countStmt.bind(b);
  const countResult = await countStmt.first();

  return {
    products: productResult.results as ProductRow[],
    total: (countResult as any)?.total ?? 0,
  };
}
```

Implement `getLatestPricesForProducts()` in `db.ts`:
```typescript
export async function getLatestPricesForProducts(
  db: D1Database,
  productKeys: string[]
): Promise<PriceRow[]> {
  if (productKeys.length === 0) return [];

  // D1 doesn't support arrays in IN clauses directly — use parameterized query
  const placeholders = productKeys.map(() => '?').join(',');
  const sql = `SELECT * FROM prices pr
               WHERE pr.product_key IN (${placeholders})
               AND pr.date = (SELECT MAX(date) FROM prices WHERE product_key = pr.product_key AND store = pr.store)
               ORDER BY pr.product_key, pr.store`;

  const stmt = db.prepare(sql);
  for (const key of productKeys) stmt.bind(key);
  const result = await stmt.all();
  return result.results as PriceRow[];
}
```

Implement `buildProductResponse()` in `[[route]].ts`:
```typescript
function buildProductResponse(product: ProductRow, prices: PriceRow[]): ProductResponse {
  const storeEntries: StoreEntry[] = prices.map(pr => ({
    store: pr.store,
    price: pr.price,
    effective_unit_price: pr.effective_unit_price,
    bundle_size: pr.bundle_size,
    promo: pr.promo ? JSON.parse(pr.promo) : null,
    promo_type: pr.promo_type,
    valid_from: pr.valid_from,
    valid_until: pr.valid_until,
    image_path: pr.image_path,
    image_r2_url: pr.image_r2_url,
    standardized_promo: pr.standardized_promo ? JSON.parse(pr.standardized_promo) : null,
  }));

  const allPrices = storeEntries.map(s => s.price);
  const priceMin = allPrices.length > 0 ? Math.min(...allPrices) : 0;
  const priceMax = allPrices.length > 0 ? Math.max(...allPrices) : 0;
  const cheapestEntry = storeEntries.find(s => s.price === priceMin);
  const hasPromo = storeEntries.some(s => s.promo !== null);
  const validUntils = storeEntries.map(s => s.valid_until).filter((v): v is string => v !== null);
  const earliestValidUntil = validUntils.length > 0 ? validUntils.sort()[0]! : null;

  return {
    key: product.key,
    name: product.name,
    brand: product.brand,
    unit: product.unit,
    unit_type: product.unit_type,
    unit_value_g: product.unit_value_g,
    stores: storeEntries,
    price_min: priceMin,
    price_max: priceMax,
    cheapest_store: cheapestEntry?.store ?? null,
    price_gap: priceMax - priceMin,
    has_promo: hasPromo,
    valid_until: earliestValidUntil,
  };
}
```

**References:** plan.md:115 (GET /products), plan.md:129-136 (query parameters for products), output/html/active_promo.json (response shape — products with stores array), index.html:754 (normalizeProduct expects stores[] array)

**Acceptance criteria:**
- `curl http://localhost:8787/api/v1/products` returns 200 with paginated product list
- `curl "http://localhost:8787/api/v1/products?limit=5"` returns 5 products with `has_more: true`
- `curl "http://localhost:8787/api/v1/products?limit=5&cursor=<cursor>"` returns the next 5 products
- `curl "http://localhost:8787/api/v1/products?store=Superindo"` returns only products with Superindo prices
- `curl "http://localhost:8787/api/v1/products?has_promo=true"` returns only products with promotions
- `curl "http://localhost:8787/api/v1/products?sort=cheapest"` returns products ordered by cheapest price
- `curl "http://localhost:8787/api/v1/products?sort=savings"` returns products ordered by price gap (largest first)
- `curl "http://localhost:8787/api/v1/products?sort=expiry"` returns products ordered by earliest expiry
- `curl "http://localhost:8787/api/v1/products?limit=0"` returns 400 with validation error
- `curl "http://localhost:8787/api/v1/products?sort=invalid"` returns 400 with validation error
- Each product in the response has: `key`, `name`, `brand`, `unit`, `stores[]` with `store`, `price`, `promo`, `standardized_promo` (JSON-decoded), `price_min`, `price_max`, `has_promo`
- **Log message clarity:** Validation errors return `{"error": "Invalid query", "message": "<zod error details>"}` with status 400
- **Failure handling:**
  - Invalid query params → 400 with Zod error message
  - Invalid cursor → offset defaults to 0 (no error)
  - D1 query error → 500 with error message
  - Empty result set → 200 with `{"data": [], "pagination": {"limit": 20, "cursor": null, "has_more": false}}`
- **Code quality:**
  - All SQL uses `db.prepare().bind()` — parameterized, no string interpolation for user input
  - `buildProductResponse` JSON-parses `promo` and `standardized_promo` from D1 TEXT columns
  - `noUncheckedIndexedAccess` is respected: `cheapestEntry?.store` uses optional chaining, `validUntils.sort()[0]!` uses non-null assertion only after filtering
  - Pagination uses base64-encoded JSON cursor (offset-based) — simple and sufficient for ~589 products
  - No `any` type in response building — all types are explicit
- **Unit test coverage:** Todo 8 tests `getProducts`, `getLatestPricesForProducts`, `buildProductResponse`, `decodeCursor`, `encodeCursor`, and Zod validation
- **Documentation:** Todo 9 documents all query params and response shape

**QA:**
- Happy: `curl /api/v1/products?limit=5` returns 5 products with correct store data → pass
- Failure: `curl /api/v1/products?sort=invalid` returns 400 → pass
- Failure: `curl /api/v1/products?limit=0` returns 400 → pass

**Commit:** Y | feat(api): add products list endpoint with pagination, filtering, and sorting

---

### Todo 4: Implement product detail and history endpoints

**What to do:**

Add two route handlers to `web/functions/api/[[route]].ts`:

**GET /api/v1/products/:key:**
```typescript
app.get('/api/v1/products/:key', async (c) => {
  const key = c.req.param('key');
  const product = await getProductByKey(c.env.DB, key);
  if (!product) {
    return errorResponse(c, 404, 'Not found', `Product '${key}' does not exist`);
  }
  const priceRows = await getLatestPricesForProducts(c.env.DB, [key]);
  const response = buildProductResponse(product, priceRows);
  return c.json(response);
});
```

**GET /api/v1/products/:key/history:**
```typescript
app.get('/api/v1/products/:key/history', async (c) => {
  const key = c.req.param('key');
  const product = await getProductByKey(c.env.DB, key);
  if (!product) {
    return errorResponse(c, 404, 'Not found', `Product '${key}' does not exist`);
  }
  const parseResult = historyQuerySchema.safeParse(c.req.query());
  if (!parseResult.success) {
    return errorResponse(c, 400, 'Invalid query', parseResult.error.message);
  }
  const params = parseResult.data;
  const history = await getPriceHistory(c.env.DB, key, {
    from: params.from,
    to: params.to,
    store: params.store,
  });
  // Return snapshots in the same shape as price_history.json
  const snapshots = history.map(pr => ({
    product_key: pr.product_key,
    name: product.name,
    brand: product.brand,
    unit: product.unit,
    date: pr.date,
    store: pr.store,
    price: pr.price,
    effective_unit_price: pr.effective_unit_price,
    promo: pr.promo ? JSON.parse(pr.promo) : null,
    valid_from: pr.valid_from,
    valid_until: pr.valid_until,
    bundle_size: pr.bundle_size,
    promo_type: pr.promo_type,
    match_method: pr.match_method,
    match_confidence: pr.match_confidence,
    image_path: pr.image_path,
    scrape_time: pr.scrape_time,
    standardized_promo: pr.standardized_promo ? JSON.parse(pr.standardized_promo) : undefined,
  }));
  return c.json({ product_key: key, snapshots });
});
```

Implement `getProductByKey()` and `getPriceHistory()` in `db.ts`:
- `getProductByKey`: `SELECT key, name, brand, unit, unit_type, unit_value_g, category FROM products WHERE key = ?` — use `db.prepare(sql).bind(key).first()`
- `getPriceHistory`: `SELECT * FROM prices WHERE product_key = ? AND (date >= ? OR ? IS NULL) AND (date <= ? OR ? IS NULL) AND (store = ? OR ? IS NULL) ORDER BY date ASC` — bind all 7 parameters (key, from, from, to, to, store, store)

**References:** plan.md:116 (GET /products/:key), plan.md:117 (GET /products/:key/history), plan.md:137-139 (history query params), database/price_history.json (snapshot schema — 18 fields)

**Acceptance criteria:**
- `curl http://localhost:8787/api/v1/products/rinso-detergen-bubuk-anti-noda-pck-1440gr--rinso--1440gr` returns 200 with product details including stores array
- `curl http://localhost:8787/api/v1/products/nonexistent-key` returns 404 with `{"error": "Not found", "message": "Product 'nonexistent-key' does not exist"}`
- `curl http://localhost:8787/api/v1/products/rinso-detergen-.../history` returns 200 with snapshots array sorted by date ascending
- `curl "http://localhost:8787/api/v1/products/rinso-detergen-.../history?from=2026-06-01&to=2026-06-30"` returns only snapshots in that date range
- `curl "http://localhost:8787/api/v1/products/rinso-detergen-.../history?store=Superindo"` returns only Superindo snapshots
- `curl "http://localhost:8787/api/v1/products/rinso-detergen-.../history?from=invalid"` returns 400 with validation error
- Each snapshot has all 18 fields matching the `price_history.json` schema, with `promo` and `standardized_promo` JSON-decoded
- **Log message clarity:** 404 errors include the product key in the message for easy debugging
- **Failure handling:**
  - Product not found → 404 with key in message
  - Invalid date format → 400 with Zod error
  - D1 error → 500
  - Product with no price history → 200 with `{"product_key": "...", "snapshots": []}`
- **Code quality:**
  - `standardized_promo` is `undefined` (not `null`) when absent, matching the JSON source where the key is omitted entirely
  - All SQL parameterized
  - No `any` types
- **Unit test coverage:** Todo 8 tests `getProductByKey`, `getPriceHistory`, and Zod validation

**QA:**
- Happy: Product detail returns correct store data, history returns correct snapshots → pass
- Failure: Nonexistent product returns 404 → pass

**Commit:** Y | feat(api): add product detail and price history endpoints

---

### Todo 5: Implement prices endpoint

**What to do:**

Add the prices endpoint to `web/functions/api/[[route]].ts`:

```typescript
app.get('/api/v1/prices', async (c) => {
  const parseResult = pricesQuerySchema.safeParse(c.req.query());
  if (!parseResult.success) {
    return errorResponse(c, 400, 'Invalid query', parseResult.error.message);
  }
  const params = parseResult.data;
  const offset = params.cursor ? decodeCursor(params.cursor) : 0;

  // Query prices with optional filters
  // ... build SQL with WHERE clauses for product_key and store
  // ... apply LIMIT and OFFSET
  // ... return paginated response with price rows (JSON-decoded promo/standardized_promo)
});
```

Implement the query in `db.ts` — `getPrices()` function:
- Build WHERE clauses for `product_key` and `store` filters
- `SELECT * FROM prices WHERE (product_key = ? OR ? IS NULL) AND (store = ? OR ? IS NULL) ORDER BY date DESC, product_key LIMIT ? OFFSET ?`
- Return paginated results with JSON-decoded `promo` and `standardized_promo` fields

Response shape:
```json
{
  "data": [
    {
      "product_key": "...",
      "store": "Superindo",
      "price": 24900,
      "effective_unit_price": 24900,
      "promo": ["DISKON 20%"],
      "date": "2026-06-13",
      "valid_until": null,
      "image_path": "database/scrape/...",
      "standardized_promo": { ... }
    }
  ],
  "pagination": { "limit": 20, "cursor": "...", "has_more": true }
}
```

**References:** plan.md:118 (GET /prices), plan.md:129-136 (query parameters — limit, cursor, product_key, store)

**Acceptance criteria:**
- `curl http://localhost:8787/api/v1/prices` returns 200 with paginated price list
- `curl "http://localhost:8787/api/v1/prices?store=Superindo"` returns only Superindo prices
- `curl "http://localhost:8787/api/v1/prices?product_key=rinso-detergen-..."` returns only prices for that product
- `curl "http://localhost:8787/api/v1/prices?limit=5"` returns 5 prices with pagination
- Each price has `promo` and `standardized_promo` JSON-decoded (not raw JSON strings)
- **Log message clarity:** Same pagination and error patterns as products endpoint
- **Failure handling:** Same as products endpoint — 400 for invalid params, 500 for D1 errors
- **Code quality:** Parameterized SQL, JSON-decoded fields, consistent pagination response
- **Unit test coverage:** Todo 8 tests the query helper and Zod schema

**QA:**
- Happy: `curl /api/v1/prices?store=Superindo&limit=5` returns 5 Superindo prices → pass
- Failure: `curl /api/v1/prices?limit=0` returns 400 → pass

**Commit:** Y | feat(api): add prices endpoint with filtering and pagination

---

### Todo 6: Implement search endpoint

**What to do:**

Add the search endpoint to `web/functions/api/[[route]].ts`:

```typescript
app.get('/api/v1/search', async (c) => {
  const parseResult = searchQuerySchema.safeParse(c.req.query());
  if (!parseResult.success) {
    return errorResponse(c, 400, 'Invalid query', parseResult.error.message);
  }
  const params = parseResult.data;

  const productRows = await searchProducts(c.env.DB, params.q, params.limit);
  const productKeys = productRows.map(p => p.key);
  const priceRows = productKeys.length > 0
    ? await getLatestPricesForProducts(c.env.DB, productKeys)
    : [];

  const pricesByKey = new Map<string, PriceRow[]>();
  for (const pr of priceRows) {
    const existing = pricesByKey.get(pr.product_key) ?? [];
    existing.push(pr);
    pricesByKey.set(pr.product_key, existing);
  }

  const data = productRows.map(p => buildProductResponse(p, pricesByKey.get(p.key) ?? []));

  return c.json({ data, query: params.q, count: data.length });
});
```

Implement `searchProducts()` in `db.ts`:
```typescript
export async function searchProducts(
  db: D1Database,
  query: string,
  limit: number
): Promise<ProductRow[]> {
  const pattern = `%${query}%`;
  const sql = `SELECT key, name, brand, unit, unit_type, unit_value_g, category
               FROM products
               WHERE name LIKE ? OR brand LIKE ? OR unit LIKE ?
               ORDER BY name LIMIT ?`;
  const result = await db.prepare(sql).bind(pattern, pattern, pattern, limit).all();
  return result.results as ProductRow[];
}
```

**References:** plan.md:121 (GET /search), plan.md:141-143 (search query params — q required, limit max 50), index.html:770 (searchProducts function — searches name, brand, unit)

**Acceptance criteria:**
- `curl "http://localhost:8787/api/v1/search?q=indomie"` returns 200 with products matching "indomie" in name, brand, or unit
- `curl "http://localhost:8787/api/v1/search?q=rinso&limit=5"` returns at most 5 results
- `curl "http://localhost:8787/api/v1/search?q="` returns 400 with validation error (q is required, min 1 char)
- `curl "http://localhost:8787/api/v1/search"` (no q param) returns 400
- Each result has the same shape as a product from `/api/v1/products` (with stores array, price_min, etc.)
- Response includes `query` and `count` fields for client-side display
- **Log message clarity:** Validation error message specifies that `q` is required
- **Failure handling:** Empty search query → 400. No results → 200 with `{"data": [], "query": "...", "count": 0}`
- **Code quality:**
  - SQL uses `LIKE` with `%query%` pattern — parameterized, no injection risk
  - `limit` max is 50 (per plan.md:143), not 100 like products endpoint
  - No `any` types
- **Unit test coverage:** Todo 8 tests `searchProducts` and `searchQuerySchema`

**QA:**
- Happy: `curl /api/v1/search?q=indomie` returns matching products → pass
- Failure: `curl /api/v1/search?q=` returns 400 → pass

**Commit:** Y | feat(api): add search endpoint with name/brand/unit matching

---

### Todo 7: Implement promos and brochures endpoints

**What to do:**

Add two route handlers to `web/functions/api/[[route]].ts`:

**GET /api/v1/promos:**
```typescript
app.get('/api/v1/promos', async (c) => {
  const promos = await getPromos(c.env.DB);
  // JSON-parse stores and example_products from D1 TEXT columns
  const data = promos.map(p => ({
    key: p.key,
    display: p.display,
    type: p.type,
    discount_pct: p.discount_pct,
    product_count: p.product_count,
    stores: p.stores ? JSON.parse(p.stores) : {},
    example_products: p.example_products ? JSON.parse(p.example_products) : [],
  }));
  return c.json({ data });
});
```

**GET /api/v1/brochures:**
```typescript
app.get('/api/v1/brochures', async (c) => {
  const brochures = await getBrochures(c.env.DB);
  return c.json({ data: brochures });
});
```

Implement `getPromos()` and `getBrochures()` in `db.ts`:

- `getPromos`: `SELECT key, display, type, discount_pct, product_count, stores, example_products FROM promos ORDER BY product_count DESC` — return raw rows (JSON-parsing done in route handler)
- `getBrochures`: `SELECT image_path, store, date, COUNT(*) as product_count, GROUP_CONCAT(product_key, ',') as product_keys FROM prices WHERE image_path IS NOT NULL GROUP BY image_path, store, date ORDER BY store, date DESC` — split `product_keys` string into array in TypeScript

**References:** plan.md:122 (GET /promos), plan.md:123 (GET /brochures), output/html/promo_catalog.json (promo schema), index.html:1377 (renderBrochures groups by image_path, store, date)

**Acceptance criteria:**
- `curl http://localhost:8787/api/v1/promos` returns 200 with promos sorted by product_count descending
- Each promo has `stores` and `example_products` as JSON-decoded objects/arrays (not raw strings)
- `curl http://localhost:8787/api/v1/brochures` returns 200 with brochures grouped by image_path
- Each brochure has: `image_path`, `store`, `date`, `product_count`, `product_keys` (array of strings)
- **Log message clarity:** Clean JSON responses, no debug output
- **Failure handling:** Empty promos table → 200 with `{"data": []}`. No images in prices → 200 with `{"data": []}`
- **Code quality:**
  - `GROUP_CONCAT` is SQLite-specific — documented in db.ts with a comment
  - `product_keys` string is split and trimmed in TypeScript, not in SQL
  - JSON-parsing of `stores` and `example_products` is done in the route handler, not db.ts — separation of concerns
  - No `any` types — use specific interfaces
- **Unit test coverage:** Todo 8 tests `getPromos` and `getBrochures`

**QA:**
- Happy: `curl /api/v1/promos` returns 50 promos, `curl /api/v1/brochures` returns ~32 brochures → pass
- Failure: D1 not seeded → empty arrays, not errors → pass

**Commit:** Y | feat(api): add promos and brochures endpoints

---

### Todo 8: Write unit tests

**What to do:**

Set up Vitest for TypeScript testing and create test files.

1. Install Vitest:
   ```bash
   cd web && npm install -D vitest @cloudflare/vitest-pool-workers
   ```

2. Add test script to `web/package.json`:
   ```json
   "scripts": {
     "dev": "wrangler pages dev --local",
     "deploy": "wrangler pages deploy . --project-name haqita",
     "typecheck": "tsc --noEmit",
     "test": "vitest run"
   }
   ```

3. Create `web/vitest.config.ts`:
   ```typescript
   import { defineConfig } from 'vitest/config';
   export default defineConfig({
     test: {
       globals: true,
       environment: 'node',
     },
   });
   ```

4. Create `web/tests/schemas.test.ts` — test Zod schemas:
   - `test('productsQuerySchema accepts valid params')` — limit=20, sort=name
   - `test('productsQuerySchema rejects limit > 100')` — limit=101 should fail
   - `test('productsQuerySchema rejects limit < 1')` — limit=0 should fail
   - `test('productsQuerySchema rejects invalid sort')` — sort=invalid should fail
   - `test('productsQuerySchema defaults limit to 20')` — no limit param → 20
   - `test('productsQuerySchema defaults sort to name')` — no sort param → 'name'
   - `test('historyQuerySchema validates date format')` — from=2026-06-01 passes, from=invalid fails
   - `test('searchQuerySchema requires q')` — no q should fail
   - `test('searchQuerySchema rejects empty q')` — q="" should fail
   - `test('searchQuerySchema limits to 50')` — limit=51 should fail
   - `test('decodeCursor returns 0 for invalid cursor')` — decodeCursor('invalid') → 0
   - `test('decodeCursor decodes valid cursor')` — decodeCursor(encodeCursor(20)) → 20
   - `test('encodeCursor produces base64 string')` — encodeCursor(0) is a valid base64 string

5. Create `web/tests/db.test.ts` — test D1 query helpers:
   - These tests require a local D1 database. Use `wrangler d1 execute haqita-db --local` to set up test fixtures.
   - `test('getStores returns all stores')` — expect 2 stores with correct colors
   - `test('getCategories returns distinct categories')` — expect empty array (no categories in seed data)
   - `test('getProductByKey returns product for valid key')` — expect product with correct fields
   - `test('getProductByKey returns null for invalid key')` — expect null
   - `test('getProducts returns paginated results')` — limit=5, offset=0 → 5 products, total > 5
   - `test('getProducts filters by store')` — store=Superindo → all products have Superindo prices
   - `test('getProducts filters by has_promo')` — has_promo=true → all products have non-null promo
   - `test('getProducts sorts by name')` — products in alphabetical order
   - `test('getProducts sorts by cheapest')` — first product has lowest price_min
   - `test('getLatestPricesForProducts returns one price per store')` — for a matched product, returns 2 rows
   - `test('getPriceHistory returns snapshots sorted by date')` — snapshots in ascending date order
   - `test('getPriceHistory filters by date range')` — from/to params filter correctly
   - `test('searchProducts matches by name')` — query='indomie' → returns Indomie products
   - `test('searchProducts matches by brand')` — query='rinso' → returns Rinso products
   - `test('getPromos returns promos sorted by product_count')` — first promo has highest count
   - `test('getBrochures returns brochures grouped by image_path')` — each brochure has unique image_path
   - `test('getStats returns correct counts')` — lotte + superindo counts match seed data

**References:** web/functions/api/schemas.ts (Zod schemas to test), web/functions/api/db.ts (query helpers to test), tests/matching/test_publish_html.py (test pattern — class-based, thorough assertions)

**Acceptance criteria:**
- `cd web && npx vitest run` passes all tests with 0 failures
- `cd web && npx tsc --noEmit` still passes (test files don't break type checking)
- **Log message clarity:** Vitest output shows each test name and pass/fail status with timing
- **Failure handling:**
  - Tests for invalid inputs (limit=0, sort=invalid, empty q) must verify the error is caught and the correct status code/message is returned
  - Tests for null/missing data must verify graceful handling (null returns, empty arrays, not exceptions)
- **Code quality:**
  - Test file naming: `*.test.ts` (Vitest convention)
  - Test function naming: `test('descriptive name', ...)` or `it('should ...', ...)`
  - No `any` types in test assertions — use typed expectations
  - Each test has a clear arrange-act-assert structure
  - Tests are independent — no shared state between tests
- **Unit test coverage:** This IS the unit test file. Minimum test count:
  - schemas.test.ts: 13 tests
  - db.test.ts: 18 tests
  - **Total: 31 tests minimum**

**QA:**
- Happy: `npx vitest run` shows 31+ passed → pass
- Failure: Any test fails → fix the implementation (not the test) until all pass

**Commit:** Y | test(api): add unit tests for Zod schemas and D1 query helpers

---

### Todo 9: Write documentation

**What to do:**

Create `docs/staging/api-read-endpoints.md` following the existing documentation pattern (see `docs/staging/publish-html.md` for the template).

**Document structure:**
1. **H1 title:** `# API Read Endpoints`
2. **Overview table:** Base URL, Version, Auth, Content-Type, Rate Limit
3. **Endpoints section:** For each endpoint, include:
   - HTTP method and path
   - Query parameters table (name, type, required, default, description)
   - Example request (curl command)
   - Example response (JSON with field descriptions)
   - Error responses (status code, error type, message)
4. **Pagination section:** Explain cursor-based pagination (base64-encoded JSON offset, has_more field, how to use cursor parameter)
5. **Response shapes section:** Table mapping API response fields to D1 table columns and source JSON fields
6. **Local development section:** Commands for starting local dev server and testing endpoints

**References:** docs/staging/publish-html.md (documentation template), plan.md:108-143 (API design), web/functions/api/[[route]].ts (actual implementation)

**Acceptance criteria:**
- `docs/staging/api-read-endpoints.md` exists with all 10 endpoints documented
- Each endpoint has: method, path, params table, example request, example response, error responses
- **Log message clarity:** Documentation includes exact curl commands for testing each endpoint
- **Failure handling:** Error responses documented for each endpoint (400 for validation, 404 for not found, 500 for server errors)
- **Code quality:** Documentation matches the style of existing `docs/staging/*.md` files — ATX headings, pipe tables, fenced code blocks
- **Unit test coverage:** N/A — documentation

**QA:**
- Happy: Open `docs/staging/api-read-endpoints.md` — all endpoints documented with examples → pass
- Failure: Missing endpoint → add documentation for it

**Commit:** Y | docs: add API read endpoints documentation

---

### Todo 10: Final verification

**What to do:**

Run the complete verification checklist — curl every endpoint:

1. Start local dev server:
   ```bash
   cd web && npx wrangler pages dev --local &
   sleep 5
   ```

2. Verify each endpoint:
   ```bash
   # Simple endpoints
   curl -s http://localhost:8787/api/v1/stores | python3 -m json.tool
   curl -s http://localhost:8787/api/v1/categories | python3 -m json.tool
   curl -s http://localhost:8787/api/v1/stats | python3 -m json.tool

   # Products with pagination
   curl -s "http://localhost:8787/api/v1/products?limit=5" | python3 -m json.tool
   curl -s "http://localhost:8787/api/v1/products?limit=5&sort=cheapest" | python3 -m json.tool
   curl -s "http://localhost:8787/api/v1/products?store=Superindo&has_promo=true" | python3 -m json.tool

   # Product detail + history
   curl -s "http://localhost:8787/api/v1/products/rinso-detergen-bubuk-anti-noda-pck-1440gr--rinso--1440gr" | python3 -m json.tool
   curl -s "http://localhost:8787/api/v1/products/rinso-detergen-bubuk-anti-noda-pck-1440gr--rinso--1440gr/history" | python3 -m json.tool

   # Prices
   curl -s "http://localhost:8787/api/v1/prices?limit=5" | python3 -m json.tool

   # Search
   curl -s "http://localhost:8787/api/v1/search?q=indomie" | python3 -m json.tool

   # Promos + brochures
   curl -s http://localhost:8787/api/v1/promos | python3 -m json.tool
   curl -s http://localhost:8787/api/v1/brochures | python3 -m json.tool
   ```

3. Verify error handling:
   ```bash
   # 400 - invalid query
   curl -s -o /dev/null -w "%{http_code}" "http://localhost:8787/api/v1/products?limit=0"
   # Expected: 400

   # 400 - invalid sort
   curl -s -o /dev/null -w "%{http_code}" "http://localhost:8787/api/v1/products?sort=invalid"
   # Expected: 400

   # 404 - product not found
   curl -s -o /dev/null -w "%{http_code}" http://localhost:8787/api/v1/products/nonexistent
   # Expected: 404

   # 404 - unknown route
   curl -s -o /dev/null -w "%{http_code}" http://localhost:8787/api/v1/unknown
   # Expected: 404

   # 400 - missing search query
   curl -s -o /dev/null -w "%{http_code}" http://localhost:8787/api/v1/search
   # Expected: 400
   ```

4. Verify type checking and tests:
   ```bash
   cd web && npx tsc --noEmit
   cd web && npx vitest run
   ```

5. Kill the dev server:
   ```bash
   kill %1
   ```

**References:** All previous todos

**Acceptance criteria:**
- All 10 endpoints return 200 with valid JSON data
- All 5 error cases return the expected status codes (400, 404)
- `tsc --noEmit` exits 0
- `vitest run` passes all tests
- **Log message clarity:** All responses are well-formed JSON
- **Failure handling:** Error responses include `error` and `message` fields
- **Documentation:** Verification confirms `docs/staging/api-read-endpoints.md` is accurate

**QA:**
- Happy: All endpoints and error cases pass → Phase 3 complete
- Failure: Any endpoint returns wrong data → fix the query helper or route handler

**Commit:** Y | test: verify all API read endpoints work correctly

---

## Final verification wave
- [ ] F1. Plan compliance audit — all 10 endpoints implemented, no POST/PUT/DELETE, no auth middleware
- [ ] F2. Code quality review — `tsc --noEmit` clean, `vitest run` all pass, no `any` types, all SQL parameterized
- [ ] F3. Real manual QA — curl every endpoint, verify response shapes match documentation
- [ ] F4. Scope fidelity — no sync endpoints, no index.html changes, no security middleware, no CORS

---

## Commit strategy
- One commit per todo (Todos 1-10)
- Commit messages: `feat(api):` for endpoints, `test(api):` for tests, `docs:` for documentation, `test:` for verification
- Implementation + tests for each endpoint group can be in the same commit if the tests are written alongside

---

## Success criteria
1. All 10 GET endpoints return correct data via `curl`
2. Pagination works correctly (cursor encodes/decodes offset, has_more is accurate)
3. Filtering by store, category, has_promo works correctly
4. Sorting by name, cheapest, savings, expiry works correctly
5. Search matches products by name, brand, or unit
6. Error handling returns 400 for invalid params, 404 for not found, 500 for server errors
7. All SQL queries use parameterized `bind()` — no string interpolation
8. `npx tsc --noEmit` passes with zero errors
9. `npx vitest run` passes 31+ tests
10. `docs/staging/api-read-endpoints.md` documents all endpoints with examples

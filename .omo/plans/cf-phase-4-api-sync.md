# Phase 4: Hono API — Protected Sync Endpoints

## TL;DR (For humans)

**What you'll get:** Two protected POST endpoints (`/api/v1/sync/batch` and `/api/v1/sync/images`) with Bearer token authentication, Zod body validation, idempotent upserts into D1, and unit tests. The sync/batch endpoint receives stores, products, prices, and promos from the Python pipeline and upserts them. The sync/images endpoint records R2 URLs for images.

**Why this approach:** The sync endpoints are the write path that the Python Stage 5 script (Phase 5) calls to push data to Cloudflare. Building them before the Python script lets us validate the API contract with `curl` before integrating with Python.

**What it will NOT do:** Implement the Python sync script (Phase 5), deploy to Cloudflare Pages (Phase 6), or configure production secrets (Phase 7).

**Effort:** Medium (~4-5 hours: auth middleware, Zod body schema, upsert logic, image manifest, tests, documentation)
**Risk:** Medium — idempotency logic is critical; wrong upserts corrupt D1 data

---

## Scope

### Must have
1. Bearer token auth middleware that validates against `SCRAPER_SECRET`
2. Zod body validation schema for `POST /api/v1/sync/batch`
3. `POST /api/v1/sync/batch` endpoint with idempotent upserts (INSERT OR REPLACE)
4. `POST /api/v1/sync/images` endpoint that records R2 URLs in D1
5. Sync response with counts (inserted, updated, skipped, errors)
6. Unit tests for auth, validation, idempotency, and error handling
7. Documentation at `docs/staging/api-sync-endpoints.md`

### Must NOT have
1. No changes to read endpoints — they remain public
2. No rate limiting — that is Phase 7
3. No image upload through the API — images are uploaded directly to R2 from the laptop (Option A, plan.md:357-375)
4. No CORS headers — same origin
5. No `any` type — all types explicit
6. No raw SQL string interpolation — all parameterized

---

## Verification strategy
- **Test decision:** TDD for auth and validation + curl verification for endpoints
- **Evidence:** curl command outputs with valid/invalid tokens and bodies
- **Idempotency verification:** POST the same batch twice → second response shows 0 inserted, all updated
- **Auth verification:** POST without token → 401, POST with wrong token → 401, POST with correct token → 200

---

## Execution strategy

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
|------|-----------|--------|---------------------|
| 1. Auth middleware | Phase 3 | 3, 4 | 2 |
| 2. Zod body schema | Phase 3 | 3, 4 | 1 |
| 3. POST /sync/batch | 1, 2 | 5, 6 | 4 |
| 4. POST /sync/images | 1, 2 | 5, 6 | 3 |
| 5. Write unit tests | 3, 4 | 6, 7 | — |
| 6. Write documentation | 3, 4 | 7 | 5 |
| 7. Final verification | 5, 6 | — | — |

---

## Todos

### Todo 1: Implement Bearer auth middleware

**What to do:**

Create `web/functions/api/middleware/auth.ts`:

```typescript
import { createMiddleware } from 'hono/factory';

// Bearer token auth middleware — protects /api/v1/sync/* routes.
// Validates Authorization: Bearer <token> header against SCRAPER_SECRET binding.
//
// Usage:
//   app.post('/api/v1/sync/*', authMiddleware, ...handler)
//
// The SCRAPER_SECRET is set via `wrangler secret put SCRAPER_SECRET` (Phase 7)
// For local dev, it's set in web/wrangler.toml [vars] section or .dev.vars file.

export const authMiddleware = createMiddleware<{
  Bindings: { SCRAPER_SECRET: string };
}>(async (c, next) => {
  const authHeader = c.req.header('Authorization');
  if (!authHeader) {
    return c.json(
      { error: 'Unauthorized', message: 'Missing Authorization header' },
      401
    );
  }

  const match = authHeader.match(/^Bearer\s+(.+)$/i);
  if (!match) {
    return c.json(
      { error: 'Unauthorized', message: 'Invalid Authorization header format. Expected: Bearer <token>' },
      401
    );
  }

  const token = match[1]!;
  const secret = c.env.SCRAPER_SECRET;

  if (!secret) {
    return c.json(
      { error: 'Server error', message: 'SCRAPER_SECRET is not configured' },
      500
    );
  }

  if (token !== secret) {
    return c.json(
      { error: 'Unauthorized', message: 'Invalid token' },
      401
    );
  }

  await next();
});
```

Update `web/functions/api/types.ts` to add `SCRAPER_SECRET` to the Bindings interface:
```typescript
interface Bindings {
  DB: D1Database;
  IMAGES: R2Bucket;
  SCRAPER_SECRET: string;
}
```

Create `web/.dev.vars` for local development (not committed to git — add to `.gitignore`):
```
SCRAPER_SECRET=dev-secret-for-local-testing
```

Add `web/.dev.vars` to root `.gitignore`:
```
web/.dev.vars
```

**References:** plan.md:384 (scraper auth via SCRAPER_SECRET), plan.md:390 (wrangler secret put), Hono middleware docs: https://hono.dev/docs/guides/middleware, Cloudflare secrets docs: https://developers.cloudflare.com/workers/configuration/secrets/

**Acceptance criteria:**
- `web/functions/api/middleware/auth.ts` exists with the auth middleware shown above
- `web/functions/api/types.ts` updated with `SCRAPER_SECRET: string` in Bindings
- `web/.dev.vars` exists with `SCRAPER_SECRET=dev-secret-for-local-testing`
- `.gitignore` includes `web/.dev.vars`
- `cd web && npx tsc --noEmit` passes
- **Log message clarity:** 401 responses include clear messages: "Missing Authorization header", "Invalid Authorization header format", "Invalid token"
- **Failure handling:**
  - Missing Authorization header → 401 with "Missing Authorization header"
  - Wrong format (not `Bearer <token>`) → 401 with format explanation
  - Wrong token → 401 with "Invalid token"
  - SCRAPER_SECRET not configured → 500 with "SCRAPER_SECRET is not configured"
  - No timing attack: token comparison is direct string equality (acceptable for internal tool with 1-10 users)
- **Code quality:**
  - Uses `createMiddleware` from Hono — follows Hono middleware pattern
  - Regex uses case-insensitive match for "Bearer" prefix
  - `match[1]!` uses non-null assertion after regex check (safe because regex guarantees capture group)
  - No `any` types
  - Middleware is composable — can be applied to any route
- **Unit test coverage:** Todo 5 tests auth middleware with valid/invalid/missing tokens
- **Documentation:** Todo 6 documents auth requirement

**QA:**
- Happy: `curl -H "Authorization: Bearer dev-secret-for-local-testing" http://localhost:8787/api/v1/sync/batch -X POST -d '{}'` passes auth (may return 400 for empty body, but not 401)
- Failure: `curl http://localhost:8787/api/v1/sync/batch -X POST` returns 401 with "Missing Authorization header"
- Failure: `curl -H "Authorization: Bearer wrong-token" http://localhost:8787/api/v1/sync/batch -X POST` returns 401 with "Invalid token"

**Commit:** Y | feat(api): add Bearer token auth middleware for sync endpoints

---

### Todo 2: Create Zod body validation schema for sync/batch

**What to do:**

Add the sync batch body schema to `web/functions/api/schemas.ts`:

```typescript
// POST /api/v1/sync/batch body schema
export const syncBatchSchema = z.object({
  source: z.string().min(1),
  sync_run_id: z.string().min(1),
  stores: z.array(z.object({
    name: z.string().min(1),
    color: z.string().optional(),
  })).optional().default([]),
  products: z.array(z.object({
    key: z.string().min(1),
    name: z.string().min(1),
    brand: z.string().nullable(),
    category: z.string().nullable().optional(),
    unit: z.string(),
    unit_type: z.string().nullable().optional(),
    unit_value_g: z.number().nullable().optional(),
  })).optional().default([]),
  prices: z.array(z.object({
    product_key: z.string().min(1),
    store: z.string().min(1),
    price: z.number().int().positive(),
    effective_unit_price: z.number().int().positive(),
    bundle_size: z.number().int().min(1).default(1),
    promo: z.array(z.string()).nullable(),
    promo_type: z.string().nullable().optional(),
    valid_from: z.string().nullable().optional(),
    valid_until: z.string().nullable().optional(),
    image_path: z.string().nullable().optional(),
    scrape_time: z.string(),
    date: z.string().regex(/^\d{4}-\d{2}-\d{2}$/),
    match_method: z.string().nullable().optional(),
    match_confidence: z.number().min(0).max(1).nullable().optional(),
    standardized_promo: z.object({
      normalized: z.array(z.string()),
      types: z.array(z.string()),
      best_type: z.string(),
      discount_pct: z.number().nullable().optional(),
      max_qty: z.number().nullable().optional(),
      display_summary: z.string(),
    }).nullable().optional(),
  })).optional().default([]),
  promos: z.array(z.object({
    key: z.string().min(1),
    display: z.string().min(1),
    type: z.string().nullable().optional(),
    discount_pct: z.number().nullable().optional(),
    max_qty: z.number().nullable().optional(),
    product_count: z.number().int().min(0).default(0),
    stores: z.record(z.string(), z.number()).optional(),
    example_products: z.array(z.string()).optional(),
  })).optional().default([]),
});

// POST /api/v1/sync/images body schema
export const syncImagesSchema = z.object({
  images: z.array(z.object({
    local_path: z.string().min(1),
    r2_key: z.string().min(1),
    r2_url: z.string().url().optional(),
  })).min(1),
});

// Sync response types
export interface SyncBatchResponse {
  sync_run_id: string;
  stores: { inserted: number; updated: number; skipped: number };
  products: { inserted: number; updated: number; skipped: number };
  prices: { inserted: number; updated: number; skipped: number };
  promos: { inserted: number; updated: number; skipped: number };
  errors: { table: string; key: string; error: string }[];
}

export interface SyncImagesResponse {
  updated: number;
  skipped: number;
  errors: { image_path: string; error: string }[];
}
```

**References:** plan.md:155-204 (sync/batch request body), plan.md:206 (idempotency rule), plan.md:213-219 (sync/images request body), database/price_history.json (field types — price is integer, promo is array or null)

**Acceptance criteria:**
- `schemas.ts` updated with `syncBatchSchema`, `syncImagesSchema`, `SyncBatchResponse`, and `SyncImagesResponse`
- `cd web && npx tsc --noEmit` passes
- Schema correctly validates the example body from plan.md:155-204
- **Log message clarity:** Zod error messages are descriptive — field name, expected type, received value
- **Failure handling:**
  - Missing required fields (source, sync_run_id) → validation fails with field name in error
  - Invalid date format (not YYYY-MM-DD) → validation fails with regex mismatch
  - Negative price → validation fails with "price must be positive"
  - Empty arrays → valid (all arrays default to `[]`)
  - Missing optional fields → valid (optional fields default to undefined/null)
- **Code quality:**
  - All field types match D1 schema and source JSON structures exactly
  - `z.record(z.string(), z.number())` for promos.stores (object with string keys and number values)
  - `z.string().url()` for r2_url validation
  - `z.number().int().positive()` for prices (IDR is always positive integer)
  - No `any` types
- **Unit test coverage:** Todo 5 tests schema validation with valid/invalid bodies

**QA:**
- Happy: Schema accepts the plan.md example body → pass
- Failure: Schema rejects body with missing `sync_run_id` → pass
- Failure: Schema rejects body with negative price → pass

**Commit:** Y | feat(api): add Zod validation schemas for sync batch and images endpoints

---

### Todo 3: Implement POST /api/v1/sync/batch

**What to do:**

Add the sync/batch endpoint to `web/functions/api/[[route]].ts`:

```typescript
import { authMiddleware } from './middleware/auth';
import { syncBatchSchema, syncImagesSchema } from './schemas';
import type { SyncBatchResponse, SyncImagesResponse } from './schemas';

// POST /api/v1/sync/batch — protected by auth middleware
app.post('/api/v1/sync/batch', authMiddleware, async (c) => {
  // 1. Parse and validate body
  let body;
  try {
    body = await c.req.json();
  } catch {
    return c.json({ error: 'Bad request', message: 'Invalid JSON body' }, 400);
  }

  const parseResult = syncBatchSchema.safeParse(body);
  if (!parseResult.success) {
    return c.json({ error: 'Validation error', message: parseResult.error.message }, 400);
  }
  const data = parseResult.data;

  // 2. Upsert each table — track counts
  const response: SyncBatchResponse = {
    sync_run_id: data.sync_run_id,
    stores: { inserted: 0, updated: 0, skipped: 0 },
    products: { inserted: 0, updated: 0, skipped: 0 },
    prices: { inserted: 0, updated: 0, skipped: 0 },
    promos: { inserted: 0, updated: 0, skipped: 0 },
    errors: [],
  };

  // 3. Upsert stores
  for (const store of data.stores) {
    try {
      const result = await c.env.DB.prepare(
        'INSERT OR REPLACE INTO stores (name, color) VALUES (?, ?)'
      ).bind(store.name, store.color ?? null).run();
      // INSERT OR REPLACE doesn't distinguish insert vs update — use a SELECT to check
      // For simplicity, count as "updated" if the store already existed
      response.stores.updated++; // Simplified: count all as updated (INSERT OR REPLACE)
    } catch (e) {
      response.stores.skipped++;
      response.errors.push({ table: 'stores', key: store.name, error: String(e) });
    }
  }

  // 4. Upsert products
  for (const product of data.products) {
    try {
      await c.env.DB.prepare(
        'INSERT OR REPLACE INTO products (key, name, brand, category, unit, unit_type, unit_value_g) VALUES (?, ?, ?, ?, ?, ?, ?)'
      ).bind(
        product.key, product.name, product.brand,
        product.category ?? null, product.unit,
        product.unit_type ?? null, product.unit_value_g ?? null
      ).run();
      response.products.updated++;
    } catch (e) {
      response.products.skipped++;
      response.errors.push({ table: 'products', key: product.key, error: String(e) });
    }
  }

  // 5. Upsert prices — JSON-encode promo and standardized_promo
  for (const price of data.prices) {
    try {
      await c.env.DB.prepare(
        `INSERT OR REPLACE INTO prices
        (product_key, store, price, effective_unit_price, bundle_size, promo, promo_type,
         valid_from, valid_until, image_path, scrape_time, date, match_method, match_confidence, standardized_promo)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`
      ).bind(
        price.product_key, price.store, price.price, price.effective_unit_price,
        price.bundle_size, price.promo ? JSON.stringify(price.promo) : null,
        price.promo_type ?? null, price.valid_from ?? null, price.valid_until ?? null,
        price.image_path ?? null, price.scrape_time, price.date,
        price.match_method ?? null, price.match_confidence ?? null,
        price.standardized_promo ? JSON.stringify(price.standardized_promo) : null
      ).run();
      response.prices.updated++;
    } catch (e) {
      response.prices.skipped++;
      response.errors.push({ table: 'prices', key: `${price.product_key}:${price.store}:${price.date}`, error: String(e) });
    }
  }

  // 6. Upsert promos — JSON-encode stores and example_products
  for (const promo of data.promos) {
    try {
      await c.env.DB.prepare(
        `INSERT OR REPLACE INTO promos
        (key, display, type, discount_pct, max_qty, product_count, stores, example_products)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)`
      ).bind(
        promo.key, promo.display, promo.type ?? null,
        promo.discount_pct ?? null, promo.max_qty ?? null,
        promo.product_count,
        promo.stores ? JSON.stringify(promo.stores) : null,
        promo.example_products ? JSON.stringify(promo.example_products) : null
      ).run();
      response.promos.updated++;
    } catch (e) {
      response.promos.skipped++;
      response.errors.push({ table: 'promos', key: promo.key, error: String(e) });
    }
  }

  // 7. Return sync response
  const hasErrors = response.errors.length > 0;
  return c.json(response, hasErrors ? 207 : 200);
});
```

**Key implementation notes:**
- Uses `INSERT OR REPLACE` for all upserts — idempotent on re-sync
- `promo` and `standardized_promo` are JSON-stringified before storing in D1 TEXT columns
- `stores` and `example_products` in promos are JSON-stringified
- If any errors occur, response status is 207 (Multi-Status) — partial success
- If no errors, response status is 200
- Each table is upserted independently — a failure in one table doesn't stop others
- The `errors` array includes the table name, the key of the failed row, and the error message

**References:** plan.md:148-149 (POST /sync/batch), plan.md:155-204 (request body), plan.md:206 (idempotency rule — UNIQUE product_key, store, date), web/schema.sql (D1 schema with UNIQUE constraint), scripts/seed_d1.py (Phase 2 — same JSON encoding pattern)

**Acceptance criteria:**
- `curl -X POST -H "Authorization: Bearer dev-secret-for-local-testing" -H "Content-Type: application/json" -d '{"source":"test","sync_run_id":"20260621_120000","stores":[{"name":"Lotte","color":"#0057A8"}],"products":[{"key":"test-1","name":"Test Product","brand":"Test","unit":"100g","unit_type":"weight","unit_value_g":100}],"prices":[{"product_key":"test-1","store":"Lotte","price":10000,"effective_unit_price":10000,"bundle_size":1,"promo":null,"scrape_time":"2026-06-21T09:00:00","date":"2026-06-21"}],"promos":[]}' http://localhost:8787/api/v1/sync/batch` returns 200 with sync response
- Sync response includes counts for each table (stores, products, prices, promos) and empty errors array
- Data appears in D1: `wrangler d1 execute haqita-db --local --command "SELECT * FROM products WHERE key='test-1'"` returns the test product
- **Idempotency:** POST the same batch twice → second response has same counts, no duplicate rows in D1
- **Log message clarity:** Response includes `sync_run_id` for correlation with the Python script's logs
- **Failure handling:**
  - Invalid JSON body → 400 with "Invalid JSON body"
  - Schema validation failure → 400 with Zod error message
  - Missing auth → 401 (from auth middleware)
  - D1 error on individual row → row is skipped, error recorded in `errors` array, other rows continue
  - All rows fail → 207 with all errors listed
- **Code quality:**
  - All SQL uses `db.prepare().bind()` — parameterized, no injection
  - `INSERT OR REPLACE` for idempotency — same as seed script (Phase 2)
  - JSON fields are stringified with `JSON.stringify()` before storage
  - Error handling is per-row, not per-batch — one bad row doesn't kill the batch
  - 207 status code for partial success follows HTTP semantics
  - No `any` types — all response fields typed via `SyncBatchResponse`
- **Unit test coverage:** Todo 5 tests the endpoint with valid/invalid bodies, idempotency, and error handling
- **Documentation:** Todo 6 documents the endpoint with example request and response

**QA:**
- Happy: POST valid batch → 200 with counts, data in D1 → pass
- Failure: POST same batch twice → no duplicates → pass
- Failure: POST with invalid JSON → 400 → pass
- Failure: POST without auth → 401 → pass

**Commit:** Y | feat(api): add POST /sync/batch endpoint with idempotent upserts

---

### Todo 4: Implement POST /api/v1/sync/images

**What to do:**

Add the sync/images endpoint to `web/functions/api/[[route]].ts`:

```typescript
// POST /api/v1/sync/images — protected by auth middleware
// Records R2 URLs for images. The actual upload happens directly from the laptop to R2.
// This endpoint updates prices.image_r2_url where image_path matches the local_path.
app.post('/api/v1/sync/images', authMiddleware, async (c) => {
  let body;
  try {
    body = await c.req.json();
  } catch {
    return c.json({ error: 'Bad request', message: 'Invalid JSON body' }, 400);
  }

  const parseResult = syncImagesSchema.safeParse(body);
  if (!parseResult.success) {
    return c.json({ error: 'Validation error', message: parseResult.error.message }, 400);
  }
  const data = parseResult.data;

  const response: SyncImagesResponse = {
    updated: 0,
    skipped: 0,
    errors: [],
  };

  for (const image of data.images) {
    try {
      // If r2_url is provided, update prices.image_r2_url for all rows matching image_path
      // If r2_url is not provided, derive it from the R2 bucket public URL + r2_key
      const r2Url = image.r2_url ?? `https://pub-<hash>.r2.dev/${image.r2_key}`;

      const result = await c.env.DB.prepare(
        'UPDATE prices SET image_r2_url = ? WHERE image_path = ?'
      ).bind(r2Url, image.local_path).run();

      if (result.meta.changes > 0) {
        response.updated++;
      } else {
        response.skipped++;
      }
    } catch (e) {
      response.errors.push({ image_path: image.local_path, error: String(e) });
    }
  }

  const hasErrors = response.errors.length > 0;
  return c.json(response, hasErrors ? 207 : 200);
});
```

**Key implementation notes:**
- This endpoint implements Option A (plan.md:212-219) — manifest-only. The actual image upload happens from the laptop to R2 directly (Phase 5).
- The endpoint updates `prices.image_r2_url` for all rows where `image_path` matches `local_path`.
- If `r2_url` is not provided in the request, it's derived from the R2 bucket public URL + `r2_key`. The R2 public URL is configured in Phase 1 (Todo 3).
- `result.meta.changes` from D1 tells how many rows were updated — if 0, the image_path doesn't exist in any price row (skipped).

**References:** plan.md:150 (POST /sync/images), plan.md:208-219 (Option A — manifest-only), plan.md:357-375 (image handling Option A details), web/schema.sql (prices.image_r2_url column)

**Acceptance criteria:**
- `curl -X POST -H "Authorization: Bearer dev-secret-for-local-testing" -H "Content-Type: application/json" -d '{"images":[{"local_path":"database/scrape/superindo/20260613/test.jpg","r2_key":"superindo/20260613/test.jpg","r2_url":"https://pub-hash.r2.dev/superindo/20260613/test.jpg"}]}' http://localhost:8787/api/v1/sync/images` returns 200 with `{"updated": N, "skipped": 0, "errors": []}`
- `wrangler d1 execute haqita-db --local --command "SELECT image_r2_url FROM prices WHERE image_path='database/scrape/superindo/20260613/test.jpg' LIMIT 1"` returns the R2 URL
- **Log message clarity:** Response includes `updated` and `skipped` counts for easy verification
- **Failure handling:**
  - Image path not found in prices → skipped (not an error)
  - D1 error on update → recorded in errors array, other images continue
  - Invalid JSON → 400
  - Missing auth → 401
- **Code quality:**
  - Uses `UPDATE` with `WHERE image_path = ?` — parameterized
  - `result.meta.changes` checks if any rows were affected
  - Derives R2 URL from r2_key if not provided (convenience for the Python script)
  - No `any` types
- **Unit test coverage:** Todo 5 tests the endpoint with valid/invalid manifests and error handling
- **Documentation:** Todo 6 documents the endpoint

**QA:**
- Happy: POST image manifest → 200 with updated count, D1 shows R2 URLs → pass
- Failure: POST with image_path that doesn't exist → skipped count > 0 → pass
- Failure: POST without auth → 401 → pass

**Commit:** Y | feat(api): add POST /sync/images endpoint for R2 URL recording

---

### Todo 5: Write unit tests

**What to do:**

Create test files for auth middleware, Zod schemas, and sync endpoints.

1. Create `web/tests/auth.test.ts`:
   - `test('auth middleware passes with valid Bearer token')` — mock Hono context with valid Authorization header and matching SCRAPER_SECRET → next() is called
   - `test('auth middleware returns 401 for missing Authorization header')` — no Authorization header → 401 with "Missing Authorization header"
   - `test('auth middleware returns 401 for wrong format')` — "Basic xyz" → 401 with format explanation
   - `test('auth middleware returns 401 for invalid token')` — "Bearer wrong-token" → 401 with "Invalid token"
   - `test('auth middleware returns 500 when SCRAPER_SECRET not configured')` — no SCRAPER_SECRET in env → 500
   - `test('auth middleware is case-insensitive for Bearer prefix')` — "bearer token" → passes

2. Create `web/tests/sync-schemas.test.ts`:
   - `test('syncBatchSchema accepts valid full body')` — all fields populated
   - `test('syncBatchSchema accepts minimal body')` — only source and sync_run_id, empty arrays
   - `test('syncBatchSchema rejects missing source')` — no source field → validation fails
   - `test('syncBatchSchema rejects missing sync_run_id')` — no sync_run_id → validation fails
   - `test('syncBatchSchema rejects negative price')` — price: -100 → validation fails
   - `test('syncBatchSchema rejects invalid date format')` — date: "2026/06/21" → validation fails
   - `test('syncBatchSchema rejects non-integer price')` — price: 100.5 → validation fails
   - `test('syncBatchSchema accepts null promo')` — promo: null → valid
   - `test('syncBatchSchema accepts null standardized_promo')` — standardized_promo: null → valid
   - `test('syncBatchSchema accepts absent standardized_promo')` — no standardized_promo field → valid
   - `test('syncImagesSchema accepts valid manifest')` — images array with local_path and r2_key
   - `test('syncImagesSchema rejects empty images array')` — images: [] → validation fails
   - `test('syncImagesSchema rejects missing local_path')` — no local_path → validation fails

3. Create `web/tests/sync-endpoints.test.ts` — integration tests against local D1:
   - `test('POST /sync/batch with valid body upserts data')` — POST valid batch, verify data in D1
   - `test('POST /sync/batch is idempotent')` — POST same batch twice, verify no duplicate rows
   - `test('POST /sync/batch returns 400 for invalid JSON')` — POST with malformed JSON
   - `test('POST /sync/batch returns 400 for validation failure')` — POST with missing required field
   - `test('POST /sync/batch returns 401 without auth')` — POST without Authorization header
   - `test('POST /sync/batch returns 207 for partial success')` — POST with one invalid price row, verify other rows are upserted and error is recorded
   - `test('POST /sync/images updates image_r2_url')` — POST image manifest, verify D1 has R2 URLs
   - `test('POST /sync/images skips non-existent image_path')` — POST with image_path that doesn't exist in prices
   - `test('POST /sync/images returns 401 without auth')` — POST without Authorization header

**References:** web/functions/api/middleware/auth.ts (auth middleware to test), web/functions/api/schemas.ts (Zod schemas to test), web/tests/schemas.test.ts (from Phase 3 — test pattern to follow)

**Acceptance criteria:**
- `cd web && npx vitest run` passes all tests with 0 failures
- `cd web && npx tsc --noEmit` still passes
- **Log message clarity:** Vitest output shows each test name and pass/fail status
- **Failure handling:**
  - Auth tests verify all 401/500 error cases
  - Schema tests verify all validation failure cases
  - Endpoint tests verify idempotency and partial success behavior
- **Code quality:**
  - Test file naming: `*.test.ts`
  - Tests are independent — no shared state
  - Mock Hono context where needed using `vi.fn()` or manual mocks
  - Integration tests use local D1 (requires `wrangler d1 execute --local` setup)
  - No `any` types in test assertions
- **Unit test coverage:** This IS the unit test file. Minimum test count:
  - auth.test.ts: 6 tests
  - sync-schemas.test.ts: 13 tests
  - sync-endpoints.test.ts: 9 tests
  - **Total: 28 tests minimum**

**QA:**
- Happy: `npx vitest run` shows 28+ passed → pass
- Failure: Any test fails → fix implementation, not the test

**Commit:** Y | test(api): add unit tests for auth middleware, sync schemas, and sync endpoints

---

### Todo 6: Write documentation

**What to do:**

Create `docs/staging/api-sync-endpoints.md` following the existing documentation pattern.

**Document structure:**
1. **H1 title:** `# API Sync Endpoints`
2. **Overview table:** Base URL, Auth (Bearer token), Content-Type, Rate Limit (Phase 7)
3. **Authentication section:** How the Bearer token works, how to set SCRAPER_SECRET, how to pass the header
4. **POST /api/v1/sync/batch section:**
   - Request body schema (table of all fields with types and descriptions)
   - Example request (curl command with full body from plan.md:155-204)
   - Example response (200 with counts)
   - Error responses (400, 401, 207)
   - Idempotency explanation
5. **POST /api/v1/sync/images section:**
   - Request body schema
   - Example request
   - Example response
   - Error responses
   - How R2 URLs are recorded
6. **Sync response format section:** Table of response fields (sync_run_id, counts per table, errors array)
7. **Local testing section:** How to test with curl and the dev secret

**References:** docs/staging/publish-html.md (documentation template), plan.md:145-231 (sync endpoint design), web/functions/api/[[route]].ts (actual implementation)

**Acceptance criteria:**
- `docs/staging/api-sync-endpoints.md` exists with all sections
- Both endpoints fully documented with example requests and responses
- **Log message clarity:** Documentation includes exact curl commands for testing
- **Failure handling:** All error cases (400, 401, 207, 500) documented
- **Code quality:** Matches existing `docs/staging/*.md` style
- **Unit test coverage:** N/A — documentation

**QA:**
- Happy: Open `docs/staging/api-sync-endpoints.md` — all sections present → pass
- Failure: Missing endpoint → add documentation

**Commit:** Y | docs: add API sync endpoints documentation

---

### Todo 7: Final verification

**What to do:**

Run the complete verification checklist:

1. Start local dev server:
   ```bash
   cd web && npx wrangler pages dev --local &
   sleep 5
   ```

2. Verify auth:
   ```bash
   # No auth → 401
   curl -s -o /dev/null -w "%{http_code}" -X POST http://localhost:8787/api/v1/sync/batch -d '{}'
   # Expected: 401

   # Wrong token → 401
   curl -s -o /dev/null -w "%{http_code}" -X POST -H "Authorization: Bearer wrong" http://localhost:8787/api/v1/sync/batch -d '{}'
   # Expected: 401

   # Valid auth, invalid body → 400
   curl -s -o /dev/null -w "%{http_code}" -X POST -H "Authorization: Bearer dev-secret-for-local-testing" -H "Content-Type: application/json" -d '{}' http://localhost:8787/api/v1/sync/batch
   # Expected: 400
   ```

3. Verify sync/batch:
   ```bash
   # Valid batch
   curl -s -X POST -H "Authorization: Bearer dev-secret-for-local-testing" -H "Content-Type: application/json" \
     -d '{"source":"test","sync_run_id":"20260621_120000","stores":[],"products":[{"key":"verify-1","name":"Verify Product","brand":"Test","unit":"100g","unit_type":"weight","unit_value_g":100}],"prices":[{"product_key":"verify-1","store":"Lotte","price":15000,"effective_unit_price":15000,"bundle_size":1,"promo":null,"scrape_time":"2026-06-21T10:00:00","date":"2026-06-21"}],"promos":[]}' \
     http://localhost:8787/api/v1/sync/batch | python3 -m json.tool
   # Expected: 200 with counts

   # Idempotency — same batch again
   curl -s -X POST -H "Authorization: Bearer dev-secret-for-local-testing" -H "Content-Type: application/json" \
     -d '{"source":"test","sync_run_id":"20260621_120000","stores":[],"products":[{"key":"verify-1","name":"Verify Product","brand":"Test","unit":"100g","unit_type":"weight","unit_value_g":100}],"prices":[{"product_key":"verify-1","store":"Lotte","price":15000,"effective_unit_price":15000,"bundle_size":1,"promo":null,"scrape_time":"2026-06-21T10:00:00","date":"2026-06-21"}],"promos":[]}' \
     http://localhost:8787/api/v1/sync/batch | python3 -m json.tool
   # Expected: 200 with same counts, no extra rows in D1

   # Verify in D1
   wrangler d1 execute haqita-db --local --command "SELECT COUNT(*) FROM prices WHERE product_key='verify-1'"
   # Expected: 1 (not 2)
   ```

4. Verify sync/images:
   ```bash
   curl -s -X POST -H "Authorization: Bearer dev-secret-for-local-testing" -H "Content-Type: application/json" \
     -d '{"images":[{"local_path":"database/scrape/superindo/20260613/test.jpg","r2_key":"superindo/20260613/test.jpg","r2_url":"https://pub-hash.r2.dev/superindo/20260613/test.jpg"}]}' \
     http://localhost:8787/api/v1/sync/images | python3 -m json.tool
   ```

5. Verify type checking and tests:
   ```bash
   cd web && npx tsc --noEmit
   cd web && npx vitest run
   ```

6. Kill the dev server:
   ```bash
   kill %1
   ```

**References:** All previous todos

**Acceptance criteria:**
- All verification steps pass
- Idempotency confirmed — same batch twice produces no duplicates
- **Log message clarity:** All responses are well-formed JSON
- **Failure handling:** All error cases (401, 400) return correct status codes
- **Documentation:** Verification confirms `docs/staging/api-sync-endpoints.md` is accurate

**QA:**
- Happy: All steps pass → Phase 4 complete
- Failure: Idempotency fails → check that INSERT OR REPLACE is used, check UNIQUE constraint in schema

**Commit:** Y | test: verify sync endpoints with auth, idempotency, and error handling

---

## Final verification wave
- [ ] F1. Plan compliance audit — both sync endpoints implemented, auth middleware works, no changes to read endpoints
- [ ] F2. Code quality review — `tsc --noEmit` clean, `vitest run` all pass, no `any` types, all SQL parameterized, idempotency verified
- [ ] F3. Real manual QA — curl with valid/invalid auth, valid/invalid body, idempotency test, images endpoint test
- [ ] F4. Scope fidelity — no rate limiting, no CORS, no image upload through API, no read endpoint changes

---

## Commit strategy
- One commit per todo (Todos 1-7)
- Commit messages: `feat(api):` for endpoints/middleware, `test(api):` for tests, `docs:` for documentation, `test:` for verification

---

## Success criteria
1. `POST /api/v1/sync/batch` accepts valid batch and upserts data into D1
2. `POST /api/v1/sync/batch` is idempotent — same batch twice produces no duplicates
3. `POST /api/v1/sync/images` records R2 URLs in `prices.image_r2_url`
4. Auth middleware returns 401 for missing/invalid tokens, passes valid tokens
5. Zod validation returns 400 for invalid bodies with descriptive error messages
6. Sync response includes counts per table and errors array
7. `npx tsc --noEmit` passes with zero errors
8. `npx vitest run` passes 28+ tests
9. `docs/staging/api-sync-endpoints.md` documents both endpoints with examples

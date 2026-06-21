# Phase 7: Security Hardening & E2E Verification

## TL;DR (For humans)

**What you'll get:** Production-grade security configuration (SCRAPER_SECRET as Cloudflare secret, security headers, rate limiting via WAF), a documented secret rotation procedure, an end-to-end integration test (pipeline → sync → browse), and a pre-deployment checklist. This phase validates the entire system works together from scrape to browser.

**Why this approach:** Security is applied last so it doesn't complicate development, but before declaring the system production-ready. The E2E test validates all 7 phases work together — if any phase has a hidden integration bug, this is where it surfaces.

**What it will NOT do:** Add user authentication (out of scope per plan.md:394), add OAuth (out of scope), or implement Cloudflare Access (Model 1 chosen per plan.md:630-649).

**Effort:** Medium (~3-4 hours: secret setup, security headers, WAF rules, E2E test, documentation)
**Risk:** Low — security configuration is additive; E2E test is read-only

---

## Scope

### Must have
1. `SCRAPER_SECRET` set as Cloudflare Workers secret via `wrangler secret put`
2. Security headers middleware added to Hono app (X-Content-Type-Options, X-Frame-Options, Referrer-Policy)
3. Cloudflare WAF rate limiting rule for `POST /api/v1/sync/*` (documented, configured via dashboard)
4. Secret rotation procedure documented
5. End-to-end integration test: `tests/cloudflare/test_e2e.py` (run pipeline → sync → query API → verify counts)
6. Pre-deployment checklist at `docs/staging/pre-deployment-checklist.md`
7. Final documentation review and update

### Must NOT have
1. No user authentication — plan.md:394 explicitly out of scope
2. No OAuth — plan.md:394
3. No Cloudflare Access — Model 1 chosen (plan.md:630-649)
4. No CORS configuration — same origin (plan.md:388)
5. No changes to API endpoint logic — security is middleware and config only
6. No changes to the Python pipeline stages 1-4

---

## Verification strategy
- **Test decision:** E2E integration test + manual verification of security headers
- **Evidence:** E2E test output, curl output showing security headers, WAF rule configuration screenshot
- **Security headers verified:** `curl -I https://haqita.pages.dev/api/v1/health` shows X-Content-Type-Options, X-Frame-Options, Referrer-Policy
- **Rate limiting verified:** `curl` POST /sync/batch rapidly → eventually gets 429 (documented, may need manual testing)
- **E2E verified:** test passes with correct data counts at each stage

---

## Execution strategy

### Dependency matrix
| Todo | Depends on | Blocks | Can parallelize with |
|------|-----------|--------|---------------------|
| 1. Set SCRAPER_SECRET as Cloudflare secret | Phase 6 | 5 | 2, 3, 4 |
| 2. Add security headers middleware | Phase 6 | 5 | 1, 3, 4 |
| 3. Configure WAF rate limiting | Phase 6 | 5 | 1, 2, 4 |
| 4. Write E2E integration test | Phase 6 | 5 | 1, 2, 3 |
| 5. Write documentation (secret rotation + checklist) | 1, 2, 3, 4 | 6 | — |
| 6. Final verification | 5 | — | — |

---

## Todos

### Todo 1: Set SCRAPER_SECRET as Cloudflare secret

**What to do:**

1. Generate a strong secret (use a random 32+ character string):
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. Set it as a Cloudflare secret for the Pages project:
   ```bash
   cd web && npx wrangler pages secret put SCRAPER_SECRET --project-name haqita
   ```
   This prompts for the secret value. Paste the generated secret.

3. Update `.env` on the laptop with the same secret:
   ```bash
   echo "SCRAPER_SECRET=<your-generated-secret>" >> .env
   ```

4. Verify the secret is set:
   ```bash
   cd web && npx wrangler pages secret list --project-name haqita
   ```
   **Expected:** Shows `SCRAPER_SECRET` in the list.

5. Verify sync works with the production secret:
   ```bash
   export SCRAPER_SECRET=<your-generated-secret>
   python scripts/sync_cloudflare.py --api-url https://haqita.pages.dev/api/v1 --verbose
   ```
   **Expected:** Batch sync succeeds (no 401 error).

**References:** plan.md:384 (scraper auth via SCRAPER_SECRET), plan.md:390 (wrangler secret put), plan.md:561-576 (env vars), Phase 4 Todo 1 (auth middleware implementation)

**Acceptance criteria:**
- `wrangler pages secret list` shows `SCRAPER_SECRET`
- `python scripts/sync_cloudflare.py --api-url https://haqita.pages.dev/api/v1` succeeds (no 401)
- The same secret value is in both Cloudflare and `.env` on the laptop
- **Log message clarity:** `wrangler pages secret put` confirms the secret was set; sync script logs success
- **Failure handling:**
  - Wrong secret → sync returns 401 → check that `.env` and Cloudflare secret match
  - `wrangler pages secret put` fails → check `wrangler whoami` is authenticated
- **Code quality:** Secret is never committed to git (`.env` is in `.gitignore`); generated with `secrets.token_urlsafe(32)` (cryptographically secure)
- **Unit test coverage:** N/A — infrastructure configuration
- **Documentation:** Todo 5 documents the rotation procedure

**QA:**
- Happy: Sync to production succeeds with the secret → pass
- Failure: Sync returns 401 → secrets don't match → fix

**Commit:** N — secrets are not code changes; update `.env` locally (not committed)

---

### Todo 2: Add security headers middleware

**What to do:**

Create `web/functions/api/middleware/security.ts`:
```typescript
import { createMiddleware } from 'hono/factory';

// Security headers middleware — adds standard security headers to all API responses.
// Applied to all /api/v1/* routes.
export const securityHeadersMiddleware = createMiddleware(async (c, next) => {
  await next();

  c.header('X-Content-Type-Options', 'nosniff');
  c.header('X-Frame-Options', 'DENY');
  c.header('Referrer-Policy', 'strict-origin-when-cross-origin');
  c.header('X-XSS-Protection', '1; mode=block');
});
```

Apply the middleware in `web/functions/api/[[route]].ts` — add it to the Hono app before any routes:
```typescript
import { securityHeadersMiddleware } from './middleware/security';

const app = new Hono<{ Bindings: Bindings }>();

// Apply security headers to all responses
app.use('*', securityHeadersMiddleware);

// ... existing routes follow
```

Verify the headers are present:
```bash
# Local
curl -I http://localhost:8787/api/v1/health
# Expected headers: X-Content-Type-Options: nosniff, X-Frame-Options: DENY, etc.

# After deploy
curl -I https://haqita.pages.dev/api/v1/health
# Expected: same headers
```

**References:** plan.md:378-393 (security section), OWASP security headers: https://owasp.org/www-project-secure-headers/, Hono middleware docs

**Acceptance criteria:**
- `web/functions/api/middleware/security.ts` exists with the security headers middleware
- `curl -I http://localhost:8787/api/v1/health` returns headers: `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: strict-origin-when-cross-origin`, `X-XSS-Protection: 1; mode=block`
- `cd web && npx tsc --noEmit` passes
- **Log message clarity:** Security headers are visible in curl -I output — no extra logging needed
- **Failure handling:** If headers are missing, check that middleware is registered before routes with `app.use('*', securityHeadersMiddleware)`
- **Code quality:**
  - Middleware uses `createMiddleware` from Hono — follows existing middleware pattern (same as auth middleware in Phase 4)
  - `await next()` ensures headers are added after the route handler runs (so they apply to all responses including errors)
  - No `any` types
  - Headers follow OWASP recommendations
- **Unit test coverage:** Todo 4 E2E test includes a check for security headers
- **Documentation:** Todo 5 documents the security headers

**QA:**
- Happy: `curl -I /api/v1/health` shows all 4 security headers → pass
- Failure: Headers missing → check middleware registration order

**Commit:** Y | feat(api): add security headers middleware for all API responses

---

### Todo 3: Configure WAF rate limiting

**What to do:**

Configure rate limiting via the Cloudflare dashboard (WAF rules are not code — they are dashboard configurations).

**Rate limiting rules to configure:**

1. **Sync endpoint rate limit** (strict):
   - Go to Cloudflare Dashboard → your domain (or `pages.dev` subdomain) → Security → WAF → Rate limiting rules
   - Create a rule:
     - **Name:** "Sync endpoint rate limit"
     - **When incoming requests match:** URI Path starts with `/api/v1/sync/`
     - **Method:** POST
     - **Then take action:** Block
     - **Rate:** 10 requests per minute per IP
   - This limits sync API calls to 10/min per IP — the Python sync script makes ~2-3 calls per sync run, so this is generous enough for legitimate use but blocks abuse.

2. **General API rate limit** (lenient):
   - Create another rule:
     - **Name:** "General API rate limit"
     - **When incoming requests match:** URI Path starts with `/api/v1/`
     - **Then take action:** Block
     - **Rate:** 100 requests per minute per IP
   - This is generous for 1-10 internal users but blocks automated scraping.

3. **Document the rules** in `docs/staging/security-configuration.md` (created in Todo 5):
   - Rule name, match condition, rate limit, action
   - How to modify or disable rules
   - How to test rate limiting (send rapid requests and verify 429 response)

**Note:** WAF rate limiting on `*.pages.dev` subdomains may have limitations depending on the Cloudflare plan. If WAF rules are not available on the free tier for Pages, document this as a known limitation and note that rate limiting can be added when a custom domain is configured.

**References:** plan.md:387 (API rate limiting via WAF rule), Cloudflare WAF docs: https://developers.cloudflare.com/waf/rate-limiting-rules/

**Acceptance criteria:**
- WAF rate limiting rules are configured in the Cloudflare dashboard (or documented as a known limitation if not available on free tier)
- Rate limits are documented in `docs/staging/security-configuration.md`
- **Log message clarity:** When rate limited, Cloudflare returns a 429 response with a plain text body — this is handled by Cloudflare, not our code
- **Failure handling:** If WAF is not available on free tier, document the limitation and note that `SCRAPER_SECRET` still protects the write path
- **Code quality:** Rate limiting is infrastructure config, not code — follows Cloudflare best practices
- **Unit test coverage:** N/A — WAF rules verified manually
- **Documentation:** Todo 5

**QA:**
- Happy: WAF rules configured, documented → pass
- Failure: WAF not available on free tier → document as known limitation → pass

**Commit:** Y | docs: add security configuration documentation with WAF rate limiting rules

---

### Todo 4: Write E2E integration test

**What to do:**

Create `tests/cloudflare/test_e2e.py` — an end-to-end integration test that validates the full system:

```python
"""
End-to-end integration test for the Cloudflare migration.

Tests the full flow: pipeline output → sync script → API → data verification.

Prerequisites:
    - Local API running (wrangler pages dev --local)
    - Local D1 seeded (python scripts/seed_d1.py --apply)
    - SCRAPER_SECRET set in environment

Usage:
    python -m pytest tests/cloudflare/test_e2e.py -v
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

ROOT = Path(__file__).resolve().parent.parent.parent
API_URL = os.getenv("E2E_API_URL", "http://localhost:8787/api/v1")
SCRAPER_SECRET = os.getenv("SCRAPER_SECRET", "dev-secret-for-local-testing")


@pytest.fixture(scope="module")
def api_available():
    """Verify the API is running before tests."""
    try:
        resp = requests.get(f"{API_URL}/health", timeout=5)
        if resp.status_code != 200:
            pytest.skip("API not running. Start with: cd web && npx wrangler pages dev --local")
    except requests.ConnectionError:
        pytest.skip("API not running. Start with: cd web && npx wrangler pages dev --local")
    return True


class TestE2EFullFlow:
    """End-to-end test: pipeline data → sync → API → verify."""

    def test_stores_endpoint_returns_correct_stores(self, api_available):
        """GET /stores should return Lotte and Superindo."""
        resp = requests.get(f"{API_URL}/stores")
        assert resp.status_code == 200
        data = resp.json()
        store_names = [s["name"] for s in data["data"]]
        assert "Lotte" in store_names
        assert "Superindo" in store_names

    def test_products_endpoint_returns_paginated_results(self, api_available):
        """GET /products should return paginated products with correct shape."""
        resp = requests.get(f"{API_URL}/products?limit=5")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert "pagination" in data
        assert len(data["data"]) <= 5
        assert "has_more" in data["pagination"]
        # Each product should have required fields
        if data["data"]:
            product = data["data"][0]
            assert "key" in product
            assert "name" in product
            assert "stores" in product
            assert "price_min" in product

    def test_product_detail_returns_full_data(self, api_available):
        """GET /products/:key should return product with stores array."""
        # First get a product key from the list
        list_resp = requests.get(f"{API_URL}/products?limit=1")
        products = list_resp.json()["data"]
        if not products:
            pytest.skip("No products in database")
        key = products[0]["key"]

        # Get the detail
        resp = requests.get(f"{API_URL}/products/{key}")
        assert resp.status_code == 200
        product = resp.json()
        assert product["key"] == key
        assert "stores" in product
        assert isinstance(product["stores"], list)

    def test_product_history_returns_snapshots(self, api_available):
        """GET /products/:key/history should return snapshots sorted by date."""
        list_resp = requests.get(f"{API_URL}/products?limit=1")
        products = list_resp.json()["data"]
        if not products:
            pytest.skip("No products in database")
        key = products[0]["key"]

        resp = requests.get(f"{API_URL}/products/{key}/history")
        assert resp.status_code == 200
        data = resp.json()
        assert "snapshots" in data
        if data["snapshots"]:
            # Verify sorted by date ascending
            dates = [s["date"] for s in data["snapshots"]]
            assert dates == sorted(dates)

    def test_search_returns_matching_products(self, api_available):
        """GET /search?q=... should return products matching the query."""
        resp = requests.get(f"{API_URL}/search?q=indomie&limit=10")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        # Each result should contain "indomie" in name, brand, or unit (case-insensitive)
        for product in data["data"]:
            text = f"{product.get('name', '')} {product.get('brand', '')} {product.get('unit', '')}".lower()
            assert "indomie" in text

    def test_promos_endpoint_returns_promo_catalog(self, api_available):
        """GET /promos should return promos sorted by product_count."""
        resp = requests.get(f"{API_URL}/promos")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        if len(data["data"]) > 1:
            # Verify sorted by product_count descending
            counts = [p["product_count"] for p in data["data"]]
            assert counts == sorted(counts, reverse=True)

    def test_brochures_endpoint_returns_brochure_metadata(self, api_available):
        """GET /brochures should return brochures grouped by image_path."""
        resp = requests.get(f"{API_URL}/brochures")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        if data["data"]:
            brochure = data["data"][0]
            assert "image_path" in brochure
            assert "store" in brochure
            assert "product_count" in brochure

    def test_stats_endpoint_returns_correct_counts(self, api_available):
        """GET /stats should return summary stats matching seed data."""
        resp = requests.get(f"{API_URL}/stats")
        assert resp.status_code == 200
        stats = resp.json()
        assert "total_products_lotte" in stats
        assert "total_products_superindo" in stats
        assert stats["total_products_lotte"] > 0
        assert stats["total_products_superindo"] > 0

    def test_sync_batch_with_valid_data(self, api_available):
        """POST /sync/batch with valid data should upsert successfully."""
        batch = {
            "source": "e2e-test",
            "sync_run_id": "e2e_test_001",
            "stores": [{"name": "TestStore", "color": "#FF0000"}],
            "products": [{
                "key": "e2e-test-product",
                "name": "E2E Test Product",
                "brand": "TestBrand",
                "unit": "100g",
                "unit_type": "weight",
                "unit_value_g": 100,
            }],
            "prices": [{
                "product_key": "e2e-test-product",
                "store": "TestStore",
                "price": 9999,
                "effective_unit_price": 9999,
                "bundle_size": 1,
                "promo": None,
                "scrape_time": "2026-06-21T12:00:00",
                "date": "2026-06-21",
            }],
            "promos": [],
        }
        headers = {"Authorization": f"Bearer {SCRAPER_SECRET}", "Content-Type": "application/json"}
        resp = requests.post(f"{API_URL}/sync/batch", json=batch, headers=headers)
        assert resp.status_code == 200
        result = resp.json()
        assert result["sync_run_id"] == "e2e_test_001"
        assert len(result["errors"]) == 0

        # Verify data in D1 via API
        detail_resp = requests.get(f"{API_URL}/products/e2e-test-product")
        assert detail_resp.status_code == 200
        product = detail_resp.json()
        assert product["name"] == "E2E Test Product"

    def test_sync_batch_idempotent(self, api_available):
        """POST /sync/batch twice with same data should not create duplicates."""
        batch = {
            "source": "e2e-test",
            "sync_run_id": "e2e_test_002",
            "stores": [],
            "products": [{
                "key": "e2e-idempotent-test",
                "name": "Idempotent Test",
                "brand": "Test",
                "unit": "50g",
                "unit_type": "weight",
                "unit_value_g": 50,
            }],
            "prices": [{
                "product_key": "e2e-idempotent-test",
                "store": "TestStore",
                "price": 5000,
                "effective_unit_price": 5000,
                "bundle_size": 1,
                "promo": None,
                "scrape_time": "2026-06-21T13:00:00",
                "date": "2026-06-21",
            }],
            "promos": [],
        }
        headers = {"Authorization": f"Bearer {SCRAPER_SECRET}", "Content-Type": "application/json"}

        # First POST
        resp1 = requests.post(f"{API_URL}/sync/batch", json=batch, headers=headers)
        assert resp1.status_code == 200

        # Second POST — same data
        resp2 = requests.post(f"{API_URL}/sync/batch", json=batch, headers=headers)
        assert resp2.status_code == 200

        # Verify no duplicate in D1 — product should appear once
        search_resp = requests.get(f"{API_URL}/search?q=Idempotent&limit=10")
        results = search_resp.json()["data"]
        matching = [p for p in results if p["key"] == "e2e-idempotent-test"]
        assert len(matching) == 1  # Not 2

    def test_sync_batch_rejects_invalid_auth(self, api_available):
        """POST /sync/batch without auth should return 401."""
        resp = requests.post(f"{API_URL}/sync/batch", json={"source": "test", "sync_run_id": "x", "stores": [], "products": [], "prices": [], "promos": []})
        assert resp.status_code == 401

    def test_security_headers_present(self, api_available):
        """API responses should include security headers."""
        resp = requests.get(f"{API_URL}/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"
        assert resp.headers.get("X-Frame-Options") == "DENY"
        assert "Referrer-Policy" in resp.headers

    def test_404_for_unknown_route(self, api_available):
        """Unknown API routes should return 404 JSON."""
        resp = requests.get(f"{API_URL}/nonexistent")
        assert resp.status_code == 404
        data = resp.json()
        assert "error" in data

    def test_400_for_invalid_query_params(self, api_available):
        """Invalid query params should return 400."""
        resp = requests.get(f"{API_URL}/products?limit=0")
        assert resp.status_code == 400
```

**References:** tests/integration/test_base.py (integration test pattern), all previous phases (E2E validates the full stack), plan.md:463-466 (integration test spec)

**Acceptance criteria:**
- `tests/cloudflare/test_e2e.py` exists with all test classes shown above
- `python -m pytest tests/cloudflare/test_e2e.py -v` passes all tests when API is running
- Tests are automatically skipped (not failed) when API is not running
- **Log message clarity:** pytest output shows each E2E test name with pass/fail/skip status
- **Failure handling:**
  - API not running → tests skipped with message explaining how to start it
  - D1 not seeded → tests for data endpoints may fail → run `python scripts/seed_d1.py --apply` first
  - SCRAPER_SECRET wrong → sync tests fail with 401 → check secret matches
- **Code quality:**
  - Uses `pytest.fixture(scope="module")` for API availability check — runs once per module
  - Uses `pytest.skip()` for missing prerequisites — tests don't fail if API is not running
  - E2E test product keys are prefixed with `e2e-` to avoid conflicts with real data
  - Idempotency test verifies no duplicates by checking search results
  - Security header test verifies middleware from Phase 7 Todo 2
  - All assertions use plain `assert`
  - No `@pytest.mark.skip` on individual tests — only the module fixture skips
- **Unit test coverage:** This IS the E2E test file. Minimum test count: 15 tests

**QA:**
- Happy: `python -m pytest tests/cloudflare/test_e2e.py -v` shows 15 passed → pass
- Failure: API not running → tests skipped → pass (start API and re-run)

**Commit:** Y | test(cloudflare): add end-to-end integration test for full system validation

---

### Todo 5: Write documentation (secret rotation + pre-deployment checklist)

**What to do:**

Create two documentation files:

**1. `docs/staging/security-configuration.md`:**
```markdown
# Security Configuration

## SCRAPER_SECRET

The SCRAPER_SECRET is a bearer token that protects the sync API endpoints.

### Setting the Secret

On Cloudflare:
```bash
cd web && npx wrangler pages secret put SCRAPER_SECRET --project-name haqita
```

On the laptop:
```bash
echo "SCRAPER_SECRET=your_secret" >> .env
```

### Secret Rotation Procedure

1. Generate a new secret:
   ```bash
   python3 -c "import secrets; print(secrets.token_urlsafe(32))"
   ```

2. Update the Cloudflare secret:
   ```bash
   cd web && npx wrangler pages secret put SCRAPER_SECRET --project-name haqita
   ```
   Enter the new secret when prompted.

3. Update `.env` on the laptop:
   ```bash
   # Edit .env and replace the old SCRAPER_SECRET value
   ```

4. Verify the new secret works:
   ```bash
   python scripts/sync_cloudflare.py --api-url https://haqita.pages.dev/api/v1 --dry-run
   ```

5. The old secret is immediately invalid — no downtime.

### Security Headers

| Header | Value | Purpose |
|--------|-------|---------|
| X-Content-Type-Options | nosniff | Prevents MIME type sniffing |
| X-Frame-Options | DENY | Prevents clickjacking |
| Referrer-Policy | strict-origin-when-cross-origin | Limits referrer information |
| X-XSS-Protection | 1; mode=block | Enables XSS filtering |

### Rate Limiting (WAF Rules)

| Rule | Match | Rate | Action |
|------|-------|------|--------|
| Sync endpoint | POST /api/v1/sync/* | 10 req/min per IP | Block (429) |
| General API | GET /api/v1/* | 100 req/min per IP | Block (429) |

### Access Model

Model 1 (Security through obscurity):
- Deployed to non-publicized *.pages.dev URL
- Read endpoints are public (no auth required)
- Write endpoints protected by SCRAPER_SECRET
- No user accounts, no OAuth, no Cloudflare Access
```

**2. `docs/staging/pre-deployment-checklist.md`:**
```markdown
# Pre-Deployment Checklist

Run through this checklist before each deployment to production.

## Infrastructure
- [ ] `wrangler whoami` shows correct account
- [ ] `wrangler d1 list` shows `haqita-db`
- [ ] `wrangler r2 bucket list` shows `haqita-images`
- [ ] `wrangler pages project list` shows `haqita`
- [ ] `wrangler pages secret list --project-name haqita` shows `SCRAPER_SECRET`

## Code Quality
- [ ] `cd web && npx tsc --noEmit` exits 0
- [ ] `cd web && npx vitest run` all tests pass
- [ ] `python -m pytest tests/cloudflare/ -v` all tests pass
- [ ] No `any` types in TypeScript code
- [ ] No SQL string interpolation — all queries use `bind()`

## Data
- [ ] `python scripts/publish_html.py` runs successfully
- [ ] `output/html/active_promo.json` exists with data
- [ ] `output/html/promo_catalog.json` exists with data
- [ ] `database/price_history.json` has recent snapshots

## Security
- [ ] SCRAPER_SECRET is set in Cloudflare and .env
- [ ] Security headers middleware is active (verify with `curl -I`)
- [ ] WAF rate limiting rules are configured (if available on plan)

## Deployment
- [ ] `./scripts/deploy_pages.sh` runs successfully
- [ ] `curl https://haqita.pages.dev/` returns 200
- [ ] `curl https://haqita.pages.dev/api/v1/health` returns {"status":"ok"}
- [ ] `curl https://haqita.pages.dev/api/v1/stores` returns store data
- [ ] Browser: UI loads, all tabs work, search/filter/sort functional

## Post-Deployment
- [ ] `python scripts/sync_cloudflare.py --api-url https://haqita.pages.dev/api/v1` succeeds
- [ ] `curl https://haqita.pages.dev/api/v1/products?limit=5` returns 5 products
- [ ] Security headers present in production responses
- [ ] No console errors in browser
```

**References:** docs/staging/publish-html.md (documentation template), plan.md:378-393 (security section), plan.md:471-477 (pre-deployment checklist), Phase 7 Todos 1-3 (security implementations)

**Acceptance criteria:**
- `docs/staging/security-configuration.md` exists with SCRAPER_SECRET, security headers, rate limiting, and access model sections
- `docs/staging/pre-deployment-checklist.md` exists with all 6 checklist sections (Infrastructure, Code Quality, Data, Security, Deployment, Post-Deployment)
- Secret rotation procedure includes 5 numbered steps with exact commands
- **Log message clarity:** Documentation includes exact commands for each verification step
- **Failure handling:** Pre-deployment checklist catches common deployment issues before they reach production
- **Code quality:** Matches existing `docs/staging/*.md` style — ATX headings, pipe tables, fenced code blocks, checkboxes for checklist
- **Unit test coverage:** N/A — documentation

**QA:**
- Happy: Both docs exist with all sections → pass
- Failure: Missing section → add it

**Commit:** Y | docs: add security configuration and pre-deployment checklist

---

### Todo 6: Final verification

**What to do:**

Run the complete end-to-end verification:

1. Verify all tests pass:
   ```bash
   # TypeScript tests
   cd web && npx tsc --noEmit
   cd web && npx vitest run

   # Python tests
   python -m pytest tests/cloudflare/ -v
   ```

2. Start local API and run E2E tests:
   ```bash
   cd web && npx wrangler pages dev --local &
   sleep 5
   python -m pytest tests/cloudflare/test_e2e.py -v
   kill %1
   ```

3. Verify security headers:
   ```bash
   cd web && npx wrangler pages dev --local &
   sleep 5
   curl -I http://localhost:8787/api/v1/health
   kill %1
   ```
   **Expected:** Response includes X-Content-Type-Options, X-Frame-Options, Referrer-Policy.

4. Verify full E2E flow (if production is deployed):
   ```bash
   # Run pipeline
   python scripts/publish_html.py

   # Sync to production
   export SCRAPER_SECRET=<your-secret>
   python scripts/sync_cloudflare.py --api-url https://haqita.pages.dev/api/v1 --verbose

   # Verify production
   curl -s https://haqita.pages.dev/api/v1/health
   curl -s "https://haqita.pages.dev/api/v1/products?limit=5" | python3 -m json.tool
   curl -s https://haqita.pages.dev/api/v1/stores | python3 -m json.tool
   curl -I https://haqita.pages.dev/api/v1/health
   ```

5. Verify pre-deployment checklist:
   - Go through every item in `docs/staging/pre-deployment-checklist.md`
   - All items should pass

6. Verify documentation:
   - `docs/staging/cloudflare-setup.md` (Phase 1)
   - `docs/database/d1-schema.md` (Phase 2)
   - `docs/staging/api-read-endpoints.md` (Phase 3)
   - `docs/staging/api-sync-endpoints.md` (Phase 4)
   - `docs/staging/sync-cloudflare.md` (Phase 5)
   - `docs/staging/deploy-pages.md` (Phase 6)
   - `docs/staging/security-configuration.md` (Phase 7)
   - `docs/staging/pre-deployment-checklist.md` (Phase 7)
   - All 8 docs exist and are accurate

**References:** All previous phases

**Acceptance criteria:**
- All TypeScript and Python tests pass
- E2E tests pass (15+ tests)
- Security headers are present in API responses
- Full E2E flow works: pipeline → sync → API → browser
- Pre-deployment checklist all items pass
- All 8 documentation files exist and are accurate
- **Log message clarity:** All test outputs are clear; E2E flow logs show each step
- **Failure handling:** Any failure → fix in the corresponding phase before declaring complete
- **Documentation:** All docs verified as accurate against actual implementation

**QA:**
- Happy: All verification steps pass → Phase 7 complete → entire migration complete
- Failure: Any step fails → fix the issue in the corresponding phase

**Commit:** Y | test: final verification of complete Cloudflare migration

---

## Final verification wave
- [ ] F1. Plan compliance audit — all Must have items delivered (secret, headers, WAF, E2E test, checklist, docs)
- [ ] F2. Code quality review — `tsc --noEmit` clean, `vitest run` passes, `pytest tests/cloudflare/ -v` passes, no `any` types
- [ ] F3. Real manual QA — E2E test passes, security headers present, sync to production works, browser UI functional
- [ ] F4. Scope fidelity — no user auth, no OAuth, no Cloudflare Access, no CORS, no API logic changes

---

## Commit strategy
- One commit per todo (Todos 2, 3, 4, 5, 6)
- Todo 1 (secret setup) does not produce a commit
- Commit messages: `feat(api):`, `docs:`, `test(cloudflare):`, `test:`

---

## Success criteria
1. `SCRAPER_SECRET` is set as a Cloudflare secret and sync works with it
2. Security headers (X-Content-Type-Options, X-Frame-Options, Referrer-Policy, X-XSS-Protection) are present in all API responses
3. WAF rate limiting rules are configured (or documented as a known limitation)
4. Secret rotation procedure is documented with 5 clear steps
5. `python -m pytest tests/cloudflare/test_e2e.py -v` passes 15+ E2E tests
6. `docs/staging/pre-deployment-checklist.md` covers all deployment verification steps
7. Full E2E flow works: pipeline → sync → API → browser
8. All 8 documentation files exist and are accurate

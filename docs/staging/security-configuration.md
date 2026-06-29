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
   python scripts/sync_cloudflare.py --api-url https://haqita.pages.dev/api/v1
   ```

5. The old secret is immediately invalid — no downtime.

### Security Headers

Headers are served via Cloudflare Pages' `_headers` file at `web/public/_headers`:

| Header | Value | Purpose |
|--------|-------|---------|
| Content-Security-Policy | `default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' fonts.googleapis.com; font-src fonts.gstatic.com; img-src 'self' data: https:; connect-src 'self'; worker-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'none'` | Strict CSP — blocks inline scripts, limits origins for all resources |
| X-Content-Type-Options | nosniff | Prevents MIME type sniffing |
| Referrer-Policy | strict-origin-when-cross-origin | Limits referrer information |

Asset files (`/assets/*`) are served with `Cache-Control: public, max-age=31536000, immutable` for long-term caching.

### Rate Limiting (WAF Rules)

| Rule | Match | Rate | Action |
|------|-------|------|--------|
| Sync endpoint | POST /api/v1/sync/* | 10 req/min per IP | Block (429) |
| General API | GET /api/v1/* | 100 req/min per IP | Block (429) |

**Note:** WAF rate limiting on `*.pages.dev` subdomains may have limitations depending on the Cloudflare plan. If WAF rules are not available on the free tier for Pages, document this as a known limitation. The `SCRAPER_SECRET` still protects the write path.

### Access Model

Model 1 (Security through obscurity):
- Deployed to non-publicized `*.pages.dev` URL
- Read endpoints are public (no auth required)
- Write endpoints protected by SCRAPER_SECRET
- No user accounts, no OAuth, no Cloudflare Access

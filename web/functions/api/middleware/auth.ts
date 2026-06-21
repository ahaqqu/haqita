import { createMiddleware } from 'hono/factory';

// Bearer token auth middleware — protects /api/v1/sync/* routes.
// Validates Authorization: Bearer <token> header against SCRAPER_SECRET binding.
//
// Usage:
//   app.post('/api/v1/sync/*', authMiddleware, ...handler)
//
// The SCRAPER_SECRET is set via `wrangler secret put SCRAPER_SECRET` (Phase 7)
// For local dev, it's set in web/.dev.vars file.

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

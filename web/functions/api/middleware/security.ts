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

import { Hono } from 'hono';
import { handle } from 'hono/cloudflare-pages';

const app = new Hono().basePath('/api');

app.get('/health', (c) => {
  return c.json({ status: 'ok', timestamp: new Date().toISOString() });
});

app.all('*', (c) => {
  return c.json({ error: 'Not found' }, 404);
});

export const onRequest = handle(app);


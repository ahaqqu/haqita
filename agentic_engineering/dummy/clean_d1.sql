-- Reset all pipeline data in Cloudflare D1 for an idempotent dummy run.
-- Run with: wrangler d1 execute <database-name> --file=tests/dummy/clean_d1.sql

DELETE FROM prices;
DELETE FROM promos;
DELETE FROM products;
DELETE FROM stores;

-- Migration 001: Add dummy_data column to all D1 tables.
-- Applied via: wrangler d1 execute haqita-db --file=./web/migrations/001_add_dummy_data.sql

ALTER TABLE stores ADD COLUMN dummy_data INTEGER NOT NULL DEFAULT 0;
ALTER TABLE products ADD COLUMN dummy_data INTEGER NOT NULL DEFAULT 0;
ALTER TABLE prices ADD COLUMN dummy_data INTEGER NOT NULL DEFAULT 0;
ALTER TABLE promos ADD COLUMN dummy_data INTEGER NOT NULL DEFAULT 0;

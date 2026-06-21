import { describe, it, expect } from 'vitest';
import * as schemas from '../functions/api/schemas';

describe('productsQuerySchema', () => {
  it('accepts valid params', () => {
    const result = schemas.productsQuerySchema.parse({ limit: '20', sort: 'name' });
    expect(result.limit).toBe(20);
    expect(result.sort).toBe('name');
  });

  it('rejects limit > 100', () => {
    expect(() => schemas.productsQuerySchema.parse({ limit: '101' })).toThrow();
  });

  it('rejects limit < 1', () => {
    expect(() => schemas.productsQuerySchema.parse({ limit: '0' })).toThrow();
  });

  it('rejects invalid sort', () => {
    expect(() => schemas.productsQuerySchema.parse({ sort: 'invalid' })).toThrow();
  });

  it('defaults limit to 20', () => {
    const result = schemas.productsQuerySchema.parse({});
    expect(result.limit).toBe(20);
  });

  it('defaults sort to name', () => {
    const result = schemas.productsQuerySchema.parse({});
    expect(result.sort).toBe('name');
  });
});

describe('historyQuerySchema', () => {
  it('validates date format', () => {
    const valid = schemas.historyQuerySchema.parse({ from: '2026-06-01' });
    expect(valid.from).toBe('2026-06-01');

    expect(() => schemas.historyQuerySchema.parse({ from: 'invalid' })).toThrow();
  });
});

describe('searchQuerySchema', () => {
  it('requires q', () => {
    expect(() => schemas.searchQuerySchema.parse({})).toThrow();
  });

  it('rejects empty q', () => {
    expect(() => schemas.searchQuerySchema.parse({ q: '' })).toThrow();
  });

  it('limits to 50', () => {
    expect(() => schemas.searchQuerySchema.parse({ q: 'test', limit: '51' })).toThrow();
  });
});

describe('cursor helpers', () => {
  it('decodeCursor returns 0 for invalid cursor', () => {
    expect(schemas.decodeCursor('invalid')).toBe(0);
  });

  it('decodeCursor decodes valid cursor', () => {
    const cursor = schemas.encodeCursor(20);
    expect(schemas.decodeCursor(cursor)).toBe(20);
  });

  it('encodeCursor produces base64 string', () => {
    const cursor = schemas.encodeCursor(0);
    expect(cursor).toMatch(/^[A-Za-z0-9+/]*={0,2}$/);
    expect(schemas.decodeCursor(cursor)).toBe(0);
  });
});

describe('syncBatchSchema', () => {
  const validBody = {
    source: 'test-source',
    sync_run_id: 'test-run-1',
    stores: [{ name: 'Superindo', color: '#ff0000' }],
    products: [
      {
        key: 'superindo-minyak-goreng-1l',
        name: 'Minyak Goreng 1L',
        brand: 'Bimoli',
        category: 'Minyak',
        unit: '1 liter',
        unit_type: 'volume',
        unit_value_g: 1000,
      },
    ],
    prices: [
      {
        product_key: 'superindo-minyak-goreng-1l',
        store: 'Superindo',
        price: 15000,
        effective_unit_price: 15,
        bundle_size: 1,
        promo: null,
        promo_type: null,
        valid_from: '2026-06-01',
        valid_until: '2026-06-07',
        image_path: 'images/1.jpg',
        scrape_time: '2026-06-01T00:00:00Z',
        date: '2026-06-01',
        match_method: 'exact',
        match_confidence: 1,
        standardized_promo: null,
      },
    ],
    promos: [
      {
        key: 'superindo-promo-1',
        display: 'Buy 1 Get 1',
        type: 'percentage',
        discount_pct: 50,
        max_qty: 2,
        product_count: 10,
        stores: { Superindo: 1 },
        example_products: ['superindo-minyak-goreng-1l'],
      },
    ],
  };

  it('accepts valid body', () => {
    const result = schemas.syncBatchSchema.parse(validBody);
    expect(result.stores).toHaveLength(1);
    expect(result.products).toHaveLength(1);
    expect(result.prices).toHaveLength(1);
    expect(result.promos).toHaveLength(1);
  });

  it('rejects missing source', () => {
    const bodyWithoutSource = { ...validBody, source: undefined };
    expect(() => schemas.syncBatchSchema.parse(bodyWithoutSource)).toThrow();
  });

  it('rejects missing sync_run_id', () => {
    const bodyWithoutRunId = { ...validBody, sync_run_id: undefined };
    expect(() => schemas.syncBatchSchema.parse(bodyWithoutRunId)).toThrow();
  });

  it('accepts empty arrays', () => {
    const result = schemas.syncBatchSchema.parse({
      source: 'test-source',
      sync_run_id: 'test-run-2',
      stores: [],
      products: [],
      prices: [],
      promos: [],
    });
    expect(result.stores).toEqual([]);
    expect(result.products).toEqual([]);
    expect(result.prices).toEqual([]);
    expect(result.promos).toEqual([]);
  });
});

describe('syncImagesSchema', () => {
  it('accepts valid manifest', () => {
    const result = schemas.syncImagesSchema.parse({
      images: [{ local_path: 'images/1.jpg', r2_key: 'images/1.jpg', r2_url: 'https://r2/1.jpg' }],
    });
    expect(result.images).toHaveLength(1);
    expect(result.images[0].local_path).toBe('images/1.jpg');
  });

  it('rejects empty images', () => {
    expect(() => schemas.syncImagesSchema.parse({ images: [] })).toThrow();
  });
});

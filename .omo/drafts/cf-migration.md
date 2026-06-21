---
slug: cf-migration
status: approved
intent: clear
pending-action: create 7 phase files in docs/plan/phases/ + update plan.md
approach: Break original plan.md Phase 1 into 7 implementation-ready phase files under docs/plan/phases/, each with detailed todos, acceptance criteria (log messages, documentation, failure handling, code quality, unit test coverage), and agent-executable QA. Keep plan.md as architecture overview with links to phase files.
---

# Draft: cf-migration

## Components (topology ledger)
| id | outcome | status | evidence path |
|----|---------|--------|---------------|
| P1 | Cloudflare infrastructure setup — Wrangler CLI, D1, R2, Pages, web/ scaffold | active | plan.md:422, wrangler CLI docs |
| P2 | D1 schema & seed data — schema.sql + Python seed script from database/*.json | active | plan.md:234-306, database/price_history.json:schema v1.2 |
| P3 | Hono API read endpoints — all GET /api/v1/* endpoints with Zod validation | active | plan.md:108-143, index.html:loadData() line 1182 |
| P4 | Hono API sync endpoints — POST /sync/batch + /sync/images with auth + idempotency | active | plan.md:145-231, scripts/common/http_client.py:retry_call |
| P5 | Python Stage 5 sync script — sync_cloudflare.py + R2 upload + haqita.sh/bat wiring | active | plan.md:85-105, scripts/publish_html.py:template pattern, scripts/orchestrator.py:subprocess pattern |
| P6 | Static HTML deployment & API integration — web/public/ + index.html API consumption | active | plan.md:344-354, index.html:tryLoadWithFallback line 712 |
| P7 | Security hardening & E2E verification — rate limiting, headers, secret rotation, E2E test | active | plan.md:378-394, plan.md:471-477 |

## Open assumptions (announced defaults)
| assumption | adopted default | rationale | reversible? |
|------------|----------------|-----------|-------------|
| Phase file location | docs/plan/phases/ | User approved; alongside existing docs/plan/astro_scraper_plan.md | Yes |
| plan.md fate | Keep as architecture overview, add links to phase files | User approved | Yes |
| Phase 2-4 detail | Not detailed — only Phase 1 is broken up | User approved; Phases 2-4 are future work | Yes |
| Number of phases | 7 phases from original Phase 1 | User said "setup cloudflare should be separate phase"; each phase has a clear verification gate | Yes |
| Hono deployment | Pages Functions (web/functions/api/[[route]].ts) | plan.md:517-520 already decided; same origin, no CORS | Yes — extractable to standalone Worker later |
| Image upload | Option A — R2 upload from laptop via boto3 S3-compatible API | plan.md:357-375 already decided | Yes |
| Auth model | Model 1 — obscure URL + SCRAPER_SECRET | plan.md:630-649 already decided | Yes |
| Python sync script name | scripts/sync_cloudflare.py | plan.md:87 already specified | Yes |
| Package manager | npm | plan.md:486 lists npm/pnpm; npm is the default | Yes |
| TypeScript config | strict mode, Zod for validation | plan.md:389 specifies Zod; strict is best practice | Yes |

## Findings (cited - path:lines)
1. Python pipeline stages communicate via JSON status files at output/stage_results/<stage>_status.json — orchestrator.py:61-71
2. Each stage script uses argparse with --dry-run flag, prints to stdout, returns 0 on success — publish_html.py:38-42
3. haqita.sh menu is a case statement at line 204-235; new items shift existing numbers — haqita.sh:204
4. haqita.bat uses goto labels; same numbering shift pattern — haqita.bat:18-39
5. index.html loads data via tryLoadWithFallback("output/html", "data/sample/html", filename) at line 1189-1190
6. retryFetch() at line 705 provides 3-attempt exponential backoff — index.html:705-710
7. No existing API consumption in index.html — all data from static JSON files
8. Builder functions (buildMatchedCard, buildSingleCard) consume normalized {key, name, stores[]} — index.html:754-763
9. price_history.json: 599 snapshots, 18 fields, schema v1.2 — database/price_history.json
10. product_catalog.json: 589 entries, 12 fields, schema v1.1 — database/product_catalog.json
11. active_promo.json: products[] + singles[] + promo_catalog[] + stats{} + display_hints{} — output/html/active_promo.json
12. promo_catalog.json: 50 entries with key, display, type, product_count, stores, example_products — output/html/promo_catalog.json
13. Tests: pytest, class-based Test* with test_* methods, unittest.mock.patch, tmp_path/capsys/monkeypatch — tests/matching/test_consolidate.py
14. Config: config.yaml with top-level sections, loaded via scripts/config.py load_config() — config.yaml
15. .env: loaded via python-dotenv, only GEMINI_API_KEY currently — .env.example
16. requirements.txt: >= version pinning, grouped by purpose with comments — requirements.txt
17. Docs: docs/staging/*.md with overview table, how-it-works, schema, config, usage pattern — docs/staging/publish-html.md
18. retry_call() in scripts/common/http_client.py provides retry with exponential backoff — scripts/common/http_client.py:62-116
19. atomic_write_json() in scripts/matching/consolidation.py for safe file writes — scripts/matching/consolidation.py
20. Database JSON files are in .gitignore — .gitignore:19-24

## Decisions (with rationale)
| decision | choice | rationale |
|----------|--------|-----------|
| Phase file location | docs/plan/phases/ | User approved; visible in docs tree |
| plan.md fate | Keep as architecture overview | User approved; add links to phase files |
| Phase count | 7 phases from original Phase 1 | Each has a clear verification gate; Cloudflare setup is separate (user's explicit request) |
| Acceptance criteria | Include log messages, documentation, failure handling, code quality, unit test coverage | User's explicit request |
| Implementation target | Lightweight LLM | Plan must be decision-complete with zero judgment calls |

## Scope IN
1. Create 7 detailed phase files in docs/plan/phases/
2. Each phase file follows ulw-plan template (TL;DR, Scope, Verification strategy, Execution strategy, Todos, Final verification wave, Commit strategy, Success criteria)
3. Each todo has: file references, step-by-step instructions, acceptance criteria (log/doc/failure/quality/tests), QA (happy+failure), commit message
4. Update plan.md with "Implementation Phases" section linking to phase files
5. Update .omo/plans/cf-migration.md with master TL;DR

## Scope OUT (Must NOT have)
1. No implementation of any phase — planning only
2. No changes to product code
3. No detailed phase files for original Phases 2-4 (future work)
4. No changes to the architecture decisions in plan.md (they are already resolved)

## Open questions
<!-- None — all resolved via exploration + user decisions -->

## Approval gate
status: approved
<!-- Approved by user on 2026-06-21. User selected: docs/plan/phases/ location, keep plan.md as overview, just break up Phase 1. -->

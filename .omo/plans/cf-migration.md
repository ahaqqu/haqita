# cf-migration - Work Plan

## TL;DR (For humans)

**What you'll get:** The existing Jakarta grocery price tracker migrated to Cloudflare in 7 implementation-ready phases. Each phase is a separate, self-contained plan file with detailed step-by-step instructions, precise acceptance criteria (including log messages, documentation, failure handling, code quality, and unit test coverage), and agent-executable QA scenarios. A lightweight LLM can implement each phase independently without making judgment calls.

**Why this approach:** The original plan.md is an excellent architecture document but its Phase 1 is a 9-item checkbox list with zero implementation detail. Breaking it into 7 phases — each with its own verification gate — lets a lightweight LLM implement incrementally, verifying each step before moving on. Cloudflare infrastructure setup is its own phase (per user request) with clear steps to verify the setup is correct.

**What it will NOT do:** Implement React migration (original Phase 3, deferred), implement dynamic features (original Phase 2, deferred), implement scale/public launch (original Phase 4, deferred), or add user authentication (out of scope per plan.md:394).

**Effort:** XL — 7 phases, ~25-35 hours total across all phases
**Risk:** Medium — SQL query correctness and idempotency are critical; R2 credentials must be correct
**Decisions to sanity-check:** All architecture decisions are already resolved in plan.md. Phase file location (docs/plan/phases/) and plan.md fate (keep as overview) are user-approved.

Your next move: Review the 7 phase files below. When ready to implement, copy them to `docs/plan/phases/` and start with Phase 1. Each phase links to the next via its dependency matrix.

---

> TL;DR (machine): XL effort, 7 phases, breaks plan.md Phase 1 into implementation-ready files with acceptance criteria including log/doc/failure/quality/tests.

## Scope

### Must have
1. 7 detailed phase plan files under `.omo/plans/` (to be copied to `docs/plan/phases/` when starting work)
2. Each phase file contains: TL;DR, Scope (Must have / Must NOT have), Verification strategy, Execution strategy (dependency matrix), detailed Todos (with file references, step-by-step instructions, acceptance criteria including log messages / documentation / failure handling / code quality / unit test coverage, QA scenarios, commit messages), Final verification wave, Commit strategy, Success criteria
3. `plan.md` updated with an "Implementation Phases" section linking to the phase files
4. Original plan.md Phases 2-4 retained as future work

### Must NOT have
1. No implementation of any phase — planning only
2. No changes to the architecture decisions in plan.md (they are already resolved)
3. No changes to existing product code (scripts/, index.html, etc.)
4. No detailed phase files for original Phases 2-4 (deferred to when they're ready to implement)

## Verification strategy
> Zero human intervention - all verification is agent-executed.
- Test decision: each phase has its own verification strategy (TDD, tests-after, verification-by-command)
- Evidence: each phase's todos specify exact commands and expected outputs
- Phase completion: each phase ends with a "Final verification" todo that runs a checklist

## Execution strategy

### Phase dependency chain

Phases must be executed in order — each phase depends on the previous one's deliverables.

| Phase | Title | Depends on | Estimated effort |
|-------|-------|-----------|-----------------|
| 1 | [Cloudflare Infrastructure Setup](cf-phase-1-infrastructure.md) | — | ~1-2 hours |
| 2 | [D1 Schema & Seed Data](cf-phase-2-schema-seed.md) | Phase 1 | ~3-4 hours |
| 3 | [Hono API — Public Read Endpoints](cf-phase-3-api-read.md) | Phase 2 | ~6-8 hours |
| 4 | [Hono API — Protected Sync Endpoints](cf-phase-4-api-sync.md) | Phase 3 | ~4-5 hours |
| 5 | [Python Stage 5 Sync Script](cf-phase-5-python-sync.md) | Phase 4 | ~6-8 hours |
| 6 | [Static HTML Deployment & API Integration](cf-phase-6-deploy-ui.md) | Phase 5 | ~3-4 hours |
| 7 | [Security Hardening & E2E Verification](cf-phase-7-security-e2e.md) | Phase 6 | ~3-4 hours |

### Dependency matrix
| Phase | Depends on | Blocks | Can parallelize with |
|-------|-----------|--------|---------------------|
| 1. Infrastructure | — | 2 | — |
| 2. Schema & Seed | 1 | 3 | — |
| 3. API Read Endpoints | 2 | 4 | — |
| 4. API Sync Endpoints | 3 | 5 | — |
| 5. Python Sync Script | 4 | 6 | — |
| 6. Deploy & UI Integration | 5 | 7 | — |
| 7. Security & E2E | 6 | — | — |

## Todos

> Implementation + Test = ONE todo. Never separate.

- [ ] 0. **Copy phase files to docs/plan/phases/ and update plan.md**
  What to do: Copy the 7 phase files from `.omo/plans/cf-phase-*.md` to `docs/plan/phases/phase-*-*.md`. Update `plan.md` by replacing the "Development Phases" section (lines 419-449) with an "Implementation Phases" section that links to the 7 phase files and retains original Phases 2-4 as "Future Phases."
  Must NOT do: Do not change any architecture decisions in plan.md. Do not change any content in the phase files during the copy.
  References: .omo/plans/cf-phase-1-infrastructure.md through cf-phase-7-security-e2e.md, plan.md:419-449 (current Development Phases section)
  Acceptance criteria: `docs/plan/phases/` contains 7 files, plan.md "Development Phases" section replaced with "Implementation Phases" linking to all 7 files
  QA: happy — `ls docs/plan/phases/` shows 7 files, plan.md links work → pass
  Commit: Y | docs: add detailed implementation phase files and update plan.md

- [ ] 1. **Execute Phase 1: Cloudflare Infrastructure Setup** — see [cf-phase-1-infrastructure.md](cf-phase-1-infrastructure.md)
  What to do: Follow all 7 todos in the phase file. Install Wrangler, create D1/R2/Pages resources, scaffold web/ project, write docs, verify.
  References: .omo/plans/cf-phase-1-infrastructure.md (full file)
  Acceptance criteria: All 7 success criteria in the phase file pass
  QA: see phase file Todo 7 for the full verification checklist
  Commit: Y | per phase file commit strategy

- [ ] 2. **Execute Phase 2: D1 Schema & Seed Data** — see [cf-phase-2-schema-seed.md](cf-phase-2-schema-seed.md)
  What to do: Follow all 6 todos in the phase file. Create schema.sql, seed script, apply to D1, write tests, write docs, verify.
  References: .omo/plans/cf-phase-2-schema-seed.md (full file)
  Acceptance criteria: All 6 success criteria in the phase file pass
  QA: see phase file Todo 6 for the full verification checklist
  Commit: Y | per phase file commit strategy

- [ ] 3. **Execute Phase 3: Hono API — Public Read Endpoints** — see [cf-phase-3-api-read.md](cf-phase-3-api-read.md)
  What to do: Follow all 10 todos in the phase file. Set up Hono structure, implement all 10 GET endpoints, write tests, write docs, verify.
  References: .omo/plans/cf-phase-3-api-read.md (full file)
  Acceptance criteria: All 10 success criteria in the phase file pass
  QA: see phase file Todo 10 for the full verification checklist
  Commit: Y | per phase file commit strategy

- [ ] 4. **Execute Phase 4: Hono API — Protected Sync Endpoints** — see [cf-phase-4-api-sync.md](cf-phase-4-api-sync.md)
  What to do: Follow all 7 todos in the phase file. Implement auth middleware, Zod schemas, sync/batch and sync/images endpoints, write tests, write docs, verify.
  References: .omo/plans/cf-phase-4-api-sync.md (full file)
  Acceptance criteria: All 9 success criteria in the phase file pass
  QA: see phase file Todo 7 for the full verification checklist
  Commit: Y | per phase file commit strategy

- [ ] 5. **Execute Phase 5: Python Stage 5 Sync Script** — see [cf-phase-5-python-sync.md](cf-phase-5-python-sync.md)
  What to do: Follow all 9 todos in the phase file. Create sync_cloudflare.py, implement batch sync, R2 upload, state tracking, wire into menus, write tests, update config, write docs, verify.
  References: .omo/plans/cf-phase-5-python-sync.md (full file)
  Acceptance criteria: All 9 success criteria in the phase file pass
  QA: see phase file Todo 9 for the full verification checklist
  Commit: Y | per phase file commit strategy

- [ ] 6. **Execute Phase 6: Static HTML Deployment & API Integration** — see [cf-phase-6-deploy-ui.md](cf-phase-6-deploy-ui.md)
  What to do: Follow all 5 todos in the phase file. Create deploy script, update index.html for API consumption, deploy to Pages, write docs, verify.
  References: .omo/plans/cf-phase-6-deploy-ui.md (full file)
  Acceptance criteria: All 7 success criteria in the phase file pass
  QA: see phase file Todo 5 for the full verification checklist
  Commit: Y | per phase file commit strategy

- [ ] 7. **Execute Phase 7: Security Hardening & E2E Verification** — see [cf-phase-7-security-e2e.md](cf-phase-7-security-e2e.md)
  What to do: Follow all 6 todos in the phase file. Set SCRAPER_SECRET, add security headers, configure WAF, write E2E test, write docs, verify.
  References: .omo/plans/cf-phase-7-security-e2e.md (full file)
  Acceptance criteria: All 8 success criteria in the phase file pass
  QA: see phase file Todo 6 for the full verification checklist
  Commit: Y | per phase file commit strategy

## Final verification wave
> Runs in parallel after ALL todos. ALL must APPROVE.
- [ ] F1. Plan compliance audit — all 7 phases executed, all phase success criteria met
- [ ] F2. Code quality review — `tsc --noEmit` clean, `vitest run` passes, `pytest tests/cloudflare/ -v` passes, no `any` types, all SQL parameterized
- [ ] F3. Real manual QA — E2E test passes, deployed site works, API functional, security headers present
- [ ] F4. Scope fidelity — no React rewrite, no user auth, no changes to Stages 1-4, plan.md architecture decisions unchanged

## Commit strategy
- Todo 0 (copy files + update plan.md): `docs: add detailed implementation phase files and update plan.md`
- Todos 1-7: follow each phase file's commit strategy (conventional commits: `feat:`, `test:`, `docs:`, `chore:`)
- One commit per todo within each phase (40+ commits total across all phases)

## Success criteria
1. All 7 phase files exist in `docs/plan/phases/` with detailed implementation instructions
2. `plan.md` has an "Implementation Phases" section linking to all 7 phase files
3. Each phase file has precise acceptance criteria including: clear log messages, documentation requirements, failure handling, code quality requirements, and unit test coverage requirements
4. Each phase has a clear verification gate with exact commands to verify the setup is correct
5. Cloudflare infrastructure setup is its own phase (Phase 1) with step-by-step verification
6. The total test count across all phases: 24+ (seed script) + 31+ (API read) + 28+ (API sync) + 28+ (Python sync) + 15+ (E2E) = 126+ tests minimum
7. The total documentation count: 8 new docs (cloudflare-setup, d1-schema, api-read-endpoints, api-sync-endpoints, sync-cloudflare, deploy-pages, security-configuration, pre-deployment-checklist)

---

## Phase file inventory

| File | Phase | Todos | Tests | Documentation |
|------|-------|-------|-------|---------------|
| `.omo/plans/cf-phase-1-infrastructure.md` | Cloudflare Infrastructure Setup | 7 | 0 (curl verification) | docs/staging/cloudflare-setup.md |
| `.omo/plans/cf-phase-2-schema-seed.md` | D1 Schema & Seed Data | 6 | 24+ | docs/database/d1-schema.md |
| `.omo/plans/cf-phase-3-api-read.md` | Hono API Read Endpoints | 10 | 31+ | docs/staging/api-read-endpoints.md |
| `.omo/plans/cf-phase-4-api-sync.md` | Hono API Sync Endpoints | 7 | 28+ | docs/staging/api-sync-endpoints.md |
| `.omo/plans/cf-phase-5-python-sync.md` | Python Stage 5 Sync Script | 9 | 28+ | docs/staging/sync-cloudflare.md |
| `.omo/plans/cf-phase-6-deploy-ui.md` | Deploy & UI Integration | 5 | 0 (manual) | docs/staging/deploy-pages.md |
| `.omo/plans/cf-phase-7-security-e2e.md` | Security & E2E | 6 | 15+ | docs/staging/security-configuration.md + pre-deployment-checklist.md |
| **Total** | | **50 todos** | **126+ tests** | **8 docs** |

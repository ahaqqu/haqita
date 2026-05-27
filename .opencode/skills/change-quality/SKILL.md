---
name: change-quality
description: Enforce unit tests, logging, and documentation for every code change. Use when implementing features, fixing bugs, refactoring, or modifying any production code.
---

# Change Quality Checklist

Every code change MUST consider these three dimensions before marking a task complete.

## 1. Unit Tests

**Always ask:** "Do existing tests need updating? Do new tests need adding?"

- If changing function behavior → update existing tests for that function
- If adding new function/branch/logic → add tests covering it
- If changing error handling → test both the happy path and error path
- If touching data serialization/deserialization → test round-trip
- Run the full test suite after changes: `python -m pytest tests/ -x -q`
- Never leave tests in a broken state

## 2. Logging / User-Facing Output

**Always ask:** "Will the user understand what happened from the output alone?"

- Error paths must log what failed and why
- Skip/break conditions must log how many items were affected
- Use provider/component names from config, not hardcoded strings
- Log before state-saving so failures are visible even if save crashes
- Print messages should be actionable (tell user what to do next)

## 3. Documentation

**Always ask:** "Does any doc reference the schema, behavior, or output I changed?"

- Check `docs/` for files that reference changed fields, schemas, or flows
- Update schema examples when field types/shapes change
- Update "How It Works" sections when behavior/logic changes
- Update output examples when JSON structure changes
- If adding a new field to output → document it in the relevant schema section
- If changing a type (e.g., `string` → `list`) → update type column in schema tables

## Workflow

After implementing a change:

1. **Tests** — Run `python -m pytest tests/ -x -q`. Fix failures before proceeding.
2. **Docs** — Search `docs/` for references to changed fields/functions. Update if found.
3. **Output** — If behavior changed, verify log/output messages are clear and correct.

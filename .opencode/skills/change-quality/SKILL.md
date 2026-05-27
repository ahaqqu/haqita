---
name: change-quality
description: Enforce unit tests, logging, and documentation for every code change. Use when implementing features, fixing bugs, refactoring, or modifying any production code.
---

# Change Quality Checklist

Every code change MUST consider these dimensions before marking a task complete.

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

## 4. Branch & Pull Request

**Always ask:** "Is this a feature or bug fix that needs a PR?"

For any feature or bug fix (not trivial typo fixes):

1. **Create a branch** — Use descriptive name: `feature/<short-description>` or `fix/<short-description>`
2. **Commit changes** — Use conventional commit format: `feat: <description>` or `fix: <description>`
3. **Push branch** — `git push -u origin <branch-name>`
4. **Create PR** — Use `gh pr create` with:
   - **Title**: Compact, clear, imperative mood (e.g., "feat: add promo array support" not "Added promo array support")
   - **Body**: Detailed description including:
     - What changed and why
     - List of files modified
     - Testing performed
     - Any breaking changes or migration notes

### PR Title Rules
- Use conventional commit prefix: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`
- Keep under 72 characters
- Use imperative mood ("add" not "added", "fix" not "fixed")
- Be specific but concise

### PR Description Template
```markdown
## Changes
- Bullet list of what changed

## Files Changed
- `path/to/file1` - Brief description
- `path/to/file2` - Brief description

## Testing
- Test results or testing performed

## Notes
- Any additional context, breaking changes, or migration steps
```

## Workflow

After implementing a change:

1. **Tests** — Run `python -m pytest tests/ -x -q`. Fix failures before proceeding.
2. **Docs** — Search `docs/` for references to changed fields/functions. Update if found.
3. **Output** — If behavior changed, verify log/output messages are clear and correct.
4. **Branch & PR** — For features/bug fixes: create branch, commit, push, and create PR.

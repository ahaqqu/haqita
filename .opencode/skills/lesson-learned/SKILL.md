---
name: lesson-learned
description: Capture and persist lessons from failures. Use when any tool call, command, or operation fails unexpectedly. Ensures mistakes are documented and not repeated.
---

# Lesson Learned

When something fails during processing, follow this protocol:

## 1. Acknowledge Failure Immediately

**Always tell the user:**
- What failed (exact command/tool/operation)
- Why it failed (error message, root cause)
- What was attempted (all approaches tried)
- What actually worked (the fix)

**Format:**
```
[FAILURE] <what failed>
- Cause: <root cause>
- Attempted: <what didn't work>
- Fix: <what worked>
```

## 2. Write Lesson to File

After resolving the failure, save the lesson to:

**File:** `.opencode/lessons/YYYY-MM-DD_<topic>.md`

**Template:**
```markdown
# Lesson: <topic>

**Date:** YYYY-MM-DD
**Context:** <what was being attempted>

## Failure
<what failed and error message>

## Root Cause
<why it failed>

## Attempted Solutions
1. <first attempt> - didn't work because <reason>
2. <second attempt> - didn't work because <reason>

## Working Solution
<what actually worked>

## Key Takeaway
<one-line summary for future reference>
```

## 3. Check Lessons Before Starting Work

At the start of any complex task:
1. Read `.opencode/lessons/*.md` files
2. Check if any lessons apply to current work
3. Apply known solutions proactively

## 4. Lesson Categories

Organize lessons by category:
- `windows-shell.md` - Windows cmd.exe quirks, escaping issues
- `git-operations.md` - Git command failures and fixes
- `github-cli.md` - gh CLI issues and workarounds
- `python-testing.md` - pytest, import issues, path problems
- `file-operations.md` - File read/write failures
- `api-integration.md` - External API failures

## Workflow

When a failure occurs:

1. **Stop** — Don't silently retry or ignore
2. **Explain** — Tell user what happened and why
3. **Fix** — Resolve the issue
4. **Document** — Write lesson to `.opencode/lessons/`
5. **Continue** — Resume original task

## Example

```
[FAILURE] gh pr edit --body "multi-line text"
- Cause: Windows cmd.exe mangles special characters in inline strings
- Attempted: Direct --body flag with escaped quotes
- Fix: Write to file first, use --body-file flag

Lesson saved to .opencode/lessons/2026-05-27_github-cli-body.md
```

## Anti-Patterns

**Don't:**
- Silently retry without telling user
- Hide error details
- Skip documentation for "obvious" fixes
- Assume failure won't happen again

**Do:**
- Be explicit about what went wrong
- Save lessons even for small fixes
- Reference past lessons when relevant
- Update existing lessons with new findings

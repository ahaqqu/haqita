# Lesson: GitHub CLI PR Body Update on Windows

**Date:** 2026-05-27
**Context:** Updating PR #22 description with multi-line content including backticks and special characters

## Failure
`gh pr edit 22 --body "multi-line text"` appeared to succeed (returned PR URL) but body was truncated to just "## Changes"

## Root Cause
Windows cmd.exe mangles special characters (newlines, backticks, quotes) in inline string arguments. The shell interprets/escapes characters before passing to gh CLI, resulting in truncated content.

## Attempted Solutions
1. Direct `--body "..."` with escaped quotes - didn't work, body truncated
2. HEREDOC syntax `<< 'EOF'` - doesn't work in Windows cmd.exe (Unix-only)

## Working Solution
Write content to a temporary file first, then use `--body-file` flag:
```cmd
echo content > pr_body.md
gh pr edit 22 --body-file pr_body.md
del pr_body.md
```

## Key Takeaway
On Windows, always use `--body-file` for multi-line PR descriptions instead of inline `--body` flag.

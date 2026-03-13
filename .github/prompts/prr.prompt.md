---
agent: agent
description: Stage, commit, and push new changes onto an already-open PR branch.
---

Follow these steps exactly. Do not skip any step.

1. **Check status** — run `git status` and `git branch --show-current`. Confirm there is an open PR for the current branch with `gh pr view --json number,title,headRefName`. If no open PR exists, stop and tell the user to use `/pr` instead.

2. **Stage files** — run `git add` for all modified or new files relevant to the current change. Do not stage unrelated files. Do not stage `.env*`, secrets, or credentials.

3. **Commit** — write a concise commit message with `feat:`, `fix:`, or `chore:` prefix describing what is new. Run `git commit -m "<message>"`.

4. **Push** — run `git push`.

5. **Confirm** — print the PR URL from `gh pr view --json url --jq .url` so the user can see the updated PR.

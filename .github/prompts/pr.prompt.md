---
agent: agent
description: Ensure uncommitted changes are on a feature branch, then commit, push, and open a PR into main.
---

Follow these steps exactly. Do not skip any step.

1. **Check status** — run `git status` and `git branch --show-current` to understand the current state.

2. **Branch safety** — if the current branch is `main` (or any protected branch):
   * Infer a descriptive branch name from the staged/modified files and recent context. Use the naming convention from the PR instructions: `feat/<topic>`, `fix/<topic>`, or `chore/<topic>`, where `<topic>` is lowercase letters, numbers, and hyphens only.
   * Run `git checkout -b <branch-name>`.

3. **Stage files** — run `git add` for all modified or new files that are relevant to the current change. Do not stage unrelated files. Do not stage `.env*`, secrets, or credentials.

4. **Commit** — write a concise commit message following the convention: `feat:`, `fix:`, or `chore:` prefix. Run `git commit -m "<message>"`.

5. **Push** — run `git push -u origin <branch-name>`.

6. **Write the PR body** — use the `create_file` tool to write the PR description to `/tmp/pr-body.txt`. Follow the PR description structure from the PR instructions: Summary, Changes, Motivation, Security considerations, Testing, Breaking changes. Never use shell heredocs or echo to write this file.

7. **Open the PR** — run `gh pr create --title "<title>" --body-file /tmp/pr-body.txt --base main`.

8. **Clean up** — run `rm /tmp/pr-body.txt`.

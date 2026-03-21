---
applyTo: "**"
---

# Pull Request Instructions

## Branch rules

- Never commit directly to `main` — all changes go on a feature branch
- Branch names must be descriptive: `feat/<topic>`, `fix/<topic>`, `chore/<topic>`
- `<topic>` uses only lowercase letters, numbers, and hyphens — never a username, org name, or repo name prefix
- Open a PR to merge into `main`

## Undoing mistakes — avoid destructive operations

`git reset --hard` rewrites history and discards uncommitted work permanently. In a shared project it can discard in-progress commits others depend on. Prefer reversible alternatives:

| Situation | Safe alternative to `reset --hard` |
| :--- | :--- |
| Undo staged changes before committing | `git restore --staged <file>` |
| Discard uncommitted changes to a file | `git restore <file>` |
| Undo the last commit but keep the changes staged | `git reset --soft HEAD~1` — only if the commit has not been pushed |
| Undo the last commit and unstage the changes | `git reset HEAD~1` (mixed — default) — only if the commit has not been pushed |
| Revert a commit that has already been pushed | `git revert <sha>` — creates a new commit, does not rewrite history |
| Update your branch with the latest `main` without discarding local work | `git fetch origin && git merge origin/main` |
| Stash work in progress before switching context | `git stash push -m "description"` / `git stash pop` |

Only use `git reset --hard` when you are certain local changes are safe to discard and the branch has not been pushed. Never use it on `main` or on a branch with an open PR.

## PR title format

Use the same convention as commit messages:

```
feat: short description of what was added
fix: short description of what was corrected
chore: tooling, infra, or non-functional changes
```

## PR description structure

### For simple changes (single-file edits, small fixes)

A short paragraph is sufficient:

- What changed and why
- Any issue it closes (`Closes #N`)

### For larger changes, use this template

```
## Summary
One or two sentences describing the overall change.

## Changes
- Bullet list of specific files/components modified and what changed in each

## Motivation
Why this change is needed — reference the open issue if one exists (`Closes #N` or `Related to #N`).

## Security considerations
- Note any changes to auth, RBAC, JWT handling, or device token logic
- Note any changes to how Stripe, KMS, S3 waivers, or Secrets Manager are used
- Note if new IAM permissions were added and why least-privilege is maintained
- Note any new Lambda endpoints and whether they are protected by the Cognito Authorizer

## Testing
- Describe how the change was verified (local dev, manual API call, unit test, etc.)
- Note any new tests added
- If DB schema changed, confirm migration is idempotent and RLS policies are intact

## Breaking changes
- List any changes to API contracts, DB schema, environment variables, or Cognito app client config that affect running deployments
- If none: "None"
```

## Referencing issues

- Always link related issues: `Closes #N` (auto-closes on merge) or `Related to #N`
- If the PR partially addresses an issue, say so explicitly
- When referencing Open Design Questions, write **ODQ N** (no `#`) — bare `#N` is auto-linked by GitHub to the issue or PR with that number, which is never the intent

## PR size

Keep PRs focused and reviewable:

- If a change touches more than 3 distinct layers (e.g. migrations + Lambda handlers + IAM + frontend) or exceeds ~500 lines, split it by layer — one PR per layer
- The test for "too large": if a reviewer would need to context-switch between unrelated concerns to evaluate the PR, it should be split
- Prefer multiple small PRs over one large one — each gets more thorough review and is easier to revert if something goes wrong
- **One new Lambda handler per PR.** Do not bundle multiple new handlers into a single PR even if they belong to the same feature area. Example: adding `checkin`, `checkout`, and `waiver` handlers → three handler PRs, not one. Any schema, infra, docs (including `docs/design.md` Section 7 route entries), or test changes required for that handler should either be (a) kept minimal and included in the same PR as directly coupled work, or (b) split into separate, linked PRs by layer if they grow large — while still keeping exactly one new handler per PR.

## Review workflow

After opening a PR, run the review workflow to process Copilot reviewer comments:

> Run `.github/prompts/review.prompt.md` on PR #N

This workflow fetches all inline and PR-level comments, classifies them (Valid / Invalid / Speculative), applies fixes, commits, replies, and resolves threads. Run it whenever `copilot-pull-request-reviewer` has posted comments.

## QA — invoke the qa agent after handler PRs

After any PR that adds or modifies a Lambda handler in `functions/`, invoke the qa agent:

> "Write tests for `functions/<path>/handler.py`"

Do not defer test writing to a later session. Tests must exist before the handler is considered production-ready.

## Security review before opening

Before opening any PR that touches `functions/**/*.py`, `db/**/*.sql`, or `infra/**/*.yaml`, invoke the security agent on the changed files:

> "Security review [list of changed files]"

Research and fix any **High** or **Critical** findings before opening the PR. **Medium** and **Low** findings may be noted in the PR description and addressed in a follow-up. This prevents a second review round for issues the security agent would have caught before the PR was opened.

## Test gate before opening

Before opening any PR that touches `functions/**/*.py` or `tests/**/*.py`, run the full pytest suite locally and verify it passes:

```bash
pytest tests/ --tb=short -q
```

**Rules:**
- If any test fails, fix it before opening the PR. Do not open a PR with a known failing test.
- Paste the final summary line (e.g., `80 passed in 0.17s`) into the PR description under **Testing**.
- If the PR adds or modifies a handler, also confirm the corresponding `tests/unit/test_<handler>.py` file exists and covers the changed behavior — add or update tests before opening.
- If the PR touches no handler or test files (e.g., docs-only, infra-only, schema-only), running pytest is not required. Omit the test summary from the PR description rather than filling in "N/A".

## cfn-lint gate before opening

Before opening any PR that touches `infra/**/*.yaml` or `infra/**/*.json`, run cfn-lint on all changed CloudFormation templates and verify there are no errors:

```bash
cfn-lint infra/**/*.yaml
```

**Rules:**
- If any error is reported, fix it before opening the PR. Do not open a PR with a known cfn-lint error.
- Warnings (`W` prefix) may be noted in the PR description and addressed in a follow-up if they are not actionable.
- If the PR touches no infra files (e.g., handler-only, docs-only, schema-only), running cfn-lint is not required.

## Checklist before opening

- [ ] Branch is not `main`
- [ ] `.env.local` values are not committed
- [ ] No Stripe keys, DB credentials, KMS key IDs, or device token salts appear in any file
- [ ] New Lambda functions are in `functions/` and follow handler conventions in `backend.instructions.md`
- [ ] New DB migrations are in `db/migrations/` and are idempotent
- [ ] New CloudFormation resources have `DeletionPolicy: Retain` if stateful
- [ ] CORS headers are returned on all Lambda responses (including errors)
- [ ] `training_level` is re-queried from Aurora — not read from the JWT claim
- [ ] If the PR touches `functions/**/*.py` or `tests/**/*.py`: pytest passes; summary line included in PR description
- [ ] If the PR touches `infra/**/*.yaml` or `infra/**/*.json`: cfn-lint reports no errors
- [ ] If a new file type or directory was introduced: verify `.gitignore` does not block it (`grep -r '<extension>' .gitignore`) before committing — this project has aggressive catch-all rules (`*.sql`, `*.csv`, `*.dump`) that silently swallow new file types

## GitHub tooling

- Use `git` for local branching, commits, and pushing; use the `gh` CLI for GitHub operations such as opening PRs, reading PR comments, checking review status, and managing issues
- Do **not** use GitKraken, GitLens MCP tools, or any other GUI Git client — `gh` and `git` on the command line are the only approved tools
- Read PR review comments with: `gh pr view <number> --comments`
- Read inline code review comments with: `gh api repos/{owner}/{repo}/pulls/<number>/comments`

## Using the gh CLI

Always use `--body-file` when creating or editing PRs and issues with multi-line descriptions.
This applies to `gh pr create`, `gh pr edit`, and `gh issue create`.

For `gh api` calls that post a body (PR review replies, issue comments, etc.), always use `--input` with a JSON file. Never use `-f body="..."` for content that contains em dashes, backticks, Unicode, or multiple lines — the terminal intercept corrupts it.

### Writing the body file

**Always** write the body using the file-creation tool (not the shell). Never use shell heredocs,
`echo`, `printf`, or any other shell redirection to create the file. The terminal intercept used
in this environment corrupts content written through the shell.

Correct approach for PR/issue bodies:

1. Use the file-creation tool to write the body to `/tmp/pr-body.txt`
2. Pass that file to the gh CLI

```bash
gh pr create --title "feat: description" --body-file /tmp/pr-body.txt --base main
gh pr edit 42 --body-file /tmp/pr-body.txt
gh issue create --title "Bug: description" --body-file /tmp/issue-body.txt
```

Correct approach for `gh api` POST calls (review replies, comments, etc.):

1. Use the file-creation tool to write JSON to `/tmp/reply.json`:
   ```json
   {"body": "Your reply text here."}
   ```
2. Pass it with `--input`:
   ```bash
   gh api repos/{owner}/{repo}/pulls/{number}/comments/{id}/replies --input /tmp/reply.json
   gh api repos/{owner}/{repo}/issues/{number}/comments --input /tmp/comment.json
   ```

3. Delete the temp file after the gh command succeeds

**Never** do any of the following — all will produce corrupted output:

```bash
# WRONG: heredoc through the shell
cat > pr-body.txt << 'EOF'
...
EOF

# WRONG: inline body flag with multi-line content
gh pr create --body "## Summary
..."

# WRONG: echo/printf redirection
echo "## Summary" > pr-body.txt

# WRONG: -f body= with special characters
gh api .../replies -f body="Fixed — see commit abc123"
```

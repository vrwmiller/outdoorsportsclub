---
applyTo: "**"
---

# Pull Request Instructions

## Branch rules

- Never commit directly to `main` — all changes go on a feature branch
- Branch names must be descriptive: `feat/<topic>`, `fix/<topic>`, `chore/<topic>`
- `<topic>` uses only lowercase letters, numbers, and hyphens — never a username, org name, or repo name prefix
- Open a PR to merge into `main`

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

## Checklist before opening

- [ ] Branch is not `main`
- [ ] `.env.local` values are not committed
- [ ] No Stripe keys, DB credentials, KMS key IDs, or device token salts appear in any file
- [ ] New Lambda functions are in `functions/` and follow handler conventions in `backend.instructions.md`
- [ ] New DB migrations are in `db/migrations/` and are idempotent
- [ ] New CloudFormation resources have `DeletionPolicy: Retain` if stateful
- [ ] CORS headers are returned on all Lambda responses (including errors)
- [ ] `training_level` is re-queried from Aurora — not read from the JWT claim

## GitHub tooling

- Use `git` for local branching, commits, and pushing; use the `gh` CLI for GitHub operations such as opening PRs, reading PR comments, checking review status, and managing issues
- Do **not** use GitKraken, GitLens MCP tools, or any other GUI Git client — `gh` and `git` on the command line are the only approved tools
- Read PR review comments with: `gh pr view <number> --comments`
- Read inline code review comments with: `gh api repos/{owner}/{repo}/pulls/<number>/comments`

## Using the gh CLI

Always use `--body-file` when creating or editing PRs and issues with multi-line descriptions.
This applies to `gh pr create`, `gh pr edit`, and `gh issue create`.

### Writing the body file

**Always** write the body using the file-creation tool (not the shell). Never use shell heredocs,
`echo`, `printf`, or any other shell redirection to create the file. The terminal intercept used
in this environment corrupts content written through the shell.

Correct approach:

1. Use the file-creation tool to write the body to `/tmp/pr-body.txt`
2. Pass that file to the gh CLI

```bash
gh pr create --title "feat: description" --body-file /tmp/pr-body.txt --base main
gh pr edit 42 --body-file /tmp/pr-body.txt
gh issue create --title "Bug: description" --body-file /tmp/issue-body.txt
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
```

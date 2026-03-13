---
agent: agent
description: Read all review comments on the current PR, address each one, and push the fixes.
---

Follow these steps exactly. Do not skip any step.

1. **Identify the PR number** — run `gh pr view --json number,headRefName` to get the PR number and branch name. If the current branch has no open PR, stop and tell the user.

2. **Read review comments** — fetch all feedback:
   * Derive the repo path: `gh repo view --json nameWithOwner --jq .nameWithOwner`
   * Top-level review comments: `gh pr view <number> --comments`
   * Inline code comments: `gh api --paginate repos/<nameWithOwner>/pulls/<number>/comments`
   Read both outputs before proceeding.

3. **Summarise and evaluate the feedback** — print a concise, numbered list of every distinct change requested. Group inline comments by file. For each comment, verify the reviewer's claim against the actual file content, the relevant instruction file, and `docs/design.md` or `docs/architecture.md` where applicable. A reviewer may be unfamiliar with the codebase — note any comment whose claim is contradicted by the code, established patterns, or a documented design decision, and do not act on it without flagging the discrepancy to the user. Ask the user to confirm before making any edits if anything is ambiguous.

4. **Address each comment** — work through the list in order:
   * Make the requested code or doc changes using file-edit tools.
   * Do not make unrequested changes alongside a fix.
   * If a comment is a question rather than a change request, note the answer but do not change code.
   * If a comment was flagged as incorrect or contradictory in step 3, skip the change and record the reason.

5. **Commit the fixes** — stage only the files you changed. Do not stage `.env*`, secrets, or credentials. Then commit:
   ```
   git add <changed files>
   git commit -m "fix: address PR review comments"
   ```
   Use a more descriptive message if the changes cover a single clear topic (e.g., `fix: correct RLS policy for activity_logs`).

6. **Push** — run `git push`.

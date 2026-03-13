---
agent: agent
description: Read all review comments on the current PR, address each one, push the fixes, and notify the reviewer.
---

Follow these steps exactly. Do not skip any step.

1. **Identify the PR number** — run `gh pr view --json number,headRefName` to get the PR number and branch name. If the current branch has no open PR, stop and tell the user.

2. **Read review comments** — fetch all feedback:
   * Derive the repo path: `gh repo view --json nameWithOwner --jq .nameWithOwner`
   * Top-level review comments: `gh pr view <number> --comments`
   * Inline code comments: `gh api repos/<nameWithOwner>/pulls/<number>/comments`
   Read both outputs before proceeding.

3. **Summarise the feedback** — print a concise, numbered list of every distinct change requested. Group inline comments by file. Ask the user to confirm before making any edits if anything is ambiguous.

4. **Address each comment** — work through the list in order:
   * Make the requested code or doc changes using file-edit tools.
   * Do not make unrequested changes alongside a fix.
   * If a comment is a question rather than a change request, note the answer but do not change code.

5. **Commit the fixes** — stage only the files you changed. Do not stage `.env*`, secrets, or credentials. Then commit:
   ```
   git add <changed files>
   git commit -m "fix: address PR review comments"
   ```
   Use a more descriptive message if the changes cover a single clear topic (e.g., `fix: correct RLS policy for activity_logs`).

6. **Push** — run `git push`.

7. **Request re-review** — run `gh pr comment <number> --body "@copilot-bot re-review"` to trigger a new Copilot review pass. To also notify human reviewers, add a follow-up comment: `gh pr comment <number> --body "Addressed all review comments — please take another look."`

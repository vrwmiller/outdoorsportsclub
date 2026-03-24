---
agent: agent
description: Read all review comments on the current PR, validate each against authoritative project docs and the changed files, fix valid claims, and post replies.
---

Follow these steps exactly. Do not skip any step.

1. **Identify the PR** — run `gh pr view --json number,headRefName` to get the PR number and branch name. If the current branch has no open PR, stop and tell the user.

2. **Gather authoritative context** — before reading any comments, establish the ground truth you will use to validate reviewer claims:
   * List the files changed in the PR: `gh pr view <number> --json files --jq '.files[].path'`
   * Read each changed file in full.
   * Invoke the architect agent: *"What sections of docs/design.md, docs/architecture.md, docs/stack-decisions.md, and which .github/instructions files are authoritative for these changed files: [list]?"*
   * Read every document the architect identifies in full before proceeding.

   The reviewer is expected to have sound software engineering knowledge but may not know this codebase. Their suggestions about general patterns are likely correct; their claims about project-specific decisions, existing conventions, or what the code already does must be verified against the files and docs you just read.

3. **Read review comments** — fetch all feedback:
   * Derive the repo path: `gh repo view --json nameWithOwner --jq .nameWithOwner`
   * Top-level PR comments: `gh pr view <number> --comments`
   * Inline code comments: `gh api --paginate repos/<nameWithOwner>/pulls/<number>/comments`

   Also fetch thread node IDs now — you will need them for step 7. Paginate until `hasNextPage` is false:
   ```bash
   gh api graphql -f query='
     query($owner: String!, $name: String!, $pr: Int!, $after: String) {
       repository(owner: $owner, name: $name) {
         pullRequest(number: $pr) {
           reviewThreads(first: 100, after: $after) {
             pageInfo { hasNextPage endCursor }
             nodes {
               id
               isResolved
               comments(first: 1) { nodes { databaseId } }
             }
           }
         }
       }
     }' -f owner='<owner>' -f name='<repo>' -F pr=<N>
   ```
   Repeat with `-f after='<endCursor>'` while `pageInfo.hasNextPage` is true. Build a map of `comment databaseId → thread node id` from the complete set of results.

   > **Note:** GitHub does not reliably mark comments as "outdated" — file-level comments (no anchor line) never go outdated regardless of how many pushes occur. Do not use the `outdated` field to determine whether a comment has been addressed. Track each comment ID explicitly.

4. **Classify every comment** — print a numbered list of every distinct comment with its ID. Group by file. For each comment, check the claim against the current file content and the authoritative documents from step 2. Assign exactly one classification:

   * **✅ Valid** — the claim is correct; a change is warranted. State what will be changed.
   * **❌ Rejected** — the claim contradicts the actual file content, a documented design decision, or an instruction file convention. Name the specific document and section that contradicts it. Do not act on it.
   * **⚠️ Ambiguous** — cannot be determined from available documents. Describe what is unclear and pause for user input before proceeding.

   Do not ask the user about ✅ Valid or ❌ Rejected comments — proceed directly for those.

5. **Process in batches of 5–6** — work through Valid comments in groups. For each batch:

   **a. Fix** — make the code or doc changes using file-edit tools. After each change, verify it is present in the file. Do not make unrequested changes alongside a fix. If a comment is a question only (no code change required), note the answer and move on.

   **b. Commit the batch**:
   ```
   git add <changed files>
   git commit -m "fix: address PR review comments (batch N)"
   ```
   Use a descriptive message if the batch covers a single topic (e.g., `fix: wrap all DB queries in transactions`).

   If the commit fails with exit code 3 and the message "The baseline file was updated", the `detect-secrets` pre-commit hook auto-updated `.secrets.baseline` to reflect line number shifts. Run:
   ```
   git add .secrets.baseline
   git commit -m "<same message as above>"
   ```
   This is expected and safe — the hook only updates line-number metadata, never suppresses new secrets.

   **c. Reply to each comment in the batch** — for each reply, write the body to `/tmp/reply.json` using the file-creation tool (never shell redirection or echo), then post it:
   ```json
   {"body": "Your reply text here."}
   ```
   ```
   gh api repos/<nameWithOwner>/pulls/<number>/comments/<comment_id>/replies --input /tmp/reply.json
   ```
   * **Valid comments that were fixed:** confirm what changed and why.
   * **Rejected comments:** explain the discrepancy — cite the specific document, section, or established pattern that contradicts the claim.
   * **Questions only:** answer directly; no code change needed.
   * Keep replies concise and factual. Do not be defensive.

   Repeat until all Valid comments are processed.

6. **Push** — run `git push` once after all batches are committed.

7. **Update docs if needed** — review the full set of fixes applied. If any fix changed an API contract, request/response shape, error code, auth level, schema column, or AWS service behavior, invoke the docs agent: *"Update docs/design.md to reflect [list of specific changes from this PR]"*. Do not resolve threads until the docs agent confirms the update is complete or confirms no update is needed.

8. **Resolve threads** — for every comment that was either fixed or rejected, resolve its review thread using the node ID map built in step 3:
   ```
   gh api graphql -f query='mutation { resolveReviewThread(input: { threadId: "<thread_node_id>" }) { thread { isResolved } } }'
   ```
   Resolve all threads before ending.

9. **Request a new Copilot review** — after all threads are resolved, tell the user:

   > All threads have been resolved. To trigger another Copilot review pass, click the **Re-request review** button (circular arrow icon) next to Copilot in the Reviewers sidebar on the PR page.

   Note: `@copilot review` in a comment triggers the Copilot *coding agent* (opens a sub-PR), not the PR reviewer — do not use it here. The reviewer-request API returns HTTP 422 for this repo. The manual button is the only reliable trigger.

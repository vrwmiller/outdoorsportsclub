---
agent: agent
description: Read all review comments on the current PR, validate each against authoritative project docs and the changed files, fix valid claims, and post replies.
---

# PR Review Workflow

Use plain, professional language. Do not use emojis.

1. **Identify the PR** — run `gh pr view --json number,headRefName` to get the PR number and branch name. If the current branch has no open PR, stop and tell the user.

2. **Gather context** — list the changed files: `gh pr view <number> --json files --jq '.files[].path'`. Read only the sections of each changed file that are relevant to the diff or review topic — do not read files in full unless the entire file is small. Then ask the system agent which sections of `docs/design.md`, `docs/architecture.md`, `docs/stack-decisions.md`, and `.github/instructions/` files are authoritative for those paths — read only those sections.

   The reviewer may not know this codebase. Treat suggestions about general patterns as high-signal; verify project-specific claims against the files and docs before accepting them.

   **Obtain repo metadata** — run `gh repo view --json nameWithOwner --jq '.nameWithOwner'` and split the result into `<owner>` and `<repo>` (e.g., `vrwmiller/outdoorsportsclub` → owner=`vrwmiller`, repo=`outdoorsportsclub`). You will need these values in step 3.

3. **Fetch review data** — use a paginated GraphQL query to retrieve all review threads, comment bodies, and thread node IDs:

   ```bash
   gh api graphql -f query='
     query($owner: String!, $name: String!, $pr: Int!, $endCursor: String) {
       repository(owner: $owner, name: $name) {
         pullRequest(number: $pr) {
           reviewThreads(first: 100, after: $endCursor) {
             pageInfo { hasNextPage endCursor }
             nodes {
               id
               isResolved
               comments(first: 100) {
                 nodes { databaseId body author { login } path line }
               }
             }
           }
         }
       }
     }' -f owner='<owner>' -f name='<repo>' -F pr=<number> --paginate
   ```

   Build a map of `reviewThreads.nodes.comments.nodes.databaseId → reviewThreads.nodes.id` from the results — you will need it in step 9 when resolving threads. Note: comments per thread are fetched up to 100; threads with more than 100 comments will be truncated. Do not use the `outdated` field to skip comments; track each comment ID explicitly.

4. **Classify every comment** — print each comment with its ID, grouped by file. Check the claim against the file content and authoritative context from step 2. Assign exactly one classification:

   - **Valid** — the claim is correct; a change is warranted. State what will be changed. A question-only comment that requires no code change is also classified Valid.
   - **Rejected** — the claim contradicts file content, a documented decision, or a project convention. Name the specific document and section.
   - **Ambiguous** — cannot be determined from available context. Describe what is unclear and pause for user input before proceeding.

   For Copilot comments: classify as Valid only after verifying the claim is correct and within scope. Reject if applying it would break application behavior, degrade UX, or introduce a security weakness.

   Do not ask the user about Valid or Rejected comments — proceed directly.

5. **Apply fixes** — for each Valid comment, make the change using file-edit tools. Verify each change is present after applying it. Do not make unrequested changes. If a comment is a question only, note the answer and move on.

   **Commit in logical groups** — commit fixes grouped by logical topic (e.g., all schema changes together, all handler changes together), not as a single monolithic commit. Use clear, scoped commit messages following the format in `.github/instructions/pr.instructions.md`:

   ```bash
   git add <changed files for this logical topic>
   git commit -m "fix(<scope>): short description"
   ```

   If a commit fails with exit code 3 and the message "The baseline file was updated", the `detect-secrets` hook updated `.secrets.baseline` — run:

   ```bash
   git add .secrets.baseline && git commit -m "<same message>"
   ```

6. **Reply to every inline review comment** — for each inline review comment in `reviewThreads`, write the body using the file-creation tool (never shell redirection), then post it:

   ```json
   {"body": "Your reply text."}
   ```

   ```bash
   gh api repos/<owner>/<repo>/pulls/<number>/comments/<comment_id>/replies --input /tmp/reply.json && rm /tmp/reply.json
   ```

   - Fixed: confirm what changed and why.
   - Rejected: cite the document, section, or pattern that contradicts the claim.
   - Question only (Valid, no code change): answer directly.
   - Keep replies concise and factual.

   Skip Ambiguous comments — do not reply until the user provides clarification.

   Note: This workflow addresses inline review comments only. Top-level PR conversation or timeline comments are not replied to in this workflow.

7. **Self-review gate** — before pushing, check the full set of changes:

   - **Docs**: if any fix changed an API contract, response shape, error code, auth level, schema column, or AWS service behavior, invoke the quality agent: *"Update docs/design.md to reflect [list of changes]"*. Wait for it to commit.
   - **Linter**: invoke the quality agent: *"Lint these files: [list of changed files]"*. Wait for it to commit any fixes.
   - **Security**: if any changed file matches `functions/**/*.py`, `db/**/*.sql`, or `infra/**/*.yaml`, invoke the system agent: *"Security review [list of files]"*. Fix High/Critical findings before pushing; note Medium/Low in the PR description.

   If none of the above conditions apply, proceed immediately.

8. **Push** — run `git push` once after all fixes and self-review commits are complete.

9. **Resolve threads** — resolve every thread that was fixed or rejected using the thread node IDs from step 3 (`reviewThreads.nodes.id`):

   ```bash
   gh api graphql -f query='mutation { resolveReviewThread(input: { threadId: "<thread_node_id>" }) { thread { isResolved } } }'
   ```

10. **Request a new Copilot review** — tell the user:

    > All threads have been resolved. To trigger another Copilot review pass, click the **Re-request review** button (circular arrow icon) next to Copilot in the Reviewers sidebar on the PR page.

    Note: `@copilot review` in a comment triggers the Copilot coding agent (opens a sub-PR), not the PR reviewer. The reviewer-request API returns HTTP 422 for this repo — the manual button is the only reliable trigger.

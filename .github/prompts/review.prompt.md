---
agent: agent
description: Read all review comments on the current PR, validate each against authoritative project docs and the changed files, fix valid claims, and post replies.
---

# PR Review Workflow

Use plain, professional language. Do not use emojis.

1. **Identify the PR** — run `gh pr view --json number,headRefName` to get the PR number and branch name. If the current branch has no open PR, stop and tell the user.

2. **Gather context** — list the changed files: `gh pr view <number> --json files --jq '.files[].path'`. Read only the sections of each changed file that are relevant to the diff or review topic — do not read files in full unless the entire file is small. Then ask the system agent which sections of `docs/design.md`, `docs/architecture.md`, `docs/stack-decisions.md`, and `.github/instructions/` files are authoritative for those paths — read only those sections.

   The reviewer may not know this codebase. Treat suggestions about general patterns as high-signal; verify project-specific claims against the files and docs before accepting them.

3. **Fetch review data** — use a single GraphQL query to retrieve all review threads, comment bodies, and thread node IDs in one call:

   ```bash
   gh api graphql -f query='
     query($owner: String!, $name: String!, $pr: Int!) {
       repository(owner: $owner, name: $name) {
         pullRequest(number: $pr) {
           comments(first: 100) {
             nodes { databaseId body author { login } }
           }
           reviewThreads(first: 100) {
             nodes {
               id
               isResolved
               comments(first: 10) {
                 nodes { databaseId body author { login } path line }
               }
             }
           }
         }
       }
     }' -f owner='<owner>' -f name='<repo>' -F pr=<N>
   ```

   Build a map of `comment databaseId → thread node id` from the results — you will need it in step 7. Do not use the `outdated` field to skip comments; track each comment ID explicitly.

4. **Classify every comment** — print each comment with its ID, grouped by file. Check the claim against the file content and authoritative context from step 2. Assign exactly one classification:

   - **Valid** — the claim is correct; a change is warranted. State what will be changed.
   - **Rejected** — the claim contradicts file content, a documented decision, or a project convention. Name the specific document and section.
   - **Ambiguous** — cannot be determined from available context. Describe what is unclear and pause for user input.

   For Copilot comments: classify as Valid only after verifying the claim is correct and within scope. Reject if applying it would break application behavior, degrade UX, or introduce a security weakness.

   Do not ask the user about Valid or Rejected comments — proceed directly.

5. **Apply fixes** — for each Valid comment, make the change using file-edit tools. Verify each change is present after applying it. Do not make unrequested changes. If a comment is a question only, note the answer and move on.

   Commit all fixes together:

   ```bash
   git add <changed files>
   git commit -m "fix: address PR review comments"
   ```

   Use a descriptive subject if the changes cover a single clear topic. If the commit fails with exit code 3 and the message "The baseline file was updated", the `detect-secrets` hook updated `.secrets.baseline` — run:

   ```bash
   git add .secrets.baseline && git commit -m "<same message>"
   ```

6. **Reply to every comment** — for each reply, write the body using the file-creation tool (never shell redirection), then post it:

   ```json
   {"body": "Your reply text."}
   ```

   ```bash
   gh api repos/<nameWithOwner>/pulls/<number>/comments/<comment_id>/replies --input /tmp/reply.json && rm /tmp/reply.json
   ```

   - Fixed: confirm what changed and why.
   - Rejected: cite the document, section, or pattern that contradicts the claim.
   - Question only: answer directly; no code change needed.
   - Keep replies concise and factual.

7. **Self-review gate** — before pushing, check the full set of changes:

   - **Docs**: if any fix changed an API contract, response shape, error code, auth level, schema column, or AWS service behavior, invoke the quality agent: *"Update docs/design.md to reflect [list of changes]"*. Wait for it to commit.
   - **Linter**: invoke the quality agent: *"Lint these files: [list of changed files]"*. Wait for it to commit any fixes.
   - **Security**: if any changed file matches `functions/**/*.py`, `db/**/*.sql`, or `infra/**/*.yaml`, invoke the system agent: *"Security review [list of files]"*. Fix High/Critical findings before pushing; note Medium/Low in the PR description.

   If none of the above conditions apply, proceed immediately.

8. **Push** — run `git push` once after all fixes and self-review commits are complete.

9. **Resolve threads** — resolve every thread that was fixed or rejected using the node IDs from step 3:

   ```bash
   gh api graphql -f query='mutation { resolveReviewThread(input: { threadId: "<thread_node_id>" }) { thread { isResolved } } }'
   ```

10. **Request a new Copilot review** — tell the user:

    > All threads have been resolved. To trigger another Copilot review pass, click the **Re-request review** button (circular arrow icon) next to Copilot in the Reviewers sidebar on the PR page.

    Note: `@copilot review` in a comment triggers the Copilot coding agent (opens a sub-PR), not the PR reviewer. The reviewer-request API returns HTTP 422 for this repo — the manual button is the only reliable trigger.

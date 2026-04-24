# Runbook: Processing Copilot PR Review Feedback

**Audience:** Developers and Webmaster.

This runbook defines how to handle Copilot reviewer feedback on pull requests.

---

## Policy reference

Do not restate acceptance and rejection policy in this runbook.

Use the review section in `.github/instructions/pr.instructions.md` and the workflow in `.github/prompts/review.prompt.md` as the canonical source of truth for:

* when to accept or reject Copilot reviewer suggestions
* what evidence is required when replying to or rejecting a suggestion
* how to process review comments and resolve threads

---

## Procedure

1. Open the pull request and fetch all Copilot review comments, including inline comments and PR-level comments.
2. Read each comment and classify it using the canonical policy references above.
3. For accepted comments, make the smallest change needed to address the feedback without expanding scope.
4. For rejected comments, reply with specific evidence that cites the exact file path and section or the concrete runtime behavior that contradicts the suggestion.
5. Re-run the required checks for the files you changed and confirm the pull request is still ready for review.
6. Reply to each review thread with the fix summary or rejection evidence, then resolve the thread when the response is complete.
7. If Copilot posts another review round, repeat this procedure until all valid comments are addressed.

---

## Workflow note

Use the PR review workflow in `.github/prompts/review.prompt.md` and the review section in `.github/instructions/pr.instructions.md` as the authoritative implementation procedure.

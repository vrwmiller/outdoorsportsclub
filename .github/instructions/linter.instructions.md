---
description: "Use when reviewing, linting, or fixing code quality issues. Covers standards for Markdown docs, TypeScript/Next.js frontend, and Python AWS Lambda functions."
applyTo: "**/*.md, **/*.ts, **/*.tsx, **/*.js, **/*.jsx, **/*.py"
---

# Linting & Style Standards

## Markdown (`docs/**`)

- Headings must follow hierarchy — no skipping levels (e.g., h1 → h3)
- Every table must have a header row and a separator row
- Use `**bold**` for UI labels, proper nouns (service names), and field names; use `backticks` for code values and column names
- No trailing whitespace
- Headings must be preceded and followed by exactly one blank line (MD022); this applies above and below every heading regardless of what follows (paragraph, list, table, or code block)
- Lists must be preceded and followed by exactly one blank line (MD032)
- List markers must be followed by exactly one space (MD030); use `* ` not `*   `
- Bullet lists use `*` as the list marker
- One blank line between sections; no double blank lines
- No duplicate headings at the same level under the same parent section — duplicate headings are allowed when they appear under different parent sections (e.g., a "Verdict" subsection in each top-level decision section is fine)

## TypeScript / Next.js (`**/*.ts`, `**/*.tsx`)

- Strict TypeScript — no implicit `any`; all function parameters and return types must be explicitly typed
- Use `const` by default; only use `let` when reassignment is needed; never use `var`
- Components must be named functions, not arrow function assignments at the module level
- No inline styles — use CSS modules or Tailwind classes only
- All API calls must handle both success and error states explicitly
- No hardcoded secrets, tokens, or API keys — use environment variables via `process.env`
- Imports ordered: React → Next.js → third-party → local (`@/`)

## Mermaid Diagrams (`docs/**/*.md`)

Mermaid `architecture-beta` diagram labels are parsed strictly. Violations cause silent parse failures or `unexpected character` errors.

**Prefer `flowchart LR` or `flowchart TD` over `architecture-beta` for complex graphs.** The `architecture-beta` renderer auto-places nodes with no grid control, causing text overlap and tangled edges when a group contains more than two services or a single node has many connections. `flowchart` uses the Dagre layout engine, which handles complex graphs cleanly, supports edge labels, and never overlaps node text.

**Use `architecture-beta` only for simple topology sketches** (few services, few edges, one or two services per group).

**Forbidden characters in `architecture-beta` group and service labels `[...]`:**

| Character | Problem | Fix |
| :--- | :--- | :--- |
| `.` | Breaks tokeniser (e.g., `Next.js`) | Use `NextJS` or omit the dot |
| `/` | Treated as path separator | Use a space or omit (e.g., `S3 Waivers` not `S3 — Waivers`) |
| `—` or `-` in labels | Em/en dash not valid label text | Use `and` or a plain space |
| `&` | Parsed as entity reference | Spell out `and` |
| `(` `)` | Parentheses reserved for icon syntax | Remove or rewrite (e.g., `AWS Primary Region` not `AWS (us-east-1)`) |

**Rules:**

- Group and service IDs must be a single `snake_case` token with no spaces or special characters
- IDs and labels are separate: `service my_db(database)[My Database Label]` — the ID never contains spaces; the label (inside `[]`) must contain only plain words and spaces
- Always validate a new diagram with the Mermaid validator before committing — do not assume valid syntax from prior examples

## Python / AWS Lambda (`**/*.py`)

- Follow PEP 8: 4-space indentation, max line length 100 characters
- All functions must have type annotations (parameters and return types)
- Lambda handlers must be named `handler(event, context)` and typed with `dict` and `LambdaContext`
- No bare `except:` — always catch specific exceptions
- Use `os.environ` for environment variable access; never hardcode credentials
- Return dicts must always include `statusCode` and `body` keys for API Gateway compatibility
- Use f-strings for string formatting; avoid `%` formatting and `.format()`

## Code Complexity & Bloat (all files)

- **Do the minimum necessary.** Serve the current requirement only — no hypothetical future needs.
- **No speculative abstractions.** Only extract a helper or utility if it is used in at least two places in the current change.
- **No defensive code for impossible cases.** Trust schema constraints, framework guarantees, and internal invariants.
- **No unused imports, variables, or dead code.**
- **No redundant comments.** Only comment where the *why* is not self-evident from the code.
- **No docstrings on unchanged code.** Only annotate functions you are writing or modifying.
- **Readable over clever.** A clear 5-line solution beats a clever 2-line solution that needs a comment to explain it.

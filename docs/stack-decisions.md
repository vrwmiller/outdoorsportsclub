# Stack Decisions — Analysis & Tradeoffs

This document records the full analysis behind key technology choices for **Outdoor Sports Club** that were examined in depth before being accepted, deferred, or rejected. The canonical locked decisions live in `design.md`; this document explains the reasoning behind them.

---

## 1. Frontend Framework — Next.js vs. Django

This section records the full analysis behind the frontend framework choice. The decision is currently **Next.js** (see `design.md` Section 9), but this analysis exists to document why the question was taken seriously and what tradeoffs were made.

### The Case for Reconsidering

The initial decision to use **Next.js** was made with an assumption of a React/TypeScript-fluent team. That assumption warrants scrutiny. Two legitimate concerns were raised:

* **Determinism:** Django's server-rendered model produces a consistent, predictable output independent of the client's browser or render engine. Next.js behavior varies by rendering mode (SSR, SSG, ISR, App Router Server Components, Client Components, Edge Runtime), and choosing the wrong mode for a given page produces subtle, sometimes production-only bugs.
* **Developer familiarity:** The backend Lambda functions are already Python. A Python-familiar developer building this solo or near-solo absorbs real friction cost from maintaining a TypeScript frontend. Building in a language you're less fluent in introduces more implementation risk than architectural elegance is worth.

These are not off-base concerns. They are worth resolving deliberately.

### The Critical Constraint

Before evaluating frameworks, one project-specific fact limits the scope of what either choice can deliver:

**The Stripe Terminal SDK is JavaScript — always.** The kiosk is the most reliability-critical surface in the system, and it runs JavaScript regardless of what framework serves the shell page. Django provides a deterministic server-rendered shell, but the payment and NFC layer on top remains a JavaScript runtime. Switching to Django does not eliminate JavaScript debugging from the surfaces that matter most.

This does not make Django a bad choice. It means the determinism gain is partial, not total.

### How the Architecture Would Change Under Django

### What disappears

| Current (Next.js) | Under Django |
| :--- | :--- |
| **Next.js** + **AWS Amplify Gen 2** | Django app on **AWS ECS Fargate** or Elastic Beanstalk |
| Amplify hosting + **Amazon CloudFront** CDN | Manually configured **CloudFront** in front of a load balancer |
| `npm` / Node build pipeline | `pip` / Gunicorn process management |
| TypeScript across the frontend | Python for everything except Stripe Terminal JS |
| RDS Data API (stateless Lambda → Aurora) | psycopg2 ORM + **Amazon RDS Proxy** for connection pooling |

### What gets simpler

* **One language.** Lambda functions are already Python. Django means Python everywhere — no TypeScript, no `npm`, no Node toolchain to maintain.
* **Stack traces are immediately readable.** Django exceptions go straight to the line. React hydration errors point at a virtual DOM diff.
* **Django's auth middleware** (`@login_required`, permission decorators) maps cleanly onto `training_level` gating with a custom authentication backend.
* **No rendering mode decision.** Django templates are server-rendered. There is no correct/incorrect choice to make per page.
* **The ORM for complex queries** is easier than the RDS Data API for multi-join queries — for example, fetching a member's active lane, guest count, waiver status, and dues standing in one query.

### What gets more complex

* **Cognito integration is no longer native.** **AWS Amplify Gen 2** has first-class **AWS Cognito** support. Django would require `python-social-auth` or `django-allauth` configured with Cognito as the OAuth2 provider — workable, but custom plumbing.
* **Django on Lambda is a known antipattern.** Python Django startup time at cold start is significant (often 3–8 seconds). The serverless web tier would need to be replaced with a persistent container process on **AWS ECS Fargate** or Elastic Beanstalk, introducing container orchestration and ongoing compute cost.
* **The clean API/frontend separation dissolves.** The current design has a crisp boundary: Lambdas expose an API; the frontend consumes it. Django views would talk directly to **Amazon Aurora** for frontend-facing requests, bypassing **Amazon API Gateway**. This is not inherently wrong, but it is a different architecture with a different security surface.
* **AWS Backup, Amazon S3, and AWS KMS are unaffected** — the data layer does not change.

### The RDS Proxy requirement

The current design uses RDS Data API in Lambda, which is connectionless. Django's psycopg2 holds persistent TCP connections to **Amazon Aurora**. Aurora Serverless v2 has a bounded connection limit (it scales with ACU but is not unlimited). For club-scale workloads this is manageable, but **Amazon RDS Proxy** must be added in front of Aurora to pool connections — otherwise each Gunicorn worker holds an open connection, and connection exhaustion becomes a failure mode under sustained load.

**Cost implication:** RDS Proxy is priced per vCPU-hour on the underlying Aurora cluster. Aurora Serverless v2 maps to roughly 2 vCPUs per ACU, and the proxy rate is approximately $0.015 per vCPU-hour. At the production floor of 2 ACU this adds approximately **$43/month** — a fixed overhead that exists regardless of traffic, paid even at 3am with zero users. The current Next.js + Lambda + RDS Data API architecture pays none of this; RDS Data API is connectionless and requires no proxy layer. The table below gives a rough sense of scale at different load levels.

| Load level | Approx. ACU | Approx. RDS Proxy cost/month |
| :--- | :--- | :--- |
| Idle (production floor) | 2 | ~$43 |
| Moderate | 4 | ~$87 |
| Busy weekend peak | 8 | ~$175 |

*These figures are ballpark estimates based on published AWS pricing and approximate ACU-to-vCPU mappings. Actual costs will vary depending on Aurora version, region, and peak ACU reached during each billing hour. Verify current pricing at the AWS RDS Proxy pricing page before making budget decisions.*

### Security Comparison

| Concern | Next.js | Django |
| :--- | :--- | :--- |
| CSRF protection | Manual — must add headers and configure | Built-in middleware, on by default |
| XSS protection | React escapes by default in JSX; raw HTML injection is opt-in | Template auto-escaping on by default |
| Clickjacking / security headers | Manual — must set `X-Frame-Options`, CSP, etc. | `django.middleware.security` includes these by default |
| SQL injection | RDS Data API uses parameterized queries | ORM uses parameterized queries; raw SQL requires explicit `.raw()` |
| Cognito token validation | **AWS Amplify** handles it natively | Custom middleware required |
| `training_level` enforcement | Must be re-queried from Aurora in each Lambda (documented invariant) | Django permission decorators + custom auth backend — same requirement, different syntax |
| Django Admin attack surface | N/A | `/admin/` is a well-known brute-force target; must be disabled, relocated, or restricted by IP if not used |

Django has a modest security advantage in that its defaults are more defensive out of the box. CSRF, clickjacking, and XSS protections are middleware you opt out of rather than opt into. The Django Admin attack surface is a real concern but is trivially mitigated.

### Verdict

Neither choice is wrong. The choice depends on who is building this and how.

**Arguments against switching to Django:**

* The kiosk has JavaScript complexity regardless — Django does not buy full determinism
* Django on Lambda is a poor fit; a container tier (**AWS ECS Fargate**) would need to be added that does not exist in the current design
* **AWS Cognito** integration loses its native **Amplify** support and requires custom OAuth2 plumbing

**Arguments for switching to Django:**

* Python familiarity lowers the real risk of implementation errors — this is more valuable than architectural elegance
* One language across Lambda functions and web tier: shared utilities, shared test patterns, shared dependency management
* Debugging is genuinely simpler for server-rendered Python applications
* Django's security defaults are more defensive with less configuration

**The honest summary:** if this project is built primarily by a Python-familiar developer, Django on **AWS ECS Fargate** is a sensible and defensible choice. The operational complexity of containers is real but well-documented. The **Next.js** choice is architecturally cleaner on paper but only if the developer is fluent in the React/TypeScript ecosystem. Building in a less-familiar language raises the implementation risk more than the architectural elegance reduces it.

This analysis does not change the current locked decision in `design.md`. If the framework decision is formally revisited, this document should be updated and Section 9 of `design.md` revised accordingly.

---

## 2. Database — Amazon Aurora Serverless v2 vs. Self-Hosted PostgreSQL

The current design uses **Amazon Aurora Serverless v2** (PostgreSQL-compatible) as the database. The question of replacing this with a self-hosted PostgreSQL instance on EC2 was raised as a cost-optimization measure. This section records that analysis.

### The Cost Appeal

At first glance, self-hosted Postgres is cheaper. A `t3.small` EC2 instance plus EBS storage runs approximately **$20–25/month** — a fraction of Aurora's ~$175/month production floor. PgBouncer (open-source connection pooler) would replace **Amazon RDS Proxy** at essentially no marginal cost beyond the instance it runs on.

### What You Take On

The Aurora cost floor is paying for a substantial operations burden that becomes your responsibility under a self-hosted model:

* **Patching is your job.** Aurora patches automatically. A self-hosted instance accumulates CVEs until you schedule and execute a maintenance window.
* **Backups are your job.** Aurora continuous PITR is built-in. Self-hosted requires WAL archiving to **Amazon S3** via WAL-G or pg_basebackup — custom tooling you write, test, and maintain.
* **High availability is your job.** Aurora has automatic failover. Self-hosted HA requires a standby replica, health checks, and a failover script — or you accept a single point of failure.
* **Multi-region replication is gone.** Aurora Global Database cross-region promotion completes in under 60 seconds. Self-hosted cross-region logical replication is a substantial ops project that would need to replace the entire DR design in `design.md` Section 8.
* **The "Red Button" procedure breaks.** The DR plan relies on Aurora snapshot + **AWS Backup** automatic cross-region copy. This entire story would need to be rewritten for self-hosted.

### Waiver Compliance

The design stores legally required safety waivers with 7-year S3 Object Lock retention. **AWS Backup Vault Lock** provides equivalent guarantees for Aurora database snapshots. A self-hosted Postgres backup to **Amazon S3** via `pg_dump` can be made immutable with careful IAM and S3 Object Lock policy work — but it requires custom implementation to achieve equivalent guarantees, and the burden of proof is on you to demonstrate compliance.

### The Better Cost Lever

If cost is the primary concern, replacing the database engine is the wrong tool. The more targeted lever is the **Aurora ACU floor**:

* `dev` is already configured to 0.5 ACU minimum (the lowest available), per the design
* Ensuring prod idles efficiently — no long-running queries, no idle connections holding ACUs up — gives meaningful savings without sacrificing any of the managed-service guarantees
* Reviewing Aurora pricing mode (standard I/O vs. I/O-Optimized) at the actual workload level may also reduce cost

### Verdict

Self-hosted PostgreSQL is not appropriate for this project. The combination of legal waiver retention requirements, multi-region DR guarantees, and the operational overhead of managing HA, patching, and backups without dedicated ops staffing makes the Aurora cost floor a reasonable trade. The savings from self-hosting would be consumed by the time required to build and maintain equivalent reliability and compliance tooling.

This decision is locked. See `design.md` for the Aurora Serverless v2 configuration.

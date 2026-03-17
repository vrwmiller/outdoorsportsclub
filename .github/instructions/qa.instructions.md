---
description: "Use when writing, editing, or reviewing tests for the Outdoor Sports Club project. Covers Python Lambda unit tests (pytest + moto), Next.js component tests (Jest + React Testing Library), Playwright end-to-end tests, and CI configuration."
applyTo: "tests/**/*.py, src/**/*.test.tsx, src/**/__tests__/**/*.tsx, e2e/**/*.ts, .github/workflows/*.yml, .github/workflows/*.yaml"
---

# QA & Testing Standards — Outdoor Sports Club

## Test Directory Layout

```
tests/                        # Python Lambda unit tests
  conftest.py                 # Shared fixtures (mock AWS env vars, sample events)
  unit/
    test_<handler_name>.py    # One file per Lambda handler
e2e/                          # Playwright end-to-end tests
  <flow_name>.spec.ts         # One file per user flow
src/
  **/__tests__/               # Jest + RTL component tests (co-located)
  **/*.test.tsx               # Inline test files acceptable for small components
.github/workflows/
  ci.yml                      # CI pipeline definition
```

## Python Lambda Tests (`tests/`)

### Framework

- `pytest` — test runner
- `moto` — mocks AWS services (S3, DynamoDB, SNS, Secrets Manager); use the `@mock_aws` decorator
- `pytest-mock` (`mocker` fixture) — mock Stripe SDK and other third-party clients

### File naming

- `test_<handler_name>.py` mirrors `functions/<handler_name>.py`
- Test function names: `test_<scenario>_<expected_outcome>` — e.g., `test_missing_token_returns_403`

### Required test cases per handler

Every handler must have tests for:

1. **Happy path** — valid auth, valid input, correct DB/AWS call made, `200` returned
2. **Missing auth** — no token header present → `403`
3. **Invalid auth** — malformed or revoked token → `403`
4. **Insufficient training level** — authenticated but below required level → `403`
5. **Invalid input** — missing required field or wrong type → `400`
6. **AWS failure** — simulate a boto3 exception → `500` with sanitised message

### Mocking patterns

```python
import json
import pytest
from moto import mock_aws
import boto3


@pytest.fixture
def aws_credentials(monkeypatch):
    """Prevent any real AWS calls by setting dummy credentials."""
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")


@pytest.fixture
def lambda_env(monkeypatch):
    """Set all required Lambda environment variables."""
    monkeypatch.setenv("DB_CLUSTER_ARN", "arn:aws:rds:us-east-1:123456789012:cluster:test")
    monkeypatch.setenv("DB_SECRET_ARN", "arn:aws:secretsmanager:us-east-1:123456789012:secret:test")
    monkeypatch.setenv("DB_NAME", "outdoorsportsclub")
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_TESTPOOL")
    monkeypatch.setenv("COGNITO_REGION", "us-east-1")
    monkeypatch.setenv("STRIPE_SECRET_ARN", "arn:aws:secretsmanager:us-east-1:123456789012:secret:stripe")
    monkeypatch.setenv("DEVICE_TOKEN_SALT_ARN", "arn:aws:secretsmanager:us-east-1:123456789012:secret:salt")
    monkeypatch.setenv("S3_WAIVER_BUCKET", "test-waivers")
    monkeypatch.setenv("SNS_ALERTS_TOPIC_ARN", "arn:aws:sns:us-east-1:123456789012:test-alerts")
    monkeypatch.setenv("CORS_ALLOW_ORIGIN", "http://localhost:3000")
```

- Scope `@mock_aws` to individual test functions or classes — never at module level
- Mock the Cognito JWKS validation at the function level using `mocker.patch`; patch the fully qualified name of the validation helper in the handler module, not the library itself:

  ```python
  # Assume your handler imports: from auth import validate_token
  # validate_token returns the decoded claims dict on success, raises on failure
  def test_happy_path(mocker, lambda_env):
      mocker.patch(
          "functions.check_in.validate_token",
          return_value={"sub": "member-uuid-1234", "training_level": 2},
      )
      # NOTE: training_level in the mock return value is used only to satisfy type
      # requirements in the JWT claims dict — the handler must re-query Aurora for
      # the authoritative value and MUST NOT rely on the claim for access control.
  ```

- Never use `training_level` from a fake JWT claim for access-control assertions — mock the RDS Data API response to return the authoritative value:

  ```python
  def test_insufficient_level_returns_403(mocker, lambda_env):
      mocker.patch("functions.check_in.validate_token", return_value={"sub": "member-uuid-1234"})
      # Mock the RDS re-query to return training_level = 1 (below required threshold)
      mocker.patch(
          "functions.check_in.rds_client.execute_statement",
          return_value={"records": [[{"longValue": 1}]]},  # training_level = 1
      )
      response = handler(event_with_auth, {})
      assert response["statusCode"] == 403
  ```

### Coverage requirement

- Minimum **80% overall line coverage** for Lambda handlers
- Run with: `pytest tests/ --cov=functions --cov-report=term-missing --cov-fail-under=80`

---

## Next.js Component Tests (`src/`)

### Framework

- `Jest` — test runner
- `React Testing Library` — component rendering and interaction
- `jest-environment-jsdom` — browser-like DOM environment
- `msw` (Mock Service Worker) — intercept `fetch` calls to the API

### File naming

- Co-locate with the component: `src/components/CheckInButton/__tests__/CheckInButton.test.tsx`
- Or inline for small components: `src/components/Badge.test.tsx`

### Required test cases per component

1. **Renders without crashing** — smoke test
2. **Displays correct content** — assert visible text, accessible roles
3. **Auth-gated routes** — mock unauthenticated session → assert redirect to `/`
4. **RBAC gating** — mock `training_level` values at and below threshold → assert portal rendered or redirect
5. **API calls** — use `msw` to intercept; assert correct URL, method, headers, and request body
6. **Error states** — mock API failure; assert user-facing error message rendered (no stack trace)

### Mocking patterns

```typescript
// Single module mock — configure behavior per test
jest.mock('aws-amplify/auth', () => ({
  getCurrentUser: jest.fn(),
  fetchAuthSession: jest.fn(),
}));

import { getCurrentUser, fetchAuthSession } from 'aws-amplify/auth';

describe('auth-gated component', () => {
  beforeEach(() => {
    (getCurrentUser as jest.Mock).mockReset();
    (fetchAuthSession as jest.Mock).mockReset();
  });

  it('redirects unauthenticated users to /', async () => {
    (getCurrentUser as jest.Mock).mockRejectedValueOnce(new Error('Not authenticated'));
    // ...render component and assert redirect to '/'
  });

  it('renders portal for authenticated member with training_level 3', async () => {
    (getCurrentUser as jest.Mock).mockResolvedValueOnce({ username: 'test-user' });
    (fetchAuthSession as jest.Mock).mockResolvedValueOnce({
      tokens: { idToken: { payload: { sub: 'uuid-123', training_level: 3 } } },
    });
    // ...render component and assert portal is visible
  });
});
```

- Use `msw` handlers in `src/mocks/handlers.ts`; start the server in `jest.setup.ts`
- Never call real API endpoints from tests

### Coverage requirement

- Minimum **70% overall line coverage** for frontend components
- Run with: `npx jest --coverage --coverageThreshold='{"global":{"lines":70}}'`

---

## End-to-End Tests (`e2e/`)

### Framework

- `Playwright` — browser automation
- Tests run against a locally running Next.js dev server (`http://localhost:3000`)

### File naming

- `<flow_name>.spec.ts` — e.g., `home-page.spec.ts`, `kiosk-check-in.spec.ts`

### Flow priority

| File | Surface | Flow | Priority |
| :--- | :--- | :--- | :--- |
| `home-page.spec.ts` | **Home Page** | Page loads; sign-in CTA visible; no member data in DOM | High |
| `member-auth.spec.ts` | **Member Portal** | Social login → redirect by `training_level`; unauthenticated access redirects to Home Page | High |
| `member-portal-qr-badge.spec.ts` | **Member Portal** | QR badge renders for authenticated member | High |
| `member-portal-level0.spec.ts` | **Member Portal** | Level 0 member sees dues/waiver prompt, not range access | Medium |
| `admin-portal-access.spec.ts` | **Admin Portal** | Level 3 member blocked; Level 4 RSO can open/close a range | High |
| `admin-portal-level6.spec.ts` | **Admin Portal** | Level 6 Webmaster can pair a device and reset member auth | High |
| `admin-portal-level5.spec.ts` | **Admin Portal** | Level 5 admin can view finance and member records | Medium |
| `kiosk-check-in.spec.ts` | **Kiosk View** | Happy path: valid member, correct level, valid waiver, dues paid, lane available → lane assigned | High |
| `kiosk-check-in.spec.ts` | **Kiosk View** | Insufficient `training_level` → violation alert displayed and screen locked | High |
| `kiosk-check-in.spec.ts` | **Kiosk View** | Expired waiver → violation alert displayed | High |
| `kiosk-check-in.spec.ts` | **Kiosk View** | Dues not current → violation alert displayed | High |
| `kiosk-check-in.spec.ts` | **Kiosk View** | No lanes available → check-in blocked with message | High |
| `kiosk-check-out.spec.ts` | **Kiosk View** | QR scan check-out → lane returns to available | High |
| `kiosk-guest-addon.spec.ts` | **Kiosk View** | Guest add-on flow: waiver acknowledgement + Stripe payment | High |
| `kiosk-violation-alert.spec.ts` | **Kiosk View** | Failed check-in → violation alert locked; Level 4+ clears it | High |
| `kiosk-revoked-device.spec.ts` | **Kiosk View** | Revoked device token rejected on next request | High |
| `consumable-purchase.spec.ts` | **Kiosk View** | Kiosk consumable purchase via Stripe Terminal | Medium |

### Conventions

- Use `page.getByRole()` and `page.getByText()` over CSS selectors
- Store shared test user credentials and device tokens in `e2e/.env.test` (gitignored)
- Never run E2E tests against production — use the `dev` environment or `localhost`
- Tag smoke tests with `@smoke` so CI can run a fast subset on every PR

---

## CI Pipeline (`.github/workflows/ci.yml`)

The CI pipeline runs on every push to any branch and on every PR targeting `main`. It must complete before any deployment workflow runs.

### Jobs and ordering

Jobs are chained with `needs:` so any failure prevents all downstream jobs from running. Do not use `continue-on-error: true` on any job.

```
           ┌─ test-python ─┐
lint ──────┤               ├── e2e
           └─ test-frontend ┘
```

`test-python` and `test-frontend` run in parallel (both `needs: lint`); `e2e` runs only after both pass.

| Job | `needs` | Trigger | Command |
| :--- | :--- | :--- | :--- |
| `lint` | — | Every push | `ruff check functions/` + `eslint src/` |
| `test-python` | `lint` | Every push | `pytest tests/ --cov=functions --cov-report=term-missing --cov-fail-under=80` |
| `test-frontend` | `lint` | Every push | `npx jest --coverage --coverageThreshold='{"global":{"lines":70}}'` |
| `e2e` | `test-python`, `test-frontend` | PRs to `main` only | Start dev server → `npx playwright test --grep @smoke` |

All four jobs must pass for a PR to be mergeable. Do not add bypass rules.

### Environment variables in CI

- Store all secrets in **GitHub Actions Secrets** — never hardcode in workflow YAML
- Use dummy values for `moto`-mocked AWS credentials (see `conftest.py` pattern above)
- The `CORS_ALLOW_ORIGIN` for CI should be `http://localhost:3000`

### Deployment workflows (`.github/workflows/deploy-dev.yml`, `deploy-prod.yml`)

Deployment workflows are separate from `ci.yml` and triggered only after CI passes on `main` (for `dev`) or on a version tag (for `prod`).

| Workflow | Trigger | Environment |
| :--- | :--- | :--- |
| `deploy-dev.yml` | Push to `main` (CI passed) | `dev` |
| `deploy-prod.yml` | Tag push matching `v*.*.*` | `prod` |

Each deployment workflow runs these steps in order. Each step uses the default `if: success()` condition — a failed step halts the workflow immediately and the remaining steps do not run:

1. `cloudformation deploy` — apply infrastructure changes
2. **Run all migrations** — execute every file in `db/migrations/*.sql` in filename (sort) order via the RDS Data API:

   ```bash
   shopt -s nullglob
   for f in db/migrations/*.sql; do
     aws rds-data execute-statement \
       --resource-arn "$AURORA_CLUSTER_ARN" \
       --secret-arn "$DB_SECRET_ARN" \
       --database osc \
       --sql "$(cat "$f")"
   done
   ```

   `shopt -s nullglob` makes the loop a no-op when no migration files exist (e.g., on first deploy). File names must be zero-padded (`001_…`) so lexicographic order matches migration order.

3. `lambda update-function-code` — deploy new Lambda packages

If step 2 fails, step 3 does not run. The existing Lambda code remains live. A human must investigate before the workflow is re-triggered.

### Pipeline failure policy

- No job or step uses `continue-on-error: true`
- No deployment step uses `if: always()` — only the default `if: success()`
- Failed runs are never auto-retried
- Repository notification settings must route workflow failures to the Webmaster
- The resolution procedure is in `docs/runbooks/ci-deployment-failure.md` — this is a **blocked runbook** pending workflow authoring; the Webmaster is the escalation point until it exists

---

## General Rules

- Tests must be deterministic — no reliance on system time, random values, or external network calls
- Use `freezegun` to control time-dependent logic in Python tests
- Clean up all mocked state between tests — use `autouse` fixtures where appropriate
- A failing test must never be silenced with `# noqa` or `// eslint-disable` without a linked issue number explaining why

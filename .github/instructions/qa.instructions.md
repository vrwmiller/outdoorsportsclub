---
description: "Use when writing, editing, or reviewing tests for the Outdoor Sports Club project. Covers Python Lambda unit tests (pytest + moto), Next.js component tests (Jest + React Testing Library), Playwright end-to-end tests, and CI configuration."
applyTo: "tests/**/*.py, src/**/*.test.tsx, src/**/__tests__/**/*.tsx, e2e/**/*.ts, .github/workflows/*.yml"
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
    monkeypatch.setenv("S3_WAIVER_BUCKET", "test-waivers")
    monkeypatch.setenv("SNS_ALERTS_TOPIC_ARN", "arn:aws:sns:us-east-1:123456789012:test-alerts")
    monkeypatch.setenv("CORS_ALLOW_ORIGIN", "http://localhost:3000")
```

- Scope `@mock_aws` to individual test functions or classes — never at module level
- Mock the Cognito JWKS validation at the function level using `mocker.patch`
- Never use `training_level` from a fake JWT claim — mock the RDS Data API response to return the authoritative value

### Coverage requirement

- Minimum **80% line coverage** per handler file
- Run with: `pytest tests/ --cov=functions --cov-report=term-missing`

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
// Mock Cognito session (unauthenticated)
jest.mock('aws-amplify/auth', () => ({
  getCurrentUser: jest.fn().mockRejectedValue(new Error('Not authenticated')),
}));

// Mock Cognito session (authenticated member, training_level 3)
jest.mock('aws-amplify/auth', () => ({
  getCurrentUser: jest.fn().mockResolvedValue({ username: 'test-user' }),
  fetchAuthSession: jest.fn().mockResolvedValue({
    tokens: { idToken: { payload: { sub: 'uuid-123', training_level: 3 } } },
  }),
}));
```

- Use `msw` handlers in `src/mocks/handlers.ts`; start the server in `jest.setup.ts`
- Never call real API endpoints from tests

### Coverage requirement

- Minimum **70% line coverage** per component file
- Run with: `npx jest --coverage`

---

## End-to-End Tests (`e2e/`)

### Framework

- `Playwright` — browser automation
- Tests run against a locally running Next.js dev server (`http://localhost:3000`)

### File naming

- `<flow_name>.spec.ts` — e.g., `home-page.spec.ts`, `kiosk-check-in.spec.ts`

### Flow priority

| File | Flow | Priority |
| :--- | :--- | :--- |
| `home-page.spec.ts` | Home Page loads; sign-in CTA visible | High |
| `member-auth.spec.ts` | Social login → redirect by `training_level` | High |
| `kiosk-check-in.spec.ts` | Device-paired kiosk → QR scan → check-in confirmed | High |
| `admin-reset-auth.spec.ts` | Level 6 admin resets a member's social auth | Medium |
| `consumable-purchase.spec.ts` | Kiosk consumable purchase via Stripe Terminal | Medium |

### Conventions

- Use `page.getByRole()` and `page.getByText()` over CSS selectors
- Store shared test user credentials and device tokens in `e2e/.env.test` (gitignored)
- Never run E2E tests against production — use a dedicated staging environment or `localhost`
- Tag smoke tests with `@smoke` so CI can run a fast subset on every PR

---

## CI Pipeline (`.github/workflows/ci.yml`)

The CI pipeline must run on every push to any branch and on every PR targeting `main`.

### Jobs

| Job | Trigger | Steps |
| :--- | :--- | :--- |
| `lint` | Every push | Run linter checks for Python (`flake8`/`ruff`) and TypeScript (`eslint`) |
| `test-python` | Every push | `pytest tests/ --cov=functions --cov-fail-under=80` |
| `test-frontend` | Every push | `npx jest --coverage --coverageThreshold='{"global":{"lines":70}}'` |
| `e2e` | PRs to `main` only | Start dev server → run Playwright `@smoke` suite |

### Environment variables in CI

- Store all secrets in **GitHub Actions Secrets** — never hardcode in workflow YAML
- Use dummy values for `moto`-mocked AWS credentials (see `conftest.py` pattern above)
- The `CORS_ALLOW_ORIGIN` for CI should be `http://localhost:3000`

---

## General Rules

- Tests must be deterministic — no reliance on system time, random values, or external network calls
- Use `freezegun` to control time-dependent logic in Python tests
- Clean up all mocked state between tests — use `autouse` fixtures where appropriate
- A failing test must never be silenced with `# noqa` or `// eslint-disable` without a linked issue number explaining why

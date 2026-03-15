---
description: "Use when writing, reviewing, or editing AWS infrastructure as code for the Outdoor Sports Club project. Covers CloudFormation, Amplify Gen 2, IAM, API Gateway, Cognito, Aurora, S3, KMS, Secrets Manager, SNS, CloudWatch, and AWS Backup configuration."
applyTo: "infra/**/*.yaml, infra/**/*.json, amplify/**/*.ts, amplify/**/*.yaml"
---

# Infrastructure Standards — Outdoor Sports Club

## AWS Services in Use

| Service | Purpose |
| :--- | :--- |
| **AWS Amplify Gen 2** | Frontend hosting, CI/CD pipeline, environment variable injection |
| **AWS CloudFormation** | All backend infrastructure not managed by Amplify |
| **AWS Lambda** | Backend compute — one function per endpoint; Python 3.12 |
| **AWS API Gateway** | REST API; regional endpoints per active region; Lambda Proxy Integration |
| **AWS Cognito** | Member auth — User Pool with Social Login; no kiosk app client |
| **Amazon Aurora Serverless v2** | PostgreSQL in a VPC; **Aurora Global Database** for multi-region |
| **Amazon S3** | Waiver storage; Object Lock; **Multi-Region Access Point** + Cross-Region Replication |
| **AWS KMS** | **Multi-region keys** (`mrk-`) replicated to all active regions |
| **AWS Secrets Manager** | DB credentials, Stripe key, device token salt; multi-region replication |
| **Amazon Route 53** | Latency-based or failover routing across regional API Gateway endpoints |
| **Amazon SNS** | SMS alerts topic |
| **Amazon CloudWatch** | Lambda logs, API Gateway access logs |
| **AWS Backup** | Aurora PITR (35-day) + daily cross-region copy to all regions in `RegionList` |

## File Layout

```
infra/
  stacks/
    aurora.yaml          # Aurora cluster, subnet group, security group
    api.yaml             # API Gateway REST API, stages, authorizer
    cognito.yaml         # User Pool, App Client, identity providers
    s3.yaml              # Waiver bucket, Object Lock, KMS encryption
    kms.yaml             # Customer-managed keys and aliases
    secrets.yaml         # Secrets Manager secret definitions
    sns.yaml             # SNS SMS topic
    backup.yaml          # AWS Backup plan and vault
    route53.yaml         # Hosted zone, health checks, A/ALIAS records
    iam/
      lambda-checkin-role.yaml
      lambda-checkout-role.yaml
      ... (one role per Lambda function)
amplify/
  backend.ts             # Amplify Gen 2 backend definition
```

## Naming Conventions

All resource logical IDs and physical names use the pattern `osc-<resource>-<env>`:

* e.g., `osc-aurora-prod`, `osc-waivers-bucket-prod`, `osc-kms-aurora-prod`
* Environments: `prod`, `staging`, `dev`
* CloudFormation stack names: `osc-<domain>-<env>` (e.g., `osc-aurora-prod`)

## IAM — Least Privilege

Each Lambda function gets its own execution role. Grant only the permissions that function actually invokes:

```yaml
# Example: check-in Lambda role
CheckInLambdaRole:
  Type: AWS::IAM::Role
  Properties:
    RoleName: osc-lambda-checkin-prod
    AssumeRolePolicyDocument:
      Version: "2012-10-17"
      Statement:
        - Effect: Allow
          Principal:
            Service: lambda.amazonaws.com
          Action: sts:AssumeRole
    Policies:
      - PolicyName: CheckInPolicy
        PolicyDocument:
          Version: "2012-10-17"
          Statement:
            - Effect: Allow
              Action:
                - rds-data:ExecuteStatement
                - rds-data:BeginTransaction
                - rds-data:CommitTransaction
                - rds-data:RollbackTransaction
              Resource: !Sub "arn:aws:rds:${AWS::Region}:${AWS::AccountId}:cluster:osc-aurora-prod"
            - Effect: Allow
              Action:
                - secretsmanager:GetSecretValue
              Resource: !Ref AuroraSecret
            - Effect: Allow
              Action:
                - logs:CreateLogGroup
                - logs:CreateLogStream
                - logs:PutLogEvents
              Resource: !Sub "arn:aws:logs:${AWS::Region}:${AWS::AccountId}:log-group:/aws/lambda/osc-checkin-prod:*"
```

* Never use `"Resource": "*"` for data-plane permissions
* Always include `logs:CreateLogGroup`, `logs:CreateLogStream`, `logs:PutLogEvents` scoped to the function's log group

## API Gateway

* Use **Lambda Proxy Integration** for all routes — the full HTTP request is passed to Lambda as `event`
* **Cognito Authorizer** on all `/v1/portal/*` and `/v1/admin/*` routes
* **No authorizer** on `/v1/kiosk/*` routes — Device Token is validated inside the Lambda
* Enable **CORS** at the API Gateway level; configure `Access-Control-Allow-Origin` from a stage variable — never hardcode the domain or use `*` in production
* Enable **API Gateway access logging** to a dedicated CloudWatch log group
* Use API Gateway **stage variables** for environment-specific values (Lambda ARNs, allowed origins)

## Route 53

### API Gateway custom domain (prerequisite)

Before Route 53 can route to an API Gateway endpoint, a custom domain name must be configured in API Gateway. This maps a domain like `api.outdoorsportsclub.example.com` to the regional API Gateway endpoint in each region.

```yaml
# In api.yaml — one ApiGatewayDomainName resource per region
ApiDomainName:
  Type: AWS::ApiGateway::DomainName
  Properties:
    DomainName: !Sub "api.outdoorsportsclub.${Environment}.example.com"
    RegionalCertificateArn: !Ref AcmCertArn   # ACM cert in same region
    EndpointConfiguration:
      Types: [REGIONAL]

ApiBasePathMapping:
  Type: AWS::ApiGateway::BasePathMapping
  Properties:
    DomainName: !Ref ApiDomainName
    RestApiId: !Ref RestApi
    Stage: !Ref ApiStage
```

* ACM certificate must be in the **same region** as the API Gateway endpoint (regional endpoints do not accept `us-east-1` certs issued for CloudFront)
* Use `prod` subdomain convention: `api.outdoorsportsclub.com` (prod), `api.staging.outdoorsportsclub.com` (staging)

### Hosted zone

* One Route 53 public hosted zone per domain: `outdoorsportsclub.com` (prod), `staging.outdoorsportsclub.com` (staging), `dev.outdoorsportsclub.com` (dev)
* Hosted zones are **not managed in CloudFormation** — create them once manually and reference the Zone ID via a CloudFormation parameter `HostedZoneId`

### Record types

| Scenario | Record type |
| :--- | :--- |
| Single region (default `dev`) | A ALIAS → regional API Gateway domain name |
| Multi-region active-active | A ALIAS + `RoutingPolicy: Latency` in each region |
| Multi-region active-passive | A ALIAS + `RoutingPolicy: Failover` (PRIMARY / SECONDARY) |

Always use **A ALIAS** records (not CNAME) for API Gateway — ALIAS records are free at the zone apex and have lower latency than CNAMEs.

### Health checks (multi-region only)

* One health check per regional API Gateway endpoint, monitoring `GET /v1/health` (a lightweight Lambda that returns `200 OK`)
* Type: `HTTPS`; resource path: `/v1/health`; request interval: `30` seconds; failure threshold: `3`
* Associate each latency/failover record with its regional health check
* When `IsMultiRegion` is false, skip health check resources to avoid cost

### CloudFormation snippet (single-region)

```yaml
# In route53.yaml
Parameters:
  HostedZoneId:
    Type: String
    Description: Route 53 hosted zone ID for the environment domain
  ApiGatewayRegionalDomainName:
    Type: String
    Description: Regional domain name output from api.yaml (Fn::ImportValue)
  ApiGatewayRegionalHostedZoneId:
    Type: String
    Description: Hosted zone ID of the API Gateway regional endpoint (from API Gateway service)

Resources:
  ApiAliasRecord:
    Type: AWS::Route53::RecordSet
    Properties:
      HostedZoneId: !Ref HostedZoneId
      Name: !Sub "api.outdoorsportsclub.${Environment}.example.com"
      Type: A
      AliasTarget:
        DNSName: !Ref ApiGatewayRegionalDomainName
        HostedZoneId: !Ref ApiGatewayRegionalHostedZoneId
        EvaluateTargetHealth: false
```

## Aurora Serverless v2

* Aurora must be deployed in a **VPC** with private subnets and a security group that allows no inbound internet traffic
* Lambda does **not** need to be in the VPC — **RDS Data API** is a public AWS service endpoint that accepts requests from any Lambda with the correct IAM permissions and Secret ARN
* Set `MinCapacity: 0.5` and `MaxCapacity: 4` ACUs for dev/staging; `MinCapacity: 1` and `MaxCapacity: 16` for production
* Enable `EnableHttpEndpoint: true` on the cluster to activate the RDS Data API
* Reference the Secrets Manager secret ARN in the cluster definition for RDS Data API authentication

## S3 — Waiver Bucket

* Enable **S3 Object Lock at bucket creation** — it cannot be enabled after the fact
* `prod`: Use **Compliance Mode** with a 7-year (2557-day) default retention period — objects cannot be deleted or shortened
* `dev`: Use **Governance Mode** with a 7-day default retention period — objects can be deleted by an admin; allows test data cleanup
* Enable **KMS server-side encryption** (`SSEAlgorithm: aws:kms`) using the `osc-kms-s3-prod` key
* Block all public access — no public bucket policies, no ACLs
* Set `DeletionPolicy: Retain` on the bucket resource in CloudFormation

## KMS

* Create separate customer-managed keys for Aurora and S3
* Set key aliases: `alias/osc-aurora-prod`, `alias/osc-s3-waivers-prod`
* Key policy must grant access to the Aurora service principal and the Lambda execution roles that perform S3 reads/writes
* Set `DeletionPolicy: Retain` — never schedule key deletion without Webmaster approval; minimum pending window is 7 days

## Secrets Manager

* One secret per sensitive value — do not bundle multiple secrets into one JSON blob
* Enable automatic rotation where supported (Aurora master credentials support native rotation via Secrets Manager)
* Secret naming: `osc/<env>/<purpose>` (e.g., `osc/prod/aurora-master`, `osc/prod/stripe-key`, `osc/prod/device-token-salt`)

### Secret inventory

| Secret name | Used by | Lambda env var |
| :--- | :--- | :--- |
| `osc/<env>/aurora-master` | RDS Data API (cluster auth) | `DB_SECRET_ARN` |
| `osc/<env>/stripe-key` | Stripe SDK in Lambda | `STRIPE_SECRET_ARN` |
| `osc/<env>/device-token-salt` | Device token HMAC in Lambda | `DEVICE_TOKEN_SALT_ARN` |

### Name → ARN wiring pattern

Lambda env vars must reference the **ARN**, not the human-readable name. Use CloudFormation `Outputs` in `secrets.yaml` to export each secret's ARN, then import them into the Lambda stack via `Fn::ImportValue`:

```yaml
# secrets.yaml — export the ARN
Outputs:
  StripeSecretArn:
    Value: !Ref StripeSecret
    Export:
      Name: !Sub "osc-stripe-secret-arn-${Environment}"

  DeviceTokenSaltArn:
    Value: !Ref DeviceTokenSaltSecret
    Export:
      Name: !Sub "osc-device-token-salt-arn-${Environment}"
```

```yaml
# In the Lambda stack (e.g., api.yaml) — import the ARN into the function's environment
KioskPairLambda:
  Type: AWS::Lambda::Function
  Properties:
    Environment:
      Variables:
        DEVICE_TOKEN_SALT_ARN: !ImportValue
          Fn::Sub: "osc-device-token-salt-arn-${Environment}"
        STRIPE_SECRET_ARN: !ImportValue
          Fn::Sub: "osc-stripe-secret-arn-${Environment}"
```

* Never pass the human-readable secret name as an env var — only ARNs
* The same pattern applies to `DB_SECRET_ARN` (exported from `aurora.yaml`)

## AWS Backup

* Backup plan targets the Aurora cluster and S3 waiver bucket
* Rules:
    * Continuous backup (PITR) on Aurora — 35-day retention window
    * Daily snapshot at 02:00 UTC — 35-day retention in primary region
    * Cross-region copy rule to every region in `RegionList` — 35-day retention
* Backup vault name: `osc-backup-vault-<env>`; enable AWS Backup Vault Lock in Compliance mode on `prod` only — do not enable Vault Lock on `dev`

## Non-Production Environment

The `dev` environment is a separate CloudFormation stack with an `Environment: dev` parameter. It uses the same templates as `prod` with reduced-cost, relaxed-retention settings.

**Privacy rule — enforced, not advisory:** The `dev` Aurora cluster must never contain real member PII. This applies to all columns in the `members` table: `email`, `home_phone`, `mobile_phone`, `social_provider_id`, and `member_num`. Required for GDPR and CCPA compliance. Use synthetically generated test data only. If a production snapshot must be used for debugging, anonymise it before import.

| Setting | `dev` value | `prod` value |
| :--- | :--- | :--- |
| Aurora `MinCapacity` | `0.5` | `1` |
| Aurora `MaxCapacity` | `4` | `16` |
| S3 Object Lock mode | `GOVERNANCE` | `COMPLIANCE` |
| S3 Object Lock retention | 7 days | 2557 days (7 years) |
| Backup Vault Lock | Off | Compliance mode |
| Backup retention | 7 days | 35 days |
| Stripe secret path | `osc/dev/stripe-key` (test-mode key) | `osc/prod/stripe-key` (live key) |
| Cognito User Pool | Separate pool — no real member accounts | Production pool |

Naming convention applies: all `dev` resources use the `-dev` suffix (e.g., `osc-aurora-dev`, `osc-backup-vault-dev`).

## Multi-Region Design

The infrastructure is parameterized for variable region count. Region count is a deployment-time decision, not an architectural one.

### RegionList parameter

All stacks that provision replicatable resources accept a `RegionList` parameter (ordered list of AWS region names). The first entry is always the primary (writer) region.

```yaml
Parameters:
  RegionList:
    Type: CommaDelimitedList
    Default: "us-east-1"
    Description: >-
      Ordered list of active regions. First entry is the primary (writer) region.
      Add a region here to enable active-active multi-region deployment.
      Example multi-region value: "us-east-1,us-east-2"
```

Use `!Select [0, !Ref RegionList]` to reference the primary region. Use `Conditions` to gate replication resources:

```yaml
Conditions:
  IsMultiRegion: !Not [!Equals [!Select [1, !Split [",", !Join [",", [!Join [",", !Ref RegionList], "SENTINEL"]]]], "SENTINEL"]]
```

Only provision cross-region resources (Aurora Global Database secondary clusters, KMS replica keys, S3 CRR rules, Secrets Manager replicas, Route 53 failover records) when `IsMultiRegion` is true.

### Per-region resources

Each region in `RegionList` must have an identical deployment of:

| Resource | Multi-region mechanism |
| :--- | :--- |
| Aurora Serverless v2 | **Aurora Global Database** — one writer, N readers; auto-failover <60s |
| S3 waiver bucket | **Multi-Region Access Point (MRAP)** + **S3 Cross-Region Replication** |
| KMS keys | **Multi-Region Keys** (`mrk-` prefix) — same key material, regional ARNs |
| Secrets Manager | **Multi-region replication** — secrets pushed to each active region |
| API Gateway | **Regional endpoint** in each region; Route 53 latency/failover routing |
| Lambda functions | Deployed identically to each region — same code, region-specific env vars |

### Traffic routing

* Use **Amazon Route 53** with latency-based routing (active-active) or failover routing (active-passive) based on `RegionList` length
* Route 53 Health Checks monitor each regional API Gateway endpoint
* When `IsMultiRegion` is false, Route 53 records point to the single regional endpoint with no failover policy

### Single-region deployment (default)

With `RegionList: "us-east-1"`:

* Aurora Global Database secondary clusters: **not provisioned**
* KMS replica keys: **not provisioned**
* S3 CRR rules: **not provisioned**
* Secrets Manager replication: **not provisioned**
* Route 53 failover records: **not provisioned** (single A/ALIAS record only)

This keeps dev and staging costs minimal while preserving the ability to go multi-region with a single parameter change.

## CloudFormation Conventions

* All stacks use `DeletionPolicy: Retain` on stateful resources (Aurora, S3, KMS, Secrets Manager)
* Use CloudFormation **parameters** for account-specific values (account ID, region, domain names) — never hardcode
* Use CloudFormation **outputs** and **cross-stack references** (`Fn::ImportValue`) to share resource ARNs between stacks
* Tag all resources with: `Project: outdoor-sports-club`, `Environment: <env>`, `ManagedBy: cloudformation`

## Security Checklist (run before any production deployment)

* [ ] No `*` in IAM resource ARNs
* [ ] CORS `Allow-Origin` is scoped to the specific domain (not `*`)
* [ ] S3 bucket has block-public-access enabled
* [ ] All Lambda environment variables that reference secrets use Secrets Manager ARNs, not plaintext values
* [ ] CloudWatch log groups have a retention policy set (do not use indefinite retention)
* [ ] Aurora security group denies all inbound traffic from `0.0.0.0/0`
* [ ] KMS key rotation is enabled on all customer-managed keys

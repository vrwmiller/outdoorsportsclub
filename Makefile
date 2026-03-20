# =============================================================================
# Outdoor Sports Club — deployment tooling
# =============================================================================
#
# Quickstart:
#   1. Generate a device token salt:
#        make gen-salt
#      Copy the output — you will need it in step 2.
#
#   2. Deploy all supporting infrastructure stacks:
#        make deploy-base ENV=dev DEVICE_TOKEN_SALT=<output-from-step-1>
#
#   3. Package Lambda handlers and upload to S3:
#        make package upload ENV=dev
#
#   4. Deploy Lambda function stack:
#        make deploy-lambda ENV=dev
#
#   5. Run database migrations:
#        make migrate ENV=dev
#
#   6. Invoke a function directly (no API Gateway required):
#        make invoke FUNCTION=osc-kiosk-range-lanes-dev \
#                    PAYLOAD='{"headers":{"x-device-token":"<token>"},"httpMethod":"GET"}'
#
# For a full first-time deploy in a single command:
#   make deploy-all ENV=dev DEVICE_TOKEN_SALT=<salt> && make migrate ENV=dev
# =============================================================================

ENV             ?= dev
AWS_PROFILE     ?= outdoorsportsclub
REGION          ?= us-east-1
CORS_ALLOW_ORIGIN ?= http://localhost:3000

# Optional on re-runs: when unset, CloudFormation reuses the previous value for
# the DeviceTokenSalt parameter (UsePreviousValue behaviour). Required on first
# deploy. Generate with: make gen-salt
DEVICE_TOKEN_SALT ?=

# Expands to a --parameter-overrides token only when DEVICE_TOKEN_SALT is set.
_SALT_PARAM = $(if $(DEVICE_TOKEN_SALT),DeviceTokenSalt=$(DEVICE_TOKEN_SALT))

BUILD_DIR = dist/lambda

# Stack names follow the osc-<domain>-<env> convention from infra.instructions.md
STACK_KMS       = osc-kms-$(ENV)
STACK_SECRETS   = osc-secrets-$(ENV)
STACK_SNS       = osc-sns-$(ENV)
STACK_S3        = osc-s3-$(ENV)
STACK_AURORA    = osc-aurora-$(ENV)
STACK_BACKUP    = osc-backup-$(ENV)
STACK_IAM_KIOSK = osc-iam-kiosk-$(ENV)
STACK_ARTIFACTS = osc-artifacts-$(ENV)
STACK_LAMBDA    = osc-lambda-$(ENV)

.PHONY: help gen-salt package upload \
        deploy-kms deploy-secrets deploy-sns deploy-s3 deploy-aurora \
        deploy-backup deploy-iam-kiosk deploy-artifacts deploy-lambda \
        deploy-base deploy-all update-code migrate invoke \
        destroy-lambda destroy-sns destroy-iam

# =============================================================================
help:
	@echo ""
	@echo "Usage: make <target> [ENV=dev|prod] [AWS_PROFILE=outdoorsportsclub]"
	@echo ""
	@echo "Targets:"
	@echo "  gen-salt          Generate a random device token salt (copy output to DEVICE_TOKEN_SALT)"
	@echo "  package           Zip Lambda handlers into $(BUILD_DIR)/"
	@echo "  upload            Upload ZIPs to the S3 artifacts bucket"
	@echo "  deploy-base       Deploy supporting stacks (kms→secrets→sns→s3→aurora→backup→iam→artifacts)"
	@echo "  deploy-lambda     Deploy the Lambda function stack"
	@echo "  deploy-all        Full first-time deploy: deploy-base + package + upload + deploy-lambda"
	@echo "  update-code       Push newly uploaded ZIPs to Lambda (use after 'make upload' on code-only changes)"
	@echo "  migrate           Run all database migrations against the deployed Aurora cluster"
	@echo "  invoke            Invoke a Lambda directly (FUNCTION=name PAYLOAD='{...}')"
	@echo ""
	@echo "Destroy targets (dev only — blocked on ENV=prod):"
	@echo "  destroy-lambda    Delete the Lambda + API Gateway stack (rebuildable via deploy-lambda)"
	@echo "  destroy-sns       Delete the SNS topic stack (rebuildable via deploy-base)"
	@echo "  destroy-iam       Delete the IAM roles stack (rebuildable via deploy-base)"
	@echo ""
	@echo "Variables:"
	@echo "  ENV=$(ENV)  AWS_PROFILE=$(AWS_PROFILE)  REGION=$(REGION)"
	@echo "  CORS_ALLOW_ORIGIN=$(CORS_ALLOW_ORIGIN)"
	@echo ""

# =============================================================================
gen-salt:
	@openssl rand -hex 32

# =============================================================================
# Packaging — zip each handler with its shared _auth.py dependency.
# Kiosk handlers: _auth.py is copied in before zipping and removed after.
# Devices/pair:   standalone handler, no _auth.py dependency.
# =============================================================================
package:
	@mkdir -p $(BUILD_DIR)
	@echo "Packaging kiosk handlers..."
	@for handler in checkin checkout waiver guest-payment consumable-purchase dues range-lanes waitlist-cancel; do \
		cp functions/kiosk/_auth.py functions/kiosk/$$handler/_auth.py; \
		(cd functions/kiosk/$$handler && zip -qr ../../../$(BUILD_DIR)/kiosk-$$handler.zip .); \
		rm functions/kiosk/$$handler/_auth.py; \
		echo "  packaged kiosk-$$handler.zip"; \
	done
	@echo "Packaging devices/pair handler..."
	@(cd functions/devices/pair && zip -qr ../../../$(BUILD_DIR)/devices-pair.zip .)
	@echo "  packaged devices-pair.zip"
	@echo "Done. Artifacts in $(BUILD_DIR)/"

# =============================================================================
# Upload — push ZIPs to the artifacts bucket.
# The bucket name is deterministic: osc-lambda-artifacts-<env>-<account-id>.
# =============================================================================
upload:
	$(eval ACCOUNT_ID := $(shell aws sts get-caller-identity \
		--query Account --output text --profile $(AWS_PROFILE)))
	@echo "Uploading Lambda ZIPs to s3://osc-lambda-artifacts-$(ENV)-$(ACCOUNT_ID)/ ..."
	@for zip in $(BUILD_DIR)/*.zip; do \
		aws s3 cp "$$zip" "s3://osc-lambda-artifacts-$(ENV)-$(ACCOUNT_ID)/$$(basename $$zip)" \
			--profile $(AWS_PROFILE) --region $(REGION); \
		echo "  uploaded $$(basename $$zip)"; \
	done

# =============================================================================
# Stack deployments — in dependency order.
# All use --no-fail-on-empty-changeset so re-runs are safe.
# =============================================================================

deploy-kms:
	aws cloudformation deploy \
		--stack-name  $(STACK_KMS) \
		--template-file infra/stacks/kms.yaml \
		--parameter-overrides Environment=$(ENV) \
		--no-fail-on-empty-changeset \
		--profile $(AWS_PROFILE) --region $(REGION)

deploy-secrets:
	aws cloudformation deploy \
		--stack-name  $(STACK_SECRETS) \
		--template-file infra/stacks/secrets.yaml \
		--parameter-overrides Environment=$(ENV) $(_SALT_PARAM) \
		--no-fail-on-empty-changeset \
		--profile $(AWS_PROFILE) --region $(REGION)

deploy-sns:
	aws cloudformation deploy \
		--stack-name  $(STACK_SNS) \
		--template-file infra/stacks/sns.yaml \
		--parameter-overrides Environment=$(ENV) \
		--no-fail-on-empty-changeset \
		--profile $(AWS_PROFILE) --region $(REGION)

deploy-s3:
	aws cloudformation deploy \
		--stack-name  $(STACK_S3) \
		--template-file infra/stacks/s3.yaml \
		--parameter-overrides Environment=$(ENV) \
		--no-fail-on-empty-changeset \
		--profile $(AWS_PROFILE) --region $(REGION)

deploy-aurora:
	aws cloudformation deploy \
		--stack-name  $(STACK_AURORA) \
		--template-file infra/stacks/aurora.yaml \
		--parameter-overrides Environment=$(ENV) \
		--no-fail-on-empty-changeset \
		--profile $(AWS_PROFILE) --region $(REGION)

deploy-backup:
	aws cloudformation deploy \
		--stack-name  $(STACK_BACKUP) \
		--template-file infra/stacks/backup.yaml \
		--parameter-overrides Environment=$(ENV) \
		--capabilities CAPABILITY_NAMED_IAM \
		--no-fail-on-empty-changeset \
		--profile $(AWS_PROFILE) --region $(REGION)

deploy-iam-kiosk:
	aws cloudformation deploy \
		--stack-name  $(STACK_IAM_KIOSK) \
		--template-file infra/stacks/iam/lambda-kiosk-roles.yaml \
		--parameter-overrides Environment=$(ENV) \
		--capabilities CAPABILITY_NAMED_IAM \
		--no-fail-on-empty-changeset \
		--profile $(AWS_PROFILE) --region $(REGION)

deploy-artifacts:
	aws cloudformation deploy \
		--stack-name  $(STACK_ARTIFACTS) \
		--template-file infra/stacks/artifacts.yaml \
		--parameter-overrides Environment=$(ENV) \
		--no-fail-on-empty-changeset \
		--profile $(AWS_PROFILE) --region $(REGION)

deploy-lambda:
	aws cloudformation deploy \
		--stack-name  $(STACK_LAMBDA) \
		--template-file infra/stacks/lambda.yaml \
		--parameter-overrides Environment=$(ENV) CorsAllowOrigin=$(CORS_ALLOW_ORIGIN) \
		--no-fail-on-empty-changeset \
		--profile $(AWS_PROFILE) --region $(REGION)

# =============================================================================
# Composite targets
# =============================================================================

# Deploy all stacks except lambda (does not need DEVICE_TOKEN_SALT after first
# run — CloudFormation will detect no-change on secrets if the value is the same).
deploy-base: deploy-kms deploy-secrets deploy-sns deploy-s3 \
             deploy-aurora deploy-backup deploy-iam-kiosk deploy-artifacts

# Full first-time deploy.
deploy-all: deploy-base package upload deploy-lambda

# =============================================================================
# Code update — force Lambda to pick up a newly uploaded ZIP.
# CloudFormation only reacts to template/parameter changes, not S3 object
# content. Run this after 'make upload' whenever re-deploying changed code
# without a template change.
# =============================================================================
update-code:
	$(eval ACCOUNT_ID := $(shell aws sts get-caller-identity \
		--query Account --output text --profile $(AWS_PROFILE)))
	@echo "Updating Lambda function code from s3://osc-lambda-artifacts-$(ENV)-$(ACCOUNT_ID)/ ..."
	@for fn in checkin checkout waiver guest-payment consumable-purchase dues range-lanes waitlist-cancel; do \
		aws lambda update-function-code \
			--function-name osc-kiosk-$$fn-$(ENV) \
			--s3-bucket osc-lambda-artifacts-$(ENV)-$(ACCOUNT_ID) \
			--s3-key kiosk-$$fn.zip \
			--profile $(AWS_PROFILE) --region $(REGION) \
			--output text --query 'FunctionName'; \
	done
	aws lambda update-function-code \
		--function-name osc-devices-pair-$(ENV) \
		--s3-bucket osc-lambda-artifacts-$(ENV)-$(ACCOUNT_ID) \
		--s3-key devices-pair.zip \
		--profile $(AWS_PROFILE) --region $(REGION) \
		--output text --query 'FunctionName'

# =============================================================================
# Migrations — query stack outputs for the cluster/secret ARNs, then run.
# =============================================================================
migrate:
	$(eval CLUSTER_ARN := $(shell aws cloudformation describe-stacks \
		--stack-name $(STACK_AURORA) \
		--query "Stacks[0].Outputs[?OutputKey=='AuroraClusterArn'].OutputValue" \
		--output text --profile $(AWS_PROFILE) --region $(REGION)))
	$(eval SECRET_ARN := $(shell aws cloudformation describe-stacks \
		--stack-name $(STACK_SECRETS) \
		--query "Stacks[0].Outputs[?OutputKey=='AuroraMasterSecretArn'].OutputValue" \
		--output text --profile $(AWS_PROFILE) --region $(REGION)))
	CLUSTER_ARN="$(CLUSTER_ARN)" \
	SECRET_ARN="$(SECRET_ARN)" \
	DATABASE=osc \
	AWS_PROFILE=$(AWS_PROFILE) \
	AWS_REGION=$(REGION) \
	python3 scripts/migrate.py

# =============================================================================
# Direct Lambda invocation — no API Gateway required.
# Usage: make invoke FUNCTION=osc-kiosk-range-lanes-dev \
#                    PAYLOAD='{"headers":{"x-device-token":"<tok>"},"httpMethod":"GET"}'
# =============================================================================
invoke:
	@test -n "$(FUNCTION)" || \
		(echo "ERROR: FUNCTION is required." && \
		 echo "Example: make invoke FUNCTION=osc-kiosk-range-lanes-dev PAYLOAD='{...}'" && exit 1)
	aws lambda invoke \
		--function-name $(FUNCTION) \
		--payload '$(PAYLOAD)' \
		--cli-binary-format raw-in-base64-out \
		--profile $(AWS_PROFILE) --region $(REGION) \
		/tmp/lambda-response.json
	@python3 -m json.tool /tmp/lambda-response.json

# =============================================================================
# Destroy targets — stateless/rebuildable stacks only.
# Blocked on ENV=prod. Stateful stacks (kms, secrets, aurora, s3, cognito,
# artifacts, backup) are intentionally excluded — they carry DeletionPolicy:
# Retain and cannot be cleanly cycled.
# =============================================================================
_guard-nonprod:
	@test "$(ENV)" != "prod" || \
		(echo "ERROR: destroy targets are blocked on ENV=prod" && exit 1)

destroy-lambda: _guard-nonprod
	aws cloudformation delete-stack \
		--stack-name $(STACK_LAMBDA) \
		--profile $(AWS_PROFILE) --region $(REGION)
	aws cloudformation wait stack-delete-complete \
		--stack-name $(STACK_LAMBDA) \
		--profile $(AWS_PROFILE) --region $(REGION)
	@echo "$(STACK_LAMBDA) deleted. Rebuild with: make deploy-lambda ENV=$(ENV)"

destroy-sns: _guard-nonprod
	aws cloudformation delete-stack \
		--stack-name $(STACK_SNS) \
		--profile $(AWS_PROFILE) --region $(REGION)
	aws cloudformation wait stack-delete-complete \
		--stack-name $(STACK_SNS) \
		--profile $(AWS_PROFILE) --region $(REGION)
	@echo "$(STACK_SNS) deleted. Rebuild with: make deploy-base ENV=$(ENV)"

destroy-iam: _guard-nonprod
	aws cloudformation delete-stack \
		--stack-name $(STACK_IAM_KIOSK) \
		--profile $(AWS_PROFILE) --region $(REGION)
	aws cloudformation wait stack-delete-complete \
		--stack-name $(STACK_IAM_KIOSK) \
		--profile $(AWS_PROFILE) --region $(REGION)
	@echo "$(STACK_IAM_KIOSK) deleted. Rebuild with: make deploy-base ENV=$(ENV)"


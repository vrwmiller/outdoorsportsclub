import { defineBackend } from "@aws-amplify/backend";

// All backend infrastructure is managed by CloudFormation (infra/stacks/).
// Amplify is used exclusively for Next.js hosting and CI/CD.
// Auth is provided by the CloudFormation-managed Cognito User Pool; configure
// it on the frontend via the NEXT_PUBLIC_COGNITO_* environment variables.
export const backend = defineBackend({});

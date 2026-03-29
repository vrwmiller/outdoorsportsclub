import { createServerRunner } from "@aws-amplify/adapter-nextjs";
import { getServerAmplifyConfig } from "@/config/amplifyAuth";

function getServerRunner() {
	const config = getServerAmplifyConfig();
	if (!config) {
		return null;
	}

	return createServerRunner({ config });
}

export function getRunWithAmplifyServerContext() {
	const runner = getServerRunner();
	if (!runner) {
		return null;
	}

	return runner.runWithAmplifyServerContext;
}

export function getCreateAuthRouteHandlers() {
	const runner = getServerRunner();
	if (!runner) {
		return null;
	}

	return runner.createAuthRouteHandlers;
}

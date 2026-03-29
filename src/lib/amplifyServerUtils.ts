import { createServerRunner } from "@aws-amplify/adapter-nextjs";
import { getServerAmplifyConfig } from "@/config/amplifyAuth";

export function getRunWithAmplifyServerContext() {
	const config = getServerAmplifyConfig();
	if (!config) {
		return null;
	}

	return createServerRunner({ config }).runWithAmplifyServerContext;
}

export function getCreateAuthRouteHandlers() {
	const config = getServerAmplifyConfig();
	if (!config) {
		return null;
	}

	return createServerRunner({ config }).createAuthRouteHandlers;
}

import { createServerRunner } from "@aws-amplify/adapter-nextjs";
import { getServerAmplifyConfig } from "@/config/amplifyAuth";

type ServerRunner = ReturnType<typeof createServerRunner>;

function getServerRunner(): ServerRunner | null {
	const config = getServerAmplifyConfig();
	if (!config) {
		return null;
	}

	return createServerRunner({ config });
}

export function getRunWithAmplifyServerContext():
	| ServerRunner["runWithAmplifyServerContext"]
	| null {
	const runner = getServerRunner();
	if (!runner) {
		return null;
	}

	return runner.runWithAmplifyServerContext;
}

export function getCreateAuthRouteHandlers(): ServerRunner["createAuthRouteHandlers"] | null {
	const runner = getServerRunner();
	if (!runner) {
		return null;
	}

	return runner.createAuthRouteHandlers;
}

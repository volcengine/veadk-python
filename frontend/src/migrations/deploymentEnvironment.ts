import {
  defaultModelApiBase,
  defaultModelName,
  type CloudProvider,
} from "../adk/cloudProvider";
import type { MigrationArtifact } from "../adk/migrations";

const SECRET_ENV_KEYS = new Set(["MODEL_AGENT_API_KEY"]);
const MODEL_NAME_ENV_KEYS = new Set(["MODEL_AGENT_NAME", "MODEL_NAME"]);

export function isSecretEnvironmentKey(key: string): boolean {
  return (
    SECRET_ENV_KEYS.has(key) ||
    /(?:API_KEY|ACCESS_KEY|SECRET_KEY|PRIVATE_KEY|TOKEN|SECRET|PASSWORD|PASSWD|PWD|CREDENTIAL)$/.test(
      key,
    )
  );
}

export function migrationDeploymentEnvDefaults(
  artifact: MigrationArtifact,
  cloudProvider: CloudProvider,
): Record<string, string> {
  const defaults: Record<string, string> = {};
  const declared = new Set([
    ...artifact.environment.required,
    ...artifact.environment.optional,
  ]);
  for (const key of declared) {
    if (isSecretEnvironmentKey(key)) continue;
    const value =
      key === "MODEL_AGENT_API_BASE"
        ? defaultModelApiBase(cloudProvider)
        : MODEL_NAME_ENV_KEYS.has(key)
          ? defaultModelName(cloudProvider)
          : artifact.environment.defaults[key];
    if (value?.trim()) defaults[key] = value;
  }
  return defaults;
}

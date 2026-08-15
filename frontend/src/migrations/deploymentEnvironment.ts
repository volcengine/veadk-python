import {
  defaultModelApiBase,
  defaultModelName,
  type CloudProvider,
} from "../adk/cloudProvider";
import type { MigrationArtifact } from "../adk/migrations";

const SECRET_ENV_KEYS = new Set(["MODEL_AGENT_API_KEY"]);
const MODEL_NAME_ENV_KEYS = new Set(["MODEL_AGENT_NAME", "MODEL_NAME"]);
const MIGRATION_NON_RUNTIME_ENV_KEYS = new Set([
  "VOLCENGINE_ACCESS_KEY",
  "VOLCENGINE_SECRET_KEY",
  "VOLCENGINE_SESSION_TOKEN",
  "BYTEPLUS_ACCESS_KEY",
  "BYTEPLUS_SECRET_KEY",
  "BYTEPLUS_SESSION_TOKEN",
  "VEADK_DISABLE_EXPIRE_AT",
]);

export function isMigrationRuntimeEnvironmentKey(key: string): boolean {
  return !MIGRATION_NON_RUNTIME_ENV_KEYS.has(key);
}

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
    if (
      !isMigrationRuntimeEnvironmentKey(key) ||
      isSecretEnvironmentKey(key)
    ) {
      continue;
    }
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

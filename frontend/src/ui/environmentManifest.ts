import { stringify } from "yaml";
import type { EnvironmentManifest } from "../adk/client";

export function formatEnvironmentManifest(manifest: EnvironmentManifest): string {
  return stringify(manifest, { lineWidth: 0 });
}

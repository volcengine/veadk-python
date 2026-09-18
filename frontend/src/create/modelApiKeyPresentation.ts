import type { ModelApiKeyModelPermission, ModelApiKeyOption, ModelOption } from "../adk/client";

export function modelOptionsWithPermissions(
  models: ModelOption[],
  permissions: ModelApiKeyModelPermission[] = [],
): ModelOption[] {
  const known = new Set(models.flatMap((model) => [model.id, model.name]));
  const additional: ModelOption[] = [];
  for (const permission of permissions) {
    const id = permission.modelId || permission.name;
    if (known.has(permission.name) || known.has(id)) continue;
    known.add(permission.name);
    known.add(id);
    additional.push({
      id,
      name: permission.name,
      displayName: permission.name,
      vendorName: "",
      activationState: "Unavailable",
      lifecycleStatus: permission.state === "Shutdown" ? "Shutdown" : "Running",
      available: false,
      apiKeyAllowed: true,
      unavailableReason: permission.state === "Available" ? "Unknown" : permission.state,
    });
  }
  const deniedIndex = models.findIndex((model) => model.apiKeyAllowed === false);
  const insertionIndex = deniedIndex < 0 ? models.length : deniedIndex;
  return [...models.slice(0, insertionIndex), ...additional, ...models.slice(insertionIndex)];
}

export function modelApiKeyDescription(
  key: ModelApiKeyOption,
  translate: (key: string) => string,
): string {
  const status = key.status === "Active"
    ? "modelApiKey.enabled"
    : key.status === "Restricted"
      ? "modelApiKey.disabled"
      : "modelApiKey.unknownStatus";
  const permission = key.allowAll === true
    ? "modelApiKey.allPermissions"
    : key.allowAll === false
      ? "modelApiKey.customPermissions"
      : "modelApiKey.unknownPermissions";
  return `${translate(status)} · ${translate(permission)}`;
}

export function modelApiKeyMatches(
  query: string,
  name: string,
  description: string,
): boolean {
  const normalize = (value: string) => value.normalize("NFKC").toLocaleLowerCase();
  const text = normalize(`${name} ${description}`);
  return normalize(query).trim().split(/\s+/).every((term) => text.includes(term));
}

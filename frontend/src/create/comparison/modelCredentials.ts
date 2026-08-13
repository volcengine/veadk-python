export interface ModelConnectionInput {
  modelName: string;
  modelProvider: string;
  modelApiBase: string;
  apiKey: string;
  studioApiBase: string;
}

export interface TransientModelCredentialState {
  values: Record<string, string>;
  locked: Set<string>;
  revealed: Set<string>;
}

export function invalidateTransientModelCredentials(
  current: TransientModelCredentialState,
  pathKey?: string,
): TransientModelCredentialState {
  if (pathKey === undefined) {
    return {
      values: {},
      locked: new Set(),
      revealed: new Set(),
    };
  }

  const values = { ...current.values };
  delete values[pathKey];
  const locked = new Set(current.locked);
  locked.delete(pathKey);
  const revealed = new Set(current.revealed);
  revealed.delete(pathKey);
  return { values, locked, revealed };
}

function normalizedBase(value: string): string {
  return value.trim().replace(/\/+$/, "");
}

export function validateModelConnection(
  input: ModelConnectionInput,
): { ok: true } | { ok: false; reason: string } {
  if (!input.modelName.trim()) {
    return { ok: false, reason: "Model ID 不能为空。" };
  }
  const apiBase = input.modelApiBase.trim();
  if (!apiBase) return { ok: true };

  let endpoint: URL;
  try {
    endpoint = new URL(apiBase);
  } catch {
    return { ok: false, reason: "API Base 必须是有效 URL。" };
  }
  if (endpoint.protocol !== "https:") {
    return {
      ok: false,
      reason: "调试 API Base 必须使用 HTTPS。",
    };
  }
  if (
    endpoint.username ||
    endpoint.password ||
    endpoint.search ||
    endpoint.hash
  ) {
    return {
      ok: false,
      reason: "API Base 不能包含账号、查询参数或片段，请只填写服务端点。",
    };
  }

  const isCustomBase =
    normalizedBase(apiBase) !== normalizedBase(input.studioApiBase);
  if (isCustomBase && !input.apiKey.trim()) {
    return {
      ok: false,
      reason: `自定义 API Base ${endpoint.host} 不能使用 Studio 服务端凭据，请输入临时 API Key。`,
    };
  }
  return { ok: true };
}

export function inheritTemporaryApiKey(
  baseline: Pick<ModelConnectionInput, "modelProvider" | "modelApiBase">,
  candidate: Pick<ModelConnectionInput, "modelProvider" | "modelApiBase">,
  apiKey: string,
): string {
  return baseline.modelProvider.trim() === candidate.modelProvider.trim() &&
    normalizedBase(baseline.modelApiBase) ===
      normalizedBase(candidate.modelApiBase)
    ? apiKey
    : "";
}

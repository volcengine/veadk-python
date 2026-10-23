import { CollaboratorApiError } from "./collaboratingAgents";

export type SpaceBinding = {
  space_id: string | null;
  space_name: string | null;
  region: string;
  revision: number;
};
export type RegistryItem = {
  Id: string;
  Name: string;
  Status?: string;
  Description?: string;
  ProjectName?: string;
  Alias?: string | null;
  AliasRevision?: number;
  AliasAvailable?: boolean;
};
export type RegistryPage = {
  items: RegistryItem[];
  total: number;
  page: number;
  page_size: number;
};
function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
async function json(response: Response): Promise<unknown> {
  if (!response.ok) {
    let reason: string | undefined;
    try {
      const body: unknown = await response.json();
      if (
        object(body) &&
        typeof body.detail === "string" &&
        [
          "alias_conflict",
          "revision_conflict",
          "invalid_alias",
          "alias_store_not_configured",
          "alias_store_unavailable",
        ].includes(body.detail)
      )
        reason = body.detail;
      if (
        object(body) &&
        object(body.detail) &&
        typeof body.detail.reason === "string" &&
        [
          "runtime_already_registered",
          "forbidden",
          "invalid_parameter",
          "not_found",
          "conflict",
          "rate_limited",
          "space_bound",
          "space_not_empty",
          "read_failed",
          "runtime_auth_failed",
        ].includes(body.detail.reason)
      )
        reason = body.detail.reason;
    } catch {
      /* Non-JSON errors have no safe structured reason. */
    }
    throw new CollaboratorApiError(response.status, reason);
  }
  return response.json();
}
export async function spaceBinding(response: Response): Promise<SpaceBinding> {
  const data = await json(response);
  if (
    !object(data) ||
    !(data.space_id === null || typeof data.space_id === "string") ||
    typeof data.region !== "string" ||
    !Number.isInteger(data.revision) ||
    typeof data.revision !== "number" ||
    data.revision < 0 ||
    !(data.space_name == null || typeof data.space_name === "string")
  )
    throw new CollaboratorApiError(502);
  return {
    space_id: data.space_id,
    space_name: data.space_name ?? null,
    region: data.region,
    revision: data.revision,
  };
}
export async function registryPage(response: Response): Promise<RegistryPage> {
  const data = await json(response);
  if (
    !object(data) ||
    !Array.isArray(data.items) ||
    typeof data.total !== "number" ||
    data.total < 0 ||
    typeof data.page !== "number" ||
    data.page < 1 ||
    typeof data.page_size !== "number" ||
    data.page_size < 1
  )
    throw new CollaboratorApiError(502);
  const items = data.items.map((item: unknown): RegistryItem => {
    if (
      !object(item) ||
      typeof item.Id !== "string" ||
      typeof item.Name !== "string" ||
      !(item.Status === undefined || typeof item.Status === "string") ||
      !(
        item.Description === undefined || typeof item.Description === "string"
      ) ||
      !(item.Alias == null || typeof item.Alias === "string") ||
      !(
        item.AliasRevision === undefined ||
        (typeof item.AliasRevision === "number" &&
          Number.isInteger(item.AliasRevision) &&
          item.AliasRevision >= 0)
      ) ||
      !(
        item.AliasAvailable === undefined ||
        typeof item.AliasAvailable === "boolean"
      ) ||
      !(item.ProjectName === undefined || typeof item.ProjectName === "string")
    )
      throw new CollaboratorApiError(502);
    return {
      Id: item.Id,
      Name: item.Name,
      Status: item.Status,
      Description: item.Description,
      ProjectName: item.ProjectName,
      Alias: item.Alias,
      AliasRevision: item.AliasRevision,
      AliasAvailable: item.AliasAvailable,
    };
  });
  return {
    items,
    total: data.total,
    page: data.page,
    page_size: data.page_size,
  };
}

export type CenterRegistration = {
  targetRuntimeId: string;
  spaceId: string;
  projectName: string;
} & (
  | { source: "Runtime"; runtimeId: string; networkType: "public" | "private" }
  | { source: "Standard"; importType: "url"; cardUrl: string }
  | {
      source: "Standard";
      importType: "json";
      agentCard: Record<string, unknown>;
    }
);
export async function createdAgent(response: Response): Promise<string> {
  const data = await json(response);
  if (
    !object(data) ||
    typeof data.id !== "string" ||
    !/^a-[\w-]+$/.test(data.id)
  )
    throw new CollaboratorApiError(502);
  return data.id;
}
export function parseRegistrationCard(raw: string): Record<string, unknown> {
  const data: unknown = JSON.parse(raw);
  if (
    !object(data) ||
    ["name", "url", "version"].some(
      (key) => typeof data[key] !== "string" || !data[key],
    )
  )
    throw new Error("invalid_card");
  return data;
}

export type SpaceCreation = {
  targetRuntimeId: string;
  name: string;
  projectName: string;
  intentEnabled: boolean;
};
export async function createdSpace(response: Response): Promise<string> {
  const data = await json(response);
  if (
    !object(data) ||
    typeof data.id !== "string" ||
    !/^as-[\w-]+$/.test(data.id)
  )
    throw new CollaboratorApiError(502);
  return data.id;
}

export type CenterAgentDetail = {
  id: string;
  name: string;
  status: string;
  source: string;
  defaultVersion?: string;
  projectName?: string;
  runtimeId?: string;
  networkType?: string;
  importType?: string;
  serviceAddress: string | null;
  skills: CenterAgentSkill[] | null;
  skillsTruncated: boolean;
};
export type CenterAgentSkill = {
  id: string;
  name: string;
  description: string;
  tags: string[];
  examples: string[];
};
export type RuntimeEndpoint = {
  networkType: "public" | "private";
  url: string;
};
function displayUrl(value: unknown): value is string {
  if (
    typeof value !== "string" ||
    value.length > 4096 ||
    /[\s\u0000-\u001f\u007f]/.test(value)
  )
    return false;
  try {
    const url = new URL(value);
    return (
      ["http:", "https:"].includes(url.protocol) &&
      !url.username &&
      !url.password &&
      !url.search &&
      !url.hash
    );
  } catch {
    return false;
  }
}
export async function runtimeEndpoints(
  response: Response,
  runtimeId: string,
): Promise<RuntimeEndpoint[]> {
  const data = await json(response);
  if (
    !object(data) ||
    data.runtimeId !== runtimeId ||
    !Array.isArray(data.endpoints) ||
    data.endpoints.length > 2
  )
    throw new CollaboratorApiError(502);
  const endpoints: RuntimeEndpoint[] = [];
  for (const endpoint of data.endpoints) {
    if (
      !object(endpoint) ||
      (endpoint.networkType !== "public" &&
        endpoint.networkType !== "private") ||
      !displayUrl(endpoint.url) ||
      endpoints.some((item) => item.networkType === endpoint.networkType)
    )
      throw new CollaboratorApiError(502);
    endpoints.push({ networkType: endpoint.networkType, url: endpoint.url });
  }
  return endpoints;
}
export async function centerAgentDetail(
  response: Response,
  id: string,
): Promise<CenterAgentDetail> {
  const data = await json(response);
  if (
    !object(data) ||
    data.id !== id ||
    !["Runtime", "Standard"].includes(String(data.source)) ||
    ["name", "status", "source"].some((key) => typeof data[key] !== "string")
  )
    throw new CollaboratorApiError(502);
  const detail: CenterAgentDetail = {
    id,
    name: String(data.name),
    status: String(data.status),
    source: String(data.source),
    serviceAddress: null,
    skills: null,
    skillsTruncated: false,
  };
  for (const key of [
    "defaultVersion",
    "projectName",
    "runtimeId",
    "networkType",
    "importType",
  ] as const) {
    if (data[key] !== undefined && typeof data[key] !== "string")
      throw new CollaboratorApiError(502);
    if (typeof data[key] === "string") detail[key] = data[key];
  }
  if (data.serviceAddress != null) {
    if (!displayUrl(data.serviceAddress)) throw new CollaboratorApiError(502);
    detail.serviceAddress = data.serviceAddress;
  }
  if (data.skills != null) {
    if (!Array.isArray(data.skills) || data.skills.length > 100)
      throw new CollaboratorApiError(502);
    detail.skills = data.skills.map((skill: unknown) => {
      if (!object(skill)) throw new CollaboratorApiError(502);
      for (const [key, limit] of [
        ["id", 256],
        ["name", 512],
        ["description", 4096],
      ] as const) {
        if (typeof skill[key] !== "string" || skill[key].length > limit)
          throw new CollaboratorApiError(502);
      }
      for (const [key, limit] of [
        ["tags", 128],
        ["examples", 1024],
      ] as const) {
        const values = skill[key];
        if (
          !Array.isArray(values) ||
          values.length > 20 ||
          values.some(
            (value) => typeof value !== "string" || value.length > limit,
          )
        )
          throw new CollaboratorApiError(502);
      }
      return {
        id: String(skill.id),
        name: String(skill.name),
        description: String(skill.description),
        tags: skill.tags as string[],
        examples: skill.examples as string[],
      };
    });
  }
  if (data.skillsTruncated !== undefined) {
    if (typeof data.skillsTruncated !== "boolean")
      throw new CollaboratorApiError(502);
    detail.skillsTruncated = data.skillsTruncated;
  }
  return detail;
}
export async function deletedResource(response: Response): Promise<void> {
  const data = await json(response);
  if (!object(data) || data.deleted !== true)
    throw new CollaboratorApiError(502);
}

export type AliasRecord = { alias: string | null; revision: number };
export async function aliasRecord(response: Response): Promise<AliasRecord> {
  const data = await json(response);
  if (
    !object(data) ||
    !(data.alias === null || typeof data.alias === "string") ||
    typeof data.revision !== "number" ||
    !Number.isInteger(data.revision) ||
    data.revision < 1
  )
    throw new CollaboratorApiError(502);
  return { alias: data.alias, revision: data.revision };
}

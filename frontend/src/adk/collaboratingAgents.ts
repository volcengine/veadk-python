export interface CollaboratorConfig {
  name: string;
  description: string;
  card_url: string;
  enabled: boolean;
  auth_type: "none" | "bearer" | "api_key";
  secret: string;
  header_name: string;
}
export interface Collaborator extends Omit<CollaboratorConfig, "secret"> {
  credential_configured: boolean;
  id: string;
  mpa_id: string;
  revision: number;
  check: {
    status: "not_checked" | "verified" | "failed";
    reason?: string;
    checked_at?: string;
    card?: {
      name: string;
      description: string;
      endpoint: string;
      protocol_version: string;
      transport: string;
      skills: { id: string; name: string; description: string }[];
    };
  };
}
export class CollaboratorApiError extends Error {
  constructor(public status: number) {
    super(`Collaborator request failed (${status})`);
  }
}
export type CollaboratorRequest = (
  suffix: string,
  init?: RequestInit,
) => Promise<Response>;
export async function collaboratorResponse(
  response: Response,
): Promise<Collaborator | { items: Collaborator[] } | null> {
  if (!response.ok) throw new CollaboratorApiError(response.status);
  if (response.status === 204) return null;
  const data: unknown = await response.json();
  if (isCollaborator(data)) return data;
  if (
    data &&
    typeof data === "object" &&
    "items" in data &&
    Array.isArray(data.items) &&
    data.items.every(isCollaborator)
  )
    return { items: data.items };
  throw new CollaboratorApiError(502);
}
function isCollaborator(value: unknown): value is Collaborator {
  if (!value || typeof value !== "object") return false;
  const item = value as Partial<Collaborator>;
  return (
    typeof item.id === "string" &&
    typeof item.mpa_id === "string" &&
    typeof item.name === "string" &&
    typeof item.description === "string" &&
    typeof item.card_url === "string" &&
    typeof item.enabled === "boolean" &&
    Number.isInteger(item.revision) &&
    (item.revision ?? 0) > 0 &&
    ["none", "bearer", "api_key"].includes(item.auth_type ?? "") &&
    typeof item.credential_configured === "boolean" &&
    typeof item.header_name === "string" &&
    !!item.check &&
    ["not_checked", "verified", "failed"].includes(item.check.status) &&
    (item.check.reason === undefined ||
      typeof item.check.reason === "string") &&
    (item.check.card === undefined ||
      (typeof item.check.card.endpoint === "string" &&
        Array.isArray(item.check.card.skills) &&
        item.check.card.skills.every(
          (skill) =>
            typeof skill?.name === "string" && typeof skill.id === "string",
        )))
  );
}

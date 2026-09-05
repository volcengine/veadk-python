import { studioFetch } from "../adk/client";
import type { ArtifactMetadataUpdate } from "./ArtifactEditDialog";
import { workspaceToolsT } from "./workspaceToolsI18n";
import type {
  ArtifactIngestCandidate,
  ArtifactLibraryItem,
} from "./artifactLibraryModel";

interface ArtifactListPayload {
  items?: unknown[];
}

function messageFromPayload(payload: unknown, fallback: string): string {
  if (payload && typeof payload === "object" && "detail" in payload) {
    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === "string" && detail.trim()) return detail;
  }
  return fallback;
}

async function requireOk(response: Response, fallback: string): Promise<Response> {
  if (response.ok) return response;
  let payload: unknown;
  try {
    payload = await response.json();
  } catch {
    payload = undefined;
  }
  throw new Error(messageFromPayload(payload, workspaceToolsT("artifactLibrary.api.withStatus", {
    message: fallback,
    status: response.status,
  })));
}

function timestamp(value: unknown): number {
  if (typeof value === "number") return value;
  if (typeof value !== "string") return 0;
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) ? parsed : 0;
}

function itemFromApi(value: unknown): ArtifactLibraryItem {
  const item = value as ArtifactLibraryItem & {
    createdAt?: unknown;
    updatedAt?: unknown;
    sessionUpdatedAt?: unknown;
  };
  return {
    ...item,
    createdAt: timestamp(item.createdAt),
    updatedAt: timestamp(item.updatedAt),
    sessionUpdatedAt: timestamp(item.sessionUpdatedAt),
  } as ArtifactLibraryItem;
}

async function itemsFromResponse(response: Response): Promise<ArtifactLibraryItem[]> {
  const payload = await response.json() as ArtifactListPayload;
  return Array.isArray(payload.items) ? payload.items.map(itemFromApi) : [];
}

export async function listStoredArtifacts(): Promise<ArtifactLibraryItem[]> {
  const response = await requireOk(
    await studioFetch("/web/artifacts"),
    workspaceToolsT("artifactLibrary.api.listFailed"),
  );
  return itemsFromResponse(response);
}

export async function syncStoredArtifacts(
  candidates: readonly ArtifactIngestCandidate[],
): Promise<ArtifactLibraryItem[]> {
  if (candidates.length === 0) return listStoredArtifacts();
  const response = await requireOk(
    await studioFetch("/web/artifacts/sync", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ candidates }),
    }, 240_000),
    workspaceToolsT("artifactLibrary.api.syncFailed"),
  );
  return itemsFromResponse(response);
}

export async function updateStoredArtifact(
  artifact: ArtifactLibraryItem,
  update: ArtifactMetadataUpdate,
): Promise<ArtifactLibraryItem> {
  const response = await requireOk(
    await studioFetch(`/web/artifacts/${encodeURIComponent(artifact.id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    }),
    workspaceToolsT("artifactLibrary.api.updateFailed"),
  );
  return itemFromApi(await response.json());
}

export async function deleteStoredArtifact(
  artifact: ArtifactLibraryItem,
): Promise<void> {
  await requireOk(
    await studioFetch(`/web/artifacts/${encodeURIComponent(artifact.id)}`, {
      method: "DELETE",
    }),
    workspaceToolsT("artifactLibrary.api.deleteFailed"),
  );
}

export async function downloadStoredArtifact(
  artifact: ArtifactLibraryItem,
): Promise<void> {
  const response = await requireOk(
    await studioFetch(
      `/web/artifacts/${encodeURIComponent(artifact.id)}/content?download=true`,
      {},
      240_000,
    ),
    workspaceToolsT("artifactLibrary.api.downloadFailed"),
  );
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = artifact.name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 0);
}

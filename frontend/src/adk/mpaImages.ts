export type ImageComponent = "runtime" | "worker";
export type ImageOperation = {
  target: string;
  phase: "submitting" | "submitted" | "uncertain" | "configured" | "rejected";
};
export type ImageDetail = {
  component: ImageComponent;
  resourceId: string;
  repository: string;
  currentImage: string;
  status: string;
  revision: string;
  canUpdate: boolean;
  reason: string;
  operation: ImageOperation | null;
};
export type ImageVersions = {
  repository: string;
  tags: string[];
  nextCursor: string;
};
export type ImageSelection = { image: string; digest: string };
export type LatestImagePreview = ImageSelection & {
  component: ImageComponent;
  revision: string;
  requestedImage: string;
};
export class ImageApiError extends Error {
  constructor(
    public reason: string,
    public status = 502,
  ) {
    super(reason);
  }
}
function object(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}
async function json(response: Response): Promise<unknown> {
  let data: unknown;
  try {
    data = await response.json();
  } catch {
    throw new ImageApiError("invalid_response", response.status);
  }
  if (!response.ok) {
    const reason =
      object(data) &&
      object(data.detail) &&
      typeof data.detail.reason === "string"
        ? data.detail.reason
        : [401, 403].includes(response.status)
          ? "forbidden"
          : "read_failed";
    throw new ImageApiError(reason, response.status);
  }
  return data;
}
export async function imageDetail(response: Response): Promise<ImageDetail> {
  const data = await json(response);
  if (
    !object(data) ||
    !["runtime", "worker"].includes(String(data.component)) ||
    [
      "resourceId",
      "repository",
      "currentImage",
      "status",
      "revision",
      "reason",
    ].some((key) => typeof data[key] !== "string") ||
    typeof data.canUpdate !== "boolean" ||
    !(
      data.operation === null ||
      (object(data.operation) &&
        typeof data.operation.target === "string" &&
        [
          "submitting",
          "submitted",
          "uncertain",
          "configured",
          "rejected",
        ].includes(String(data.operation.phase)))
    )
  )
    throw new ImageApiError("invalid_response");
  return data as ImageDetail;
}
export async function imageVersions(
  response: Response,
): Promise<ImageVersions> {
  const data = await json(response);
  if (
    !object(data) ||
    typeof data.repository !== "string" ||
    !Array.isArray(data.tags) ||
    data.tags.some(
      (tag) => typeof tag !== "string" || !/^[\w][\w.-]{0,127}$/.test(tag),
    ) ||
    typeof data.nextCursor !== "string"
  )
    throw new ImageApiError("invalid_response");
  return data as ImageVersions;
}

export type ImageUpdateSource =
  | { image: string; tag?: never }
  | { tag: string; image?: never; selection?: ImageSelection };

export async function latestImagePreview(
  response: Response,
): Promise<LatestImagePreview> {
  const data = await json(response);
  if (
    !object(data) ||
    !["runtime", "worker"].includes(String(data.component)) ||
    typeof data.revision !== "string" ||
    typeof data.requestedImage !== "string" ||
    !data.requestedImage.endsWith(":latest") ||
    typeof data.image !== "string" ||
    !validImageReference(data.image) ||
    data.image === data.requestedImage ||
    data.image.slice(0, data.image.lastIndexOf(":")) !==
      data.requestedImage.slice(0, -7) ||
    typeof data.digest !== "string" ||
    !/^sha256:[a-f0-9]{64}$/.test(data.digest)
  )
    throw new ImageApiError("invalid_response");
  return data as LatestImagePreview;
}
const imageHost = "[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?";
const imagePart = "[a-z0-9]+(?:(?:[._]|__|[-]+)[a-z0-9]+)*";
const imageReference = new RegExp(
  `^(${imageHost}(?:\\.${imageHost})*)(?::([0-9]{1,5}))?/${imagePart}(?:/${imagePart})*:[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$`,
);
export function validImageReference(value: string): boolean {
  if (value.length > 2048) return false;
  const match = imageReference.exec(value);
  if (!match || match[0].length !== value.length) return false;
  const [, host, port] = match;
  return (
    (!port || (Number(port) >= 1 && Number(port) <= 65535)) &&
    (host.includes(".") || Boolean(port) || host === "localhost")
  );
}

export const MAX_DOCKERFILE_BYTES = 128 * 1024;

export interface DockerfileUploadResult {
  content: string;
  error: string;
}

type DockerfileTranslation = (key: string) => string;

const DEFAULT_MESSAGES = {
  baseImageRequired: "请填写基础镜像。",
  duplicateFrom: "基础镜像已固定在第一行，请删除 Dockerfile 正文中的 FROM 指令。",
  tooLarge: "Dockerfile 不能超过 128 KiB。",
  empty: "Dockerfile 内容不能为空。",
  missingFrom: "Dockerfile 缺少 FROM 指令。",
} as const;

function validationMessage(
  key: keyof typeof DEFAULT_MESSAGES,
  t?: DockerfileTranslation,
): string {
  return t?.(`environmentCenter.dockerfileValidation.${key}`) ?? DEFAULT_MESSAGES[key];
}

export function normalizeDockerfileContent(content: string): string {
  return content.replace(/^\uFEFF/, "").replace(/\r\n?/g, "\n");
}

export function dockerfileByteSize(content: string): number {
  return new TextEncoder().encode(content).byteLength;
}

export function dockerfileBaseImage(content: string, fallback = "ubuntu:22.04"): string {
  const from = normalizeDockerfileContent(content).match(
    /^\s*FROM(?:\s+--platform=\S+)?\s+(\S+)/im,
  );
  return from?.[1] ?? fallback;
}

export function dockerfileBody(content: string): string {
  const lines = normalizeDockerfileContent(content).split("\n");
  const fromLineIndex = lines.findIndex((line) => /^\s*FROM(?:\s|$)/i.test(line));
  return (fromLineIndex >= 0 ? lines.slice(fromLineIndex + 1) : lines)
    .join("\n")
    .replace(/^\n+/, "");
}

export function composeDockerfile(baseImage: string, body: string): string {
  const from = `FROM ${baseImage.trim()}`;
  const normalizedBody = normalizeDockerfileContent(body).replace(/^\n+/, "");
  return normalizedBody ? `${from}\n${normalizedBody}` : from;
}

export function validateDockerfileBody(
  body: string,
  baseImage: string,
  t?: DockerfileTranslation,
): string {
  if (!baseImage.trim()) return validationMessage("baseImageRequired", t);
  if (/^\s*FROM(?:\s|$)/im.test(body)) {
    return validationMessage("duplicateFrom", t);
  }
  return validateDockerfileUpload(composeDockerfile(baseImage, body), undefined, t);
}

export function validateDockerfileUpload(
  content: string,
  byteSize = dockerfileByteSize(content),
  t?: DockerfileTranslation,
): string {
  if (byteSize > MAX_DOCKERFILE_BYTES) {
    return validationMessage("tooLarge", t);
  }
  if (!content.trim()) {
    return validationMessage("empty", t);
  }
  if (!/^\s*FROM\s+\S+/im.test(content)) {
    return validationMessage("missingFrom", t);
  }
  return "";
}

export async function readDockerfileUpload(
  file: File,
  t?: DockerfileTranslation,
): Promise<DockerfileUploadResult> {
  if (file.size > MAX_DOCKERFILE_BYTES) {
    return {
      content: "",
      error: validationMessage("tooLarge", t),
    };
  }
  const content = normalizeDockerfileContent(await file.text());
  return {
    content,
    error: validateDockerfileUpload(content, file.size, t),
  };
}

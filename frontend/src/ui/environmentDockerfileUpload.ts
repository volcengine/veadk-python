export const MAX_DOCKERFILE_BYTES = 128 * 1024;

export interface DockerfileUploadResult {
  content: string;
  error: string;
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

export function validateDockerfileBody(body: string, baseImage: string): string {
  if (!baseImage.trim()) return "请填写基础镜像。";
  if (/^\s*FROM(?:\s|$)/im.test(body)) {
    return "基础镜像已固定在第一行，请删除 Dockerfile 正文中的 FROM 指令。";
  }
  return validateDockerfileUpload(composeDockerfile(baseImage, body));
}

export function validateDockerfileUpload(
  content: string,
  byteSize = dockerfileByteSize(content),
): string {
  if (byteSize > MAX_DOCKERFILE_BYTES) {
    return "Dockerfile 不能超过 128 KiB。";
  }
  if (!content.trim()) {
    return "Dockerfile 内容不能为空。";
  }
  if (!/^\s*FROM\s+\S+/im.test(content)) {
    return "Dockerfile 缺少 FROM 指令。";
  }
  return "";
}

export async function readDockerfileUpload(file: File): Promise<DockerfileUploadResult> {
  if (file.size > MAX_DOCKERFILE_BYTES) {
    return {
      content: "",
      error: "Dockerfile 不能超过 128 KiB。",
    };
  }
  const content = normalizeDockerfileContent(await file.text());
  return {
    content,
    error: validateDockerfileUpload(content, file.size),
  };
}

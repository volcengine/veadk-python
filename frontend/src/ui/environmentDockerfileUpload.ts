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

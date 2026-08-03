export function formatRequestError(
  cause: unknown,
  action: string,
  request?: string,
): string {
  const detail = cause instanceof Error
    ? `${cause.name}: ${cause.message}`
    : String(cause || "未知错误");
  return [
    `${action}失败`,
    `详细信息：${detail}`,
    request ? `请求：${request}` : "",
  ].filter(Boolean).join("\n");
}

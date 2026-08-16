import {
  DEFAULT_REQUEST_TIMEOUT_MS,
  TRANSFER_REQUEST_TIMEOUT_MS,
  requestSignal,
} from "./timeout";
import { withLocalUser } from "./identity";
export type { CloudProvider } from "./cloudProvider";

export interface KnowledgeBaseItem {
  id: string;
  name: string;
  description: string;
  providerType: string;
  providerKnowledgeId: string;
  projectName: string;
  region: string;
  status: string;
  createdAt: string;
  updatedAt: string;
  ownerId: string;
  ownerLabel: string;
  canManage: boolean;
}

export interface KnowledgeBasePage {
  items: KnowledgeBaseItem[];
  nextToken: string;
}

export interface KnowledgeRegionFailure {
  region: string;
  error: Error;
}

export interface KnowledgeBaseRegionPage {
  items: KnowledgeBaseItem[];
  nextTokens: Record<string, string>;
  failures: KnowledgeRegionFailure[];
}

export const KNOWLEDGE_PROVIDER_ASSOCIATION_INVALID =
  "KNOWLEDGE_PROVIDER_ASSOCIATION_INVALID";

export interface KnowledgeDocumentItem {
  id: string;
  name: string;
  type: string;
  sizeBytes: number;
  status: string;
  url: string;
  tosPath: string;
  metadata: Record<string, unknown>;
  createdAt: string;
  updatedAt: string;
}

export interface KnowledgeDocumentPage {
  items: KnowledgeDocumentItem[];
  offset: number;
  limit: number;
  hasMore: boolean;
}

export interface KnowledgeDocumentPreviewChunk {
  id: string;
  title: string;
  content: string;
  attachmentUrl: string;
  attachmentType: string;
  attachment: unknown;
  tableFields: unknown;
}

export interface KnowledgeDocumentPreviewPage {
  document: KnowledgeDocumentItem;
  chunks: KnowledgeDocumentPreviewChunk[];
  offset: number;
  limit: number;
  hasMore: boolean;
}

export interface CreateKnowledgeBaseInput {
  name: string;
  description?: string;
}

export interface CreateKnowledgeDocumentInput {
  sourceType: "url" | "tos";
  name?: string;
  documentType?: string;
  url?: string;
  tosPath?: string;
  metadata?: Record<string, unknown>;
}

export interface UploadKnowledgeDocumentInput {
  file: File;
  name?: string;
  documentType?: string;
  metadata?: Record<string, unknown>;
}

export interface KnowledgeErrorPayload {
  detail?: unknown;
  message?: unknown;
  errorCode?: unknown;
  requestId?: unknown;
  request_id?: unknown;
  diagnostics?: unknown;
}

interface KnowledgeErrorInfo {
  message: string;
  errorCode: string;
  requestId: string;
  diagnostics: unknown;
  detail: unknown;
  payload: unknown;
}

export interface KnowledgeRequestErrorOptions {
  errorCode?: string;
  requestId?: string;
  diagnostics?: unknown;
  detail?: unknown;
  payload?: unknown;
  rawBody?: string;
}

export class KnowledgeRequestError extends Error {
  readonly status: number;
  readonly errorCode: string;
  readonly requestId: string;
  readonly diagnostics: unknown;
  readonly detail: unknown;
  readonly payload: unknown;
  readonly rawBody: string;

  constructor(
    message: string,
    status: number,
    options: KnowledgeRequestErrorOptions | string = {},
  ) {
    super(message);
    this.name = "KnowledgeRequestError";
    this.status = status;
    const normalized = typeof options === "string"
      ? { errorCode: options }
      : options;
    this.errorCode = normalized.errorCode || "";
    this.requestId = normalized.requestId || "";
    this.diagnostics = normalized.diagnostics;
    this.detail = normalized.detail;
    this.payload = normalized.payload;
    this.rawBody = normalized.rawBody || "";
  }
}

export class KnowledgeRegionAggregateError extends Error {
  readonly failures: KnowledgeRegionFailure[];

  constructor(failures: KnowledgeRegionFailure[]) {
    super(failures.map(({ region, error }) => (
      `${region}: ${error.message || "读取知识库失败"}`
    )).join("\n"));
    this.name = "KnowledgeRegionAggregateError";
    this.failures = failures;
  }
}

const SENSITIVE_DIAGNOSTIC_KEYS = new Set([
  "ak",
  "apikey",
  "sk",
  "accesskey",
  "accesskeyid",
  "authorization",
  "authkey",
  "clientsecret",
  "cookie",
  "credential",
  "credentials",
  "password",
  "passwd",
  "privatekey",
  "secret",
  "secretaccesskey",
  "secretkey",
  "securitytoken",
  "sessiontoken",
  "setcookie",
  "token",
]);
const MAX_DIAGNOSTIC_DEPTH = 6;
const MAX_DIAGNOSTIC_ITEMS = 50;
const MAX_DIAGNOSTIC_TEXT = 4_000;

function normalizedDiagnosticKey(value: string): string {
  return value.toLowerCase().replace(/[^a-z0-9]/g, "");
}

function isSensitiveDiagnosticKey(value: string): boolean {
  const normalized = normalizedDiagnosticKey(value);
  return SENSITIVE_DIAGNOSTIC_KEYS.has(normalized)
    || normalized.endsWith("password")
    || normalized.endsWith("secret")
    || normalized.endsWith("token")
    || normalized.endsWith("credential");
}

function looksLikeHtml(value: string): boolean {
  return /<\s*(?:!doctype|html|head|body|script|style)\b/i.test(value);
}

function redactSensitiveText(value: string): string {
  if (looksLikeHtml(value)) return "[HTML 内容已隐藏]";
  return value
    .replace(/\bBearer\s+[^\s,;]+/gi, "Bearer [已脱敏]")
    .replace(/\b(?:set-)?cookie\s*:\s*[^\r\n]*/gi, "cookie: [已脱敏]")
    .replace(/\bAKLT[A-Za-z0-9_-]{6,}\b/g, "[已脱敏]")
    .replace(
      /((?:access[_-]?key(?:[_-]?id)?|secret(?:[_-]?(?:access)?[_-]?key)?|session[_-]?token|security[_-]?token|client[_-]?secret|api[_-]?key|authorization|cookie|[a-z0-9_-]*(?:password|secret|token)|credential|ak|sk)\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;&]+)/gi,
      "$1[已脱敏]",
    )
    .replace(
      /([?&](?:access[_-]?key|api[_-]?key|client[_-]?secret|security[_-]?token|session[_-]?token|secret|token|password|authorization|cookie|credential)=)[^&#\s]+/gi,
      "$1[已脱敏]",
    );
}

function sanitizeDiagnosticValue(
  value: unknown,
  depth = 0,
  seen = new WeakSet<object>(),
): unknown {
  if (value === null || typeof value === "number" || typeof value === "boolean") {
    return value;
  }
  if (typeof value === "string") {
    return redactSensitiveText(value).slice(0, MAX_DIAGNOSTIC_TEXT);
  }
  if (typeof value !== "object") return undefined;
  if (depth >= MAX_DIAGNOSTIC_DEPTH) return "[内容过深，已截断]";
  if (seen.has(value)) return "[循环引用]";
  seen.add(value);
  if (Array.isArray(value)) {
    return value.slice(0, MAX_DIAGNOSTIC_ITEMS).map((item) => (
      sanitizeDiagnosticValue(item, depth + 1, seen)
    ));
  }
  const output: Record<string, unknown> = {};
  Object.entries(value as Record<string, unknown>)
    .slice(0, MAX_DIAGNOSTIC_ITEMS)
    .forEach(([key, item]) => {
      output[key] = isSensitiveDiagnosticKey(key)
        ? "[已脱敏]"
        : sanitizeDiagnosticValue(item, depth + 1, seen);
    });
  return output;
}

function safeDiagnosticText(value: unknown): string {
  if (value === undefined) return "";
  const sanitized = sanitizeDiagnosticValue(value);
  if (typeof sanitized === "string") return sanitized;
  if (sanitized === undefined) return "";
  try {
    return JSON.stringify(sanitized).slice(0, MAX_DIAGNOSTIC_TEXT);
  } catch {
    return "[诊断信息无法显示]";
  }
}

export function formatKnowledgeError(reason: unknown, fallback: string): string {
  if (reason instanceof KnowledgeRegionAggregateError) {
    return reason.failures.map(({ region, error }) => (
      `${region}\n${formatKnowledgeError(error, fallback)}`
    )).join("\n\n");
  }
  if (!(reason instanceof KnowledgeRequestError)) {
    const message = reason instanceof Error ? redactSensitiveText(reason.message) : "";
    return message || fallback;
  }
  const message = redactSensitiveText(reason.message) || fallback;
  const context = [
    Number.isFinite(reason.status) ? `状态码：${reason.status}` : "",
    reason.errorCode ? `错误码：${redactSensitiveText(reason.errorCode)}` : "",
    reason.requestId ? `请求 ID：${redactSensitiveText(reason.requestId)}` : "",
  ].filter(Boolean).join(" · ");
  const diagnostics = safeDiagnosticText(reason.diagnostics);
  const detail = safeDiagnosticText(reason.detail);
  return [
    message,
    context,
    diagnostics ? `诊断：${diagnostics}` : "",
    detail && detail !== message ? `详情：${detail}` : "",
  ].filter(Boolean).join("\n");
}

function firstString(...values: unknown[]): string {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return "";
}

function validationDetailMessage(detail: unknown): string {
  if (!Array.isArray(detail)) return "";
  return detail.map((value) => {
    const issue = asRecord(value);
    const message = firstString(issue.msg, issue.message);
    if (!message) return "";
    const location = Array.isArray(issue.loc)
      ? issue.loc
        .filter((part) => typeof part === "string" || typeof part === "number")
        .map(String)
        .join(".")
      : "";
    return location ? `${location}: ${message}` : message;
  }).filter(Boolean).join("; ");
}

function errorInfo(payload: unknown, allowRootString = true): KnowledgeErrorInfo {
  const root = asRecord(payload) as KnowledgeErrorPayload;
  const detail = Object.prototype.hasOwnProperty.call(root, "detail")
    ? root.detail
    : typeof payload === "string"
      ? payload
      : undefined;
  const detailRecord = asRecord(detail);
  const message = typeof detail === "string"
    ? (allowRootString ? detail.trim() : "")
    : firstString(
      detailRecord.message,
      root.message,
      validationDetailMessage(detail),
    );
  return {
    message,
    errorCode: firstString(detailRecord.errorCode, root.errorCode),
    requestId: firstString(
      detailRecord.requestId,
      detailRecord.request_id,
      detailRecord.RequestId,
      root.requestId,
      root.request_id,
    ),
    diagnostics: detailRecord.diagnostics ?? root.diagnostics,
    detail,
    payload,
  };
}

function asRecord(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

function asNumber(value: unknown, fallback: number): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function normalizeKnowledgeBase(value: unknown): KnowledgeBaseItem {
  const item = asRecord(value);
  return {
    id: asString(item.id),
    name: asString(item.name),
    description: asString(item.description),
    providerType: asString(item.providerType),
    providerKnowledgeId: asString(item.providerKnowledgeId),
    projectName: asString(item.projectName),
    region: asString(item.region),
    status: asString(item.status),
    createdAt: asString(item.createdAt),
    updatedAt: asString(item.updatedAt),
    ownerId: asString(item.ownerId),
    ownerLabel: asString(item.ownerLabel),
    canManage: item.canManage === true,
  };
}

function normalizeKnowledgeDocument(value: unknown): KnowledgeDocumentItem {
  const item = asRecord(value);
  return {
    id: asString(item.id),
    name: asString(item.name),
    type: asString(item.type),
    sizeBytes: asNumber(item.sizeBytes, 0),
    status: asString(item.status),
    url: asString(item.url),
    tosPath: asString(item.tosPath),
    metadata: asRecord(item.metadata),
    createdAt: asString(item.createdAt),
    updatedAt: asString(item.updatedAt),
  };
}

function normalizeKnowledgePreviewChunk(value: unknown): KnowledgeDocumentPreviewChunk {
  const item = asRecord(value);
  const attachment = item.attachment;
  const attachmentRecord = asRecord(attachment);
  return {
    id: asString(item.id),
    title: asString(item.title),
    content: asString(item.content),
    attachmentUrl: asString(item.attachmentUrl)
      || asString(attachmentRecord.url)
      || asString(attachmentRecord.previewUrl),
    attachmentType: asString(item.attachmentType)
      || asString(attachmentRecord.type)
      || asString(attachmentRecord.mimeType),
    attachment,
    tableFields: item.tableFields,
  };
}

async function knowledgeFetch<T>(
  path: string,
  init: RequestInit = {},
  timeoutMs = DEFAULT_REQUEST_TIMEOUT_MS,
): Promise<T> {
  const headers = withLocalUser(init.headers);
  headers.set("accept", "application/json");
  if (init.body && !(init.body instanceof FormData)) {
    headers.set("content-type", "application/json");
  }
  const response = await fetch(path, {
    ...init,
    headers,
    signal: requestSignal(init.signal, timeoutMs),
  });
  if (response.ok) {
    if (response.status === 204) return undefined as T;
    return response.json() as Promise<T>;
  }
  const rawBody = await response.text();
  let payload: unknown = rawBody;
  let parsedJson = false;
  if (rawBody) {
    try {
      payload = JSON.parse(rawBody) as unknown;
      parsedJson = true;
    } catch {
      // Preserve the raw response body on the error without stringifying it.
    }
  }
  const contentType = response.headers.get("content-type")?.toLowerCase() || "";
  const info = errorInfo(
    payload,
    parsedJson || contentType.startsWith("text/plain"),
  );
  const fallback = response.status === 401
    ? "请先登录后再访问知识库"
    : response.status === 403
      ? "你没有权限操作这个知识库"
      : response.status === 404
        ? "知识库或知识内容不存在"
        : response.status === 409
          ? "知识库当前状态不允许执行此操作"
          : `知识库请求失败 (${response.status})`;
  throw new KnowledgeRequestError(info.message || fallback, response.status, {
    errorCode: info.errorCode,
    requestId: info.requestId,
    diagnostics: info.diagnostics,
    detail: info.detail,
    payload: info.payload,
    rawBody,
  });
}

function regionQuery(region: string): string {
  const params = new URLSearchParams();
  if (region.trim()) params.set("region", region.trim());
  const query = params.toString();
  return query ? `?${query}` : "";
}

export async function listKnowledgeBases(options: {
  region: string;
  projectName?: string;
  nextToken?: string;
  pageSize?: number;
  signal?: AbortSignal;
}): Promise<KnowledgeBasePage> {
  const params = new URLSearchParams({
    region: options.region,
    pageSize: String(options.pageSize ?? 30),
  });
  if (options.projectName?.trim()) params.set("projectName", options.projectName.trim());
  if (options.nextToken) params.set("nextToken", options.nextToken);
  const response = await knowledgeFetch<unknown>(
    `/web/knowledge-bases?${params.toString()}`,
    { signal: options.signal },
  );
  const page = asRecord(response);
  return {
    items: Array.isArray(page.items) ? page.items.map(normalizeKnowledgeBase) : [],
    nextToken: asString(page.nextToken),
  };
}

function knowledgeBaseKey(item: KnowledgeBaseItem): string {
  return `${item.region}\u0000${item.id}`;
}

export async function listKnowledgeBasesAcrossRegions(options: {
  regions: readonly string[];
  projectName?: string;
  nextTokens?: Readonly<Record<string, string>>;
  pageSize?: number;
  signal?: AbortSignal;
}): Promise<KnowledgeBaseRegionPage> {
  const regions = [...new Set(options.regions.map((region) => region.trim()).filter(Boolean))];
  const requestedRegions = options.nextTokens
    ? regions.filter((region) => Boolean(options.nextTokens?.[region]))
    : regions;
  if (requestedRegions.length === 0) {
    return { items: [], nextTokens: {}, failures: [] };
  }
  const settled = await Promise.allSettled(requestedRegions.map(async (region) => ({
    region,
    page: await listKnowledgeBases({
      region,
      projectName: options.projectName,
      nextToken: options.nextTokens?.[region],
      pageSize: options.pageSize,
      signal: options.signal,
    }),
  })));
  if (options.signal?.aborted) throw new DOMException("Aborted", "AbortError");

  const failures: KnowledgeRegionFailure[] = [];
  const nextTokens: Record<string, string> = {};
  const merged = new Map<string, KnowledgeBaseItem>();
  settled.forEach((result, index) => {
    const region = requestedRegions[index];
    if (result.status === "rejected") {
      const retryToken = options.nextTokens?.[region];
      if (retryToken) nextTokens[region] = retryToken;
      failures.push({
        region,
        error: result.reason instanceof Error
          ? result.reason
          : new Error("读取知识库失败"),
      });
      return;
    }
    if (result.value.page.nextToken) {
      nextTokens[region] = result.value.page.nextToken;
    }
    result.value.page.items.forEach((item) => {
      const normalized = item.region ? item : { ...item, region };
      merged.set(knowledgeBaseKey(normalized), normalized);
    });
  });
  if (failures.length === requestedRegions.length) {
    throw new KnowledgeRegionAggregateError(failures);
  }
  return { items: [...merged.values()], nextTokens, failures };
}

export function getKnowledgeBase(
  knowledgeId: string,
  region: string,
): Promise<KnowledgeBaseItem> {
  return knowledgeFetch(
    `/web/knowledge-bases/${encodeURIComponent(knowledgeId)}${regionQuery(region)}`,
  );
}

export function createKnowledgeBase(
  input: CreateKnowledgeBaseInput,
): Promise<KnowledgeBaseItem> {
  return knowledgeFetch<unknown>("/web/knowledge-bases", {
    method: "POST",
    body: JSON.stringify(input),
  }, TRANSFER_REQUEST_TIMEOUT_MS).then(normalizeKnowledgeBase);
}

export function updateKnowledgeBase(
  knowledgeId: string,
  region: string,
  input: { description: string },
): Promise<KnowledgeBaseItem> {
  return knowledgeFetch<unknown>(
    `/web/knowledge-bases/${encodeURIComponent(knowledgeId)}${regionQuery(region)}`,
    { method: "PATCH", body: JSON.stringify(input) },
  ).then(normalizeKnowledgeBase);
}

export function deleteKnowledgeBase(
  knowledgeId: string,
  region: string,
): Promise<void> {
  return knowledgeFetch(
    `/web/knowledge-bases/${encodeURIComponent(knowledgeId)}${regionQuery(region)}`,
    { method: "DELETE" },
    TRANSFER_REQUEST_TIMEOUT_MS,
  );
}

export async function listKnowledgeDocuments(
  knowledgeId: string,
  options: { region: string; offset?: number; limit?: number; documentType?: string; signal?: AbortSignal },
): Promise<KnowledgeDocumentPage> {
  const params = new URLSearchParams({
    region: options.region,
    offset: String(options.offset ?? 0),
    limit: String(options.limit ?? 30),
  });
  if (options.documentType?.trim()) params.set("documentType", options.documentType.trim());
  const response = await knowledgeFetch<unknown>(
    `/web/knowledge-bases/${encodeURIComponent(knowledgeId)}/documents?${params.toString()}`,
    { signal: options.signal },
  );
  const page = asRecord(response);
  return {
    items: Array.isArray(page.items) ? page.items.map(normalizeKnowledgeDocument) : [],
    offset: asNumber(page.offset, 0),
    limit: asNumber(page.limit, options.limit ?? 30),
    hasMore: page.hasMore === true,
  };
}

export async function previewKnowledgeDocument(
  knowledgeId: string,
  documentId: string,
  options: { region: string; offset?: number; limit?: number; signal?: AbortSignal },
): Promise<KnowledgeDocumentPreviewPage> {
  const params = new URLSearchParams({
    region: options.region,
    offset: String(options.offset ?? 0),
    limit: String(options.limit ?? 20),
  });
  const response = await knowledgeFetch<unknown>(
    `/web/knowledge-bases/${encodeURIComponent(knowledgeId)}/documents/${encodeURIComponent(documentId)}/preview?${params.toString()}`,
    { signal: options.signal },
  );
  const page = asRecord(response);
  return {
    document: normalizeKnowledgeDocument(page.document),
    chunks: Array.isArray(page.chunks)
      ? page.chunks.map(normalizeKnowledgePreviewChunk)
      : [],
    offset: asNumber(page.offset, 0),
    limit: asNumber(page.limit, options.limit ?? 20),
    hasMore: page.hasMore === true,
  };
}

export function createKnowledgeDocument(
  knowledgeId: string,
  region: string,
  input: CreateKnowledgeDocumentInput,
): Promise<KnowledgeDocumentItem> {
  return knowledgeFetch<unknown>(
    `/web/knowledge-bases/${encodeURIComponent(knowledgeId)}/documents${regionQuery(region)}`,
    { method: "POST", body: JSON.stringify(input) },
    TRANSFER_REQUEST_TIMEOUT_MS,
  ).then(normalizeKnowledgeDocument);
}

export function uploadKnowledgeDocument(
  knowledgeId: string,
  region: string,
  input: UploadKnowledgeDocumentInput,
): Promise<KnowledgeDocumentItem> {
  const form = new FormData();
  form.set("file", input.file);
  if (input.name?.trim()) form.set("name", input.name.trim());
  if (input.documentType?.trim()) form.set("documentType", input.documentType.trim());
  if (input.metadata) form.set("metadata", JSON.stringify(input.metadata));
  return knowledgeFetch<unknown>(
    `/web/knowledge-bases/${encodeURIComponent(knowledgeId)}/documents/upload${regionQuery(region)}`,
    { method: "POST", body: form },
    TRANSFER_REQUEST_TIMEOUT_MS,
  ).then(normalizeKnowledgeDocument);
}

export function updateKnowledgeDocument(
  knowledgeId: string,
  documentId: string,
  region: string,
  input: { metadata: Record<string, unknown> },
): Promise<KnowledgeDocumentItem> {
  return knowledgeFetch<unknown>(
    `/web/knowledge-bases/${encodeURIComponent(knowledgeId)}/documents/${encodeURIComponent(documentId)}${regionQuery(region)}`,
    { method: "PATCH", body: JSON.stringify(input) },
  ).then(normalizeKnowledgeDocument);
}

export function deleteKnowledgeDocument(
  knowledgeId: string,
  documentId: string,
  region: string,
): Promise<void> {
  return knowledgeFetch(
    `/web/knowledge-bases/${encodeURIComponent(knowledgeId)}/documents/${encodeURIComponent(documentId)}${regionQuery(region)}`,
    { method: "DELETE" },
    TRANSFER_REQUEST_TIMEOUT_MS,
  );
}

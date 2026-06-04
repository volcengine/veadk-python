// Smart search, scoped to a single agent, organized by source. Results carry a
// `type` discriminator so the UI renders each kind differently.
//   - session:   text match across the agent's session contents (client-side,
//                reusing the ADK list/get-session endpoints).
//   - web:       the agent's web-search tool, run server-side with the user's
//                environment credentials (see backend /web/search).
//   - knowledge/memory: reserved (TODO, backend-backed).

import { getSession, listSessions, webSearch, type AdkSession } from "./client";

export type SearchSource = "session" | "web" | "knowledge" | "memory";

export interface SessionResult {
  type: "session";
  appId: string;
  sessionId: string;
  title: string;
  snippet: string;
  role: string;
  ts?: number;
}

export interface WebResult {
  type: "web";
  index: number;
  title: string;
  url: string;
  siteName: string;
  summary: string;
}

export type SearchResult = SessionResult | WebResult;

/** Search outcome: results plus an optional human note (e.g. "not mounted"). */
export interface SearchOutcome {
  results: SearchResult[];
  note?: string;
}

const MAX_RESULTS = 50;
const SNIPPET_PAD = 48;

function textOf(session: AdkSession): { text: string; role: string; ts?: number }[] {
  return (session.events ?? []).flatMap((ev) => {
    const parts = ev.content?.parts ?? [];
    const text = parts
      .map((p) => (typeof p.text === "string" ? p.text : ""))
      .filter(Boolean)
      .join("");
    return text ? [{ text, role: ev.author ?? ev.content?.role ?? "", ts: ev.timestamp }] : [];
  });
}

function firstUserText(session: AdkSession): string {
  for (const ev of session.events ?? []) {
    if (ev.author === "user" || ev.content?.role === "user") {
      const t = (ev.content?.parts ?? []).map((p) => p.text).find(Boolean);
      if (t) return t;
    }
  }
  return "未命名会话";
}

function snippetAround(text: string, idx: number, qlen: number): string {
  const start = Math.max(0, idx - SNIPPET_PAD);
  const end = Math.min(text.length, idx + qlen + SNIPPET_PAD);
  return (start > 0 ? "…" : "") + text.slice(start, end).trim() + (end < text.length ? "…" : "");
}

/** Text-match across one agent's sessions. */
async function searchSessions(
  userId: string,
  appId: string,
  query: string,
): Promise<SessionResult[]> {
  const q = query.trim().toLowerCase();
  if (!q || !appId) return [];

  const list = await listSessions(appId, userId);
  const hydrated = await Promise.all(
    list.map(async (s) => {
      if (s.events?.length) return s;
      try {
        return await getSession(appId, userId, s.id);
      } catch {
        return s;
      }
    }),
  );

  const results: SessionResult[] = [];
  for (const session of hydrated) {
    for (const { text, role, ts } of textOf(session)) {
      const idx = text.toLowerCase().indexOf(q);
      if (idx === -1) continue;
      results.push({
        type: "session",
        appId,
        sessionId: session.id,
        title: firstUserText(session),
        snippet: snippetAround(text, idx, q.length),
        role,
        ts: ts ?? session.lastUpdateTime,
      });
      break; // one result per session
    }
  }
  results.sort((a, b) => (b.ts ?? 0) - (a.ts ?? 0));
  return results.slice(0, MAX_RESULTS);
}

/** Run the agent's web-search tool server-side (env credentials). */
async function searchWeb(appId: string, query: string): Promise<SearchOutcome> {
  if (!appId || !query.trim()) return { results: [] };
  let res;
  try {
    res = await webSearch(appId, query.trim());
  } catch (e) {
    const msg = String(e);
    return {
      results: [],
      note: msg.includes("404")
        ? "网页搜索接口未就绪（后端未启用 /web/search）。"
        : `网页搜索失败：${msg}`,
    };
  }
  const { mounted, results, error } = res;
  if (!mounted) return { results: [], note: "该 Agent 未挂载 Web Search 工具。" };
  if (error) return { results: [], note: error };
  return {
    results: results.map((hit, index) => ({
      type: "web",
      index,
      title: hit.title,
      url: hit.url,
      siteName: hit.siteName,
      summary: hit.summary,
    })),
  };
}

export interface SearchContext {
  userId: string;
  appId: string;
}

/** Dispatch a search to the chosen source. */
export async function search(
  source: SearchSource,
  query: string,
  ctx: SearchContext,
): Promise<SearchOutcome> {
  if (source === "session") return { results: await searchSessions(ctx.userId, ctx.appId, query) };
  if (source === "web") return searchWeb(ctx.appId, query);
  return { results: [], note: "该搜索源即将支持。" };
}

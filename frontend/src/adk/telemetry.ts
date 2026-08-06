import type {
  StudioRole,
  StudioTelemetryConfig,
  StudioTelemetryContext,
} from "./client";

export type StudioTelemetryEventName =
  | "studio_instance_loaded"
  | "studio_user_authenticated"
  | "studio_agent_deploy"
  | "studio_sandbox_create";

export interface StudioTelemetryEventOptions {
  dedupeKey?: string;
  dailyDedupeKey?: string;
}

interface ApmplusInitConfig {
  aid: number;
  token: string;
  domain: string;
  env: string;
  release?: string;
  userId?: string;
}

interface ApmplusCustomEvent {
  name: string;
  categories?: Record<string, string>;
  metrics?: Record<string, number>;
}

interface ApmplusCustomReport {
  ev_type: "custom";
  payload: ApmplusCustomEvent & {
    type: "event";
  };
  extra: {
    timestamp: number;
  };
}

interface ApmplusClient {
  (method: "init", config: ApmplusInitConfig): void;
  (method: "start"): void;
  (method: "config", config: Partial<ApmplusInitConfig>): void;
  (method: "report", data: ApmplusCustomReport): void;
}

const MAX_PENDING_EVENTS = 50;
const sentKeys = new Set<string>();

let telemetryConfig: StudioTelemetryConfig = { enabled: false };
let telemetryContext: StudioTelemetryContext | undefined;
let apmplusClient: ApmplusClient | null = null;
let initPromise: Promise<void> | null = null;
let userId = "";
let userRole: StudioRole | "unknown" = "unknown";
let userSource: "sso" | "local" | "unknown" = "unknown";
let pendingEvents: ApmplusCustomEvent[] = [];

function stringifyCategory(value: unknown): string {
  if (value === undefined || value === null) return "";
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return JSON.stringify(value);
}

function normalizeCategories(
  categories: Record<string, unknown>,
): Record<string, string> {
  return Object.fromEntries(
    Object.entries(categories)
      .filter(([, value]) => value !== undefined && value !== null)
      .map(([key, value]) => [key, stringifyCategory(value)]),
  );
}

function normalizeMetrics(metrics?: Record<string, number>): Record<string, number> {
  if (!metrics) return {};
  return Object.fromEntries(
    Object.entries(metrics).filter(([, value]) => Number.isFinite(value)),
  );
}

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function consumeDedupe(options?: StudioTelemetryEventOptions): boolean {
  if (!options) return true;
  if (options.dedupeKey) {
    if (sentKeys.has(options.dedupeKey)) return false;
    sentKeys.add(options.dedupeKey);
  }
  if (options.dailyDedupeKey && typeof localStorage !== "undefined") {
    const key = `veadk.studio.telemetry.${today()}.${options.dailyDedupeKey}`;
    try {
      if (localStorage.getItem(key) === "1") return false;
      localStorage.setItem(key, "1");
    } catch {
      /* ignore storage failures */
    }
  }
  return true;
}

function enqueueOrSend(event: ApmplusCustomEvent): void {
  if (apmplusClient) {
    try {
      apmplusClient("report", {
        ev_type: "custom",
        payload: {
          ...event,
          type: "event",
        },
        extra: {
          timestamp: Date.now(),
        },
      });
    } catch (error) {
      console.warn("[telemetry] failed to send Studio event:", error);
    }
    return;
  }
  pendingEvents = [...pendingEvents.slice(-(MAX_PENDING_EVENTS - 1)), event];
}

function flushPendingEvents(): void {
  if (!apmplusClient) return;
  const events = pendingEvents;
  pendingEvents = [];
  for (const event of events) enqueueOrSend(event);
}

export function initStudioTelemetry(config: StudioTelemetryConfig): void {
  telemetryConfig = config;
  telemetryContext = config.studio;
  if (!config.enabled || !config.apmplus) return;
  if (initPromise) return;
  const apmplus = config.apmplus;
  initPromise = import("@apmplus/web")
    .then((module) => {
      const client = module.default as unknown as ApmplusClient;
      client("init", {
        aid: apmplus.aid,
        token: apmplus.token,
        domain: apmplus.domain,
        env: apmplus.env,
        release: config.studio?.version,
        userId: userId || undefined,
      });
      client("start");
      apmplusClient = client;
      flushPendingEvents();
    })
    .catch((error) => {
      console.warn("[telemetry] APMPlus SDK failed to initialize:", error);
      telemetryConfig = { enabled: false };
      pendingEvents = [];
    });
}

export function trackStudioEvent(
  name: StudioTelemetryEventName,
  categories: Record<string, unknown> = {},
  metrics?: Record<string, number>,
  options?: StudioTelemetryEventOptions,
): void {
  if (!telemetryConfig.enabled || !telemetryConfig.apmplus) return;
  if (!consumeDedupe(options)) return;
  const userCategories = name !== "studio_instance_loaded"
    ? {
      user_id: userId,
      user_role: userRole,
      user_source: userSource,
    }
    : {};
  enqueueOrSend({
    name,
    categories: normalizeCategories({
      studio_deploy_id: telemetryContext?.deployId,
      user_pool_id: telemetryContext?.userPoolId,
      vefaas_application_id: telemetryContext?.applicationId,
      vefaas_function_id: telemetryContext?.functionId,
      studio_region: telemetryContext?.region,
      studio_project: telemetryContext?.project,
      studio_version: telemetryContext?.version,
      ...userCategories,
      ...categories,
    }),
    metrics: normalizeMetrics(metrics),
  });
}

export function identifyStudioTelemetryUser(args: {
  userId: string;
  role?: StudioRole;
  local: boolean;
}): void {
  userId = args.userId.trim();
  if (!userId) return;
  userRole = args.role ?? "unknown";
  userSource = args.local ? "local" : "sso";
  if (apmplusClient) {
    try {
      apmplusClient("config", { userId });
    } catch (error) {
      console.warn("[telemetry] failed to update Studio user id:", error);
    }
  }
  trackStudioEvent(
    "studio_user_authenticated",
    {},
    undefined,
    {
      dailyDedupeKey: [
        "studio_user_authenticated",
        telemetryContext?.deployId ?? "",
        userId,
        userRole,
      ].join(":"),
    },
  );
}

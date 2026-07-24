import type { BrowserCommandClient } from "@apmplus/web";

type EventCategories = Record<string, string | boolean | number | undefined>;
type EventMetrics = Record<string, number | undefined>;

const appId = Number(__APMPLUS_AID__);
const configured =
  __APMPLUS_ENABLED__.toLowerCase() !== "false" &&
  Number.isInteger(appId) &&
  appId > 0 &&
  __APMPLUS_TOKEN__.length > 0;

let client: BrowserCommandClient | undefined;
let initialization: Promise<void> | undefined;

function trackingAllowed(): boolean {
  return configured && navigator.doNotTrack !== "1";
}

export function initAnalytics(): Promise<void> {
  if (!trackingAllowed()) return Promise.resolve();
  if (initialization) return initialization;

  initialization = import("@apmplus/web")
    .then(({ default: browserClient }) => {
      browserClient("context.merge", {
        product: "veadk_studio",
        distribution: "open_source",
      });
      browserClient("init", {
        aid: appId,
        token: __APMPLUS_TOKEN__,
        env: __APMPLUS_ENV__,
        pid: "/studio",
      });
      browserClient("start");
      client = browserClient;
      browserClient("sendEvent", {
        name: "studio_open",
        metrics: { count: 1 },
        categories: { environment: __APMPLUS_ENV__ },
      });
    })
    .catch((error: unknown) => {
      console.warn("[analytics] WebPro initialization failed:", error);
    });

  return initialization;
}

export function identifyAnalyticsUser(userId: string): void {
  if (!userId || !trackingAllowed()) return;
  void initAnalytics().then(() => {
    client?.("config", { userId });
  });
}

export function trackEvent(
  name: string,
  categories: EventCategories = {},
  metrics: EventMetrics = {},
): void {
  if (!trackingAllowed()) return;
  const normalizedCategories = Object.fromEntries(
    Object.entries(categories)
      .filter((entry): entry is [string, string | boolean | number] => entry[1] !== undefined)
      .map(([key, value]) => [key, String(value)]),
  );
  const normalizedMetrics = Object.fromEntries(
    Object.entries(metrics).filter(
      (entry): entry is [string, number] =>
        entry[1] !== undefined && Number.isFinite(entry[1]),
    ),
  );
  const eventMetrics =
    Object.keys(normalizedMetrics).length > 0 ? normalizedMetrics : { count: 1 };

  void initAnalytics().then(() => {
    client?.("sendEvent", {
      name,
      categories: normalizedCategories,
      metrics: eventMetrics,
    });
  });
}

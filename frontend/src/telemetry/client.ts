import {
  TEA_APP_ID,
  type StudioTelemetryEventName,
  type TelemetryEnvironment,
  type TelemetryPayload,
} from "./schema";
import type { TelemetrySink } from "./runtime";

export const TEA_SCRIPT_URL =
  "https://lf-static.applogcdn.com/obj/applog-sdk-static/log-sdk/collect/5/collect.js";
const MAX_PENDING_EVENTS = 50;

interface TeaCollector {
  (command: string, payload?: TelemetryPayload): void;
  q?: IArguments[];
  l?: number;
}

declare global {
  interface Window {
    LogAnalyticsObject?: "collectEvent";
    collectEvent?: TeaCollector;
  }
}

export interface TeaClientConfig {
  enabled: boolean;
  environment: TelemetryEnvironment;
}

export class TeaClient implements TelemetrySink {
  private enabled = false;
  private initialized = false;
  private pending: Array<[StudioTelemetryEventName, TelemetryPayload]> = [];
  private userUniqueId = "";
  private initPromise: Promise<void> | undefined;

  init(config: TeaClientConfig): Promise<void> {
    this.enabled = config.enabled;
    if (!this.enabled) {
      this.pending = [];
      return Promise.resolve();
    }
    if (this.initPromise) return this.initPromise;
    this.initPromise = Promise.resolve().then(() => {
      const collector = this.bootstrapCollector();
      collector("init", {
        app_id: TEA_APP_ID,
        channel: "cn",
        disable_auto_pv: 1,
      });
      if (this.userUniqueId) {
        collector("config", { user_unique_id: this.userUniqueId });
      }
      collector("config", {
        _staging_flag: config.environment === "prod" ? 0 : 1,
      });
      collector("start");
      this.initialized = true;
      const pending = this.pending;
      this.pending = [];
      for (const [name, payload] of pending) this.collect(name, payload);
    });
    return this.initPromise;
  }

  identify(userUniqueId: string): void {
    this.userUniqueId = userUniqueId;
    if (this.initialized) {
      this.collect("config", { user_unique_id: userUniqueId });
    }
  }

  emit(name: StudioTelemetryEventName, payload: TelemetryPayload): void {
    if (!this.enabled) return;
    if (this.initialized) {
      this.collect(name, payload);
      return;
    }
    this.pending = [
      ...this.pending.slice(-(MAX_PENDING_EVENTS - 1)),
      [name, payload],
    ];
  }

  private bootstrapCollector(): TeaCollector {
    if (window.collectEvent) return window.collectEvent;
    window.LogAnalyticsObject = "collectEvent";
    const collector: TeaCollector = function collectEventQueue() {
      collector.q?.push(arguments);
    };
    collector.q = [];
    collector.l = Date.now();
    window.collectEvent = collector;

    const script = document.createElement("script");
    script.async = true;
    script.src = TEA_SCRIPT_URL;
    script.onerror = () => {
      this.enabled = false;
      collector.q = [];
      console.warn("[telemetry] TEA SDK script failed to load");
    };
    document.head.appendChild(script);
    return collector;
  }

  private collect(command: string, payload: TelemetryPayload): void {
    // The SDK replaces the bootstrap queue on `window.collectEvent` once its
    // script loads. Always resolve the current global function so events that
    // occur after that handoff do not remain stranded in the old queue.
    window.collectEvent?.(command, payload);
  }
}

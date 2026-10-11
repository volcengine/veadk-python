import defaultSdk, {
  WecomAIBotSDK,
} from "@wecom/wecom-aibot-sdk/dist/wecom-aibot-sdk.esm.js";

// The package creates a singleton listener on import; attempts own their instances.
defaultSdk.destroy();

export class WecomAuthorizationError extends Error {
  constructor(public readonly code: string) {
    super("WeCom authorization failed");
  }
}

export function authorizeWecom(
  signal: AbortSignal,
): Promise<{ botId: string; secret: string }> {
  if (signal.aborted)
    return Promise.reject(new DOMException("Cancelled", "AbortError"));
  const sdk = new WecomAIBotSDK();
  return new Promise((resolve, reject) => {
    let settled = false;
    const cleanup = () => {
      settled = true;
      clearTimeout(timeout);
      signal.removeEventListener("abort", abort);
      sdk.destroy();
    };
    const fail = (error: unknown) => {
      if (settled) return;
      cleanup();
      reject(error);
    };
    const abort = () => fail(new DOMException("Cancelled", "AbortError"));
    const timeout = setTimeout(
      () => fail(new WecomAuthorizationError("AUTH_TIMEOUT")),
      300_000,
    );
    signal.addEventListener("abort", abort, { once: true });
    try {
      // No await before opening: browsers require the original user activation.
      sdk
        .openBotInfoAuthWindow({
          source: "mpa-agent",
          state: crypto.randomUUID(),
          debug: false,
        })
        .then(
          (bot) => {
            if (settled) return;
            if (
              typeof bot?.botid !== "string" ||
              !bot.botid.trim() ||
              typeof bot?.secret !== "string" ||
              !bot.secret.trim()
            ) {
              fail(new WecomAuthorizationError("INVALID_RESULT"));
              return;
            }
            cleanup();
            resolve({ botId: bot.botid.trim(), secret: bot.secret.trim() });
          },
          (error: unknown) => {
            const code =
              error &&
              typeof error === "object" &&
              "code" in error &&
              typeof error.code === "string"
                ? error.code
                : "FAILED";
            fail(new WecomAuthorizationError(code));
          },
        );
    } catch {
      fail(new WecomAuthorizationError("FAILED"));
    }
  });
}

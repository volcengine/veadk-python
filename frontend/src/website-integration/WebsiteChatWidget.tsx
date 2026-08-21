import { useCallback, useEffect, useRef, useState } from "react";

import defaultSiteLogo from "../assets/logo.svg";
import { parseSSE } from "../adk/sse";
import type { AdkEvent } from "../adk/client";
import { applyEvent, emptyAcc, type Turn } from "../blocks";
import { Blocks, ThinkingPlaceholder } from "../ui/Blocks";
import { CompactComposer } from "../ui/CompactComposer";
import { Markdown } from "../ui/Markdown";

interface WebsiteChatWidgetProps {
  studioOrigin: string;
  token: string;
}

interface BootstrapPayload {
  sessionToken?: string;
}

interface Point {
  x: number;
  y: number;
}

interface LauncherDrag {
  pointerId: number;
  start: Point;
  origin: Point;
  moved: boolean;
}

const DRAG_THRESHOLD = 5;
const FLOATING_MARGIN = 12;
const PANEL_GAP = 12;

function clamp(value: number, minimum: number, maximum: number): number {
  return Math.min(Math.max(value, minimum), Math.max(minimum, maximum));
}

function CloseIcon() {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      aria-hidden="true"
    >
      <path d="m6.5 6.5 11 11M17.5 6.5l-11 11" />
    </svg>
  );
}

function SiteLogo({ studioOrigin, className = "" }: { studioOrigin: string; className?: string }) {
  const [fallback, setFallback] = useState(false);
  return (
    <img
      className={className}
      src={fallback ? defaultSiteLogo : `${studioOrigin}/web/site-logo`}
      alt=""
      onError={() => setFallback(true)}
    />
  );
}

function textTurn(text: string, role: "user" | "assistant"): Turn {
  return {
    role,
    blocks: [{ kind: "text", text }],
    meta: { ts: Date.now() / 1000 },
  };
}

function errorMessage(response: Response): Promise<string> {
  return response.text().then((body) => {
    try {
      const detail = (JSON.parse(body) as { detail?: unknown }).detail;
      if (typeof detail === "string" && detail) return detail;
    } catch {
      // Preserve the readable response body below.
    }
    return body.trim() || `请求失败 (${response.status})`;
  });
}

export function WebsiteChatWidget({ studioOrigin, token }: WebsiteChatWidgetProps) {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [turns, setTurns] = useState<Turn[]>([
    textTurn("您好，有什么可以帮您？", "assistant"),
  ]);
  const [sessionToken, setSessionToken] = useState("");
  const [bootstrapError, setBootstrapError] = useState("");
  const [busy, setBusy] = useState(false);
  const transcriptRef = useRef<HTMLDivElement>(null);
  const launcherRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLElement>(null);
  const launcherPositionRef = useRef<Point | null>(null);
  const dragRef = useRef<LauncherDrag | null>(null);
  const suppressClickRef = useRef(false);
  const suppressClickTimerRef = useRef<number | null>(null);
  const userIdRef = useRef(`website-${crypto.randomUUID()}`);
  const sessionIdRef = useRef(crypto.randomUUID());

  const positionPanelByLauncher = useCallback(() => {
    const launcher = launcherRef.current;
    const panel = panelRef.current;
    if (!launcher || !panel || !launcherPositionRef.current) return;

    const launcherRect = launcher.getBoundingClientRect();
    const panelWidth = panel.offsetWidth;
    const panelHeight = panel.offsetHeight;
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const launcherCenterX = launcherRect.left + launcherRect.width / 2;
    const spaceAbove = launcherRect.top - FLOATING_MARGIN;
    const spaceBelow = viewportHeight - launcherRect.bottom - FLOATING_MARGIN;

    const preferredTop = spaceAbove >= panelHeight + PANEL_GAP || spaceAbove >= spaceBelow
      ? launcherRect.top - panelHeight - PANEL_GAP
      : launcherRect.bottom + PANEL_GAP;
    const preferredLeft = launcherCenterX >= viewportWidth / 2
      ? launcherRect.right - panelWidth
      : launcherRect.left;
    const left = clamp(
      preferredLeft,
      FLOATING_MARGIN,
      viewportWidth - panelWidth - FLOATING_MARGIN,
    );
    const top = clamp(
      preferredTop,
      FLOATING_MARGIN,
      viewportHeight - panelHeight - FLOATING_MARGIN,
    );

    panel.style.left = `${left}px`;
    panel.style.top = `${top}px`;
    panel.style.right = "auto";
    panel.style.bottom = "auto";
    panel.style.transformOrigin = `${clamp(launcherCenterX - left, 0, panelWidth)}px ${
      launcherRect.top >= top + panelHeight ? panelHeight : 0
    }px`;
  }, []);

  const positionLauncher = useCallback((x: number, y: number) => {
    const launcher = launcherRef.current;
    if (!launcher) return;
    const next = {
      x: clamp(x, FLOATING_MARGIN, window.innerWidth - launcher.offsetWidth - FLOATING_MARGIN),
      y: clamp(y, FLOATING_MARGIN, window.innerHeight - launcher.offsetHeight - FLOATING_MARGIN),
    };
    launcherPositionRef.current = next;
    launcher.style.left = `${next.x}px`;
    launcher.style.top = `${next.y}px`;
    launcher.style.right = "auto";
    launcher.style.bottom = "auto";
    positionPanelByLauncher();
  }, [positionPanelByLauncher]);

  const moveLauncher = useCallback((event: PointerEvent) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    event.preventDefault();
    const deltaX = event.clientX - drag.start.x;
    const deltaY = event.clientY - drag.start.y;
    if (!drag.moved && Math.hypot(deltaX, deltaY) < DRAG_THRESHOLD) return;
    if (!drag.moved) {
      drag.moved = true;
      launcherRef.current?.classList.add("is-dragging");
    }
    positionLauncher(drag.origin.x + deltaX, drag.origin.y + deltaY);
  }, [positionLauncher]);

  const finishLauncherDrag = useCallback((event: PointerEvent) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== event.pointerId) return;
    if (drag.moved) {
      suppressClickRef.current = true;
      if (suppressClickTimerRef.current != null) {
        window.clearTimeout(suppressClickTimerRef.current);
      }
      suppressClickTimerRef.current = window.setTimeout(() => {
        suppressClickRef.current = false;
        suppressClickTimerRef.current = null;
      }, 0);
    }
    dragRef.current = null;
    launcherRef.current?.classList.remove("is-dragging");
  }, []);

  const scrollToLatest = useCallback(() => {
    requestAnimationFrame(() => {
      const transcript = transcriptRef.current;
      if (transcript) transcript.scrollTop = transcript.scrollHeight;
    });
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    void fetch(`${studioOrigin}/embed/session`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
      signal: controller.signal,
    })
      .then(async (response) => {
        if (!response.ok) throw new Error(await errorMessage(response));
        return response.json() as Promise<BootstrapPayload>;
      })
      .then((payload) => {
        if (!payload.sessionToken) throw new Error("无法建立对话会话");
        setSessionToken(payload.sessionToken);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        setBootstrapError(
          cause instanceof Error ? cause.message : "当前网站未获得对话授权",
        );
      });
    return () => controller.abort();
  }, [studioOrigin, token]);

  useEffect(scrollToLatest, [busy, scrollToLatest, turns]);

  useEffect(() => {
    if (!open || !launcherPositionRef.current) return;
    const frame = requestAnimationFrame(positionPanelByLauncher);
    return () => cancelAnimationFrame(frame);
  }, [open, positionPanelByLauncher]);

  useEffect(() => {
    const keepInViewport = () => {
      const position = launcherPositionRef.current;
      if (position) positionLauncher(position.x, position.y);
    };
    window.addEventListener("resize", keepInViewport);
    window.visualViewport?.addEventListener("resize", keepInViewport);
    return () => {
      window.removeEventListener("resize", keepInViewport);
      window.visualViewport?.removeEventListener("resize", keepInViewport);
    };
  }, [positionLauncher]);

  useEffect(() => {
    window.addEventListener("pointermove", moveLauncher, { passive: false });
    window.addEventListener("pointerup", finishLauncherDrag);
    window.addEventListener("pointercancel", finishLauncherDrag);
    return () => {
      window.removeEventListener("pointermove", moveLauncher);
      window.removeEventListener("pointerup", finishLauncherDrag);
      window.removeEventListener("pointercancel", finishLauncherDrag);
    };
  }, [finishLauncherDrag, moveLauncher]);

  useEffect(() => () => {
    if (suppressClickTimerRef.current != null) {
      window.clearTimeout(suppressClickTimerRef.current);
    }
  }, []);

  const submit = async () => {
    const message = input.trim();
    if (!message || !sessionToken || busy) return;
    setInput("");
    setBusy(true);
    setTurns((current) => [
      ...current,
      textTurn(message, "user"),
      { role: "assistant", blocks: [], meta: { ts: Date.now() / 1000 } },
    ]);

    try {
      const response = await fetch(`${studioOrigin}/embed/run_sse`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${sessionToken}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          message,
          userId: userIdRef.current,
          sessionId: sessionIdRef.current,
        }),
      });
      if (!response.ok || !response.body) {
        throw new Error(await errorMessage(response));
      }

      let accumulator = emptyAcc();
      let meta: Turn["meta"] = { ts: Date.now() / 1000 };
      for await (const rawEvent of parseSSE(response)) {
        const event = rawEvent as AdkEvent;
        const streamError = event.error ?? event.errorMessage ?? event.error_message;
        if (typeof streamError === "string" && streamError) {
          throw new Error(streamError);
        }
        accumulator = applyEvent(accumulator, event);
        meta = {
          author: event.author && event.author !== "user" ? event.author : meta?.author,
          ts: event.timestamp ?? meta?.ts,
          eventId: event.id ?? meta?.eventId,
          invocationId: event.invocationId ?? event.invocation_id ?? meta?.invocationId,
        };
        const nextTurn: Turn = {
          role: "assistant",
          blocks: accumulator.blocks,
          meta,
        };
        setTurns((current) => [...current.slice(0, -1), nextTurn]);
      }
    } catch (cause: unknown) {
      const message = cause instanceof Error ? cause.message : "对话请求失败，请稍后重试";
      setTurns((current) => [
        ...current.slice(0, -1),
        textTurn(message, "assistant"),
      ]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="website-widget">
      <button
        ref={launcherRef}
        type="button"
        className="website-widget__launcher"
        aria-label={open ? "关闭智能体对话" : "打开智能体对话"}
        aria-expanded={open}
        onClick={() => {
          if (suppressClickRef.current) {
            suppressClickRef.current = false;
            if (suppressClickTimerRef.current != null) {
              window.clearTimeout(suppressClickTimerRef.current);
              suppressClickTimerRef.current = null;
            }
            return;
          }
          setOpen((current) => !current);
        }}
        onPointerDown={(event) => {
          if (event.button !== 0) return;
          const rect = event.currentTarget.getBoundingClientRect();
          dragRef.current = {
            pointerId: event.pointerId,
            start: { x: event.clientX, y: event.clientY },
            origin: { x: rect.left, y: rect.top },
            moved: false,
          };
        }}
        onDragStart={(event) => event.preventDefault()}
      >
        <SiteLogo studioOrigin={studioOrigin} className="website-widget__launcher-logo" />
      </button>

      <section
        ref={panelRef}
        className={`website-widget__panel${open ? " is-open" : ""}`}
        aria-label="智能体对话面板"
        aria-hidden={!open}
      >
        <header className="website-widget__header">
          <div className="website-widget__identity">
            <span className="website-widget__identity-logo">
              <SiteLogo studioOrigin={studioOrigin} />
            </span>
            <span className="website-widget__identity-copy">
              <strong>智能体助手</strong>
              <span>在线对话</span>
            </span>
          </div>
          <button
            type="button"
            className="website-widget__close"
            aria-label="关闭对话"
            onClick={() => setOpen(false)}
          >
            <CloseIcon />
          </button>
        </header>

        <div
          ref={transcriptRef}
          className={`website-widget__transcript transcript${busy ? " is-streaming" : ""}`}
          aria-live="polite"
        >
          {turns.map((turn, index) => {
            if (turn.role === "user") {
              const text = turn.blocks
                .filter((block) => block.kind === "text")
                .map((block) => block.kind === "text" ? block.text : "")
                .join("");
              return (
                <div className="turn turn--user" key={`user-${index}`}>
                  <div className="bubble"><Markdown text={text} allowRawHtml={false} /></div>
                </div>
              );
            }
            const pending = turn.blocks.length === 0;
            const streaming = busy && index === turns.length - 1;
            return (
              <div className="turn turn--assistant" key={`assistant-${index}`}>
                {pending && streaming ? (
                  <ThinkingPlaceholder />
                ) : (
                  <Blocks
                    blocks={turn.blocks}
                    streaming={streaming}
                    onStreamFrame={scrollToLatest}
                    onAction={() => {}}
                  />
                )}
              </div>
            );
          })}
          {bootstrapError ? (
            <div className="website-widget__error" role="alert">
              {bootstrapError}
            </div>
          ) : null}
        </div>

        <div className="website-widget__composer-slot">
          <CompactComposer
            value={input}
            busy={busy}
            disabled={!sessionToken || Boolean(bootstrapError)}
            onChange={setInput}
            onSubmit={() => void submit()}
          />
        </div>
      </section>
    </div>
  );
}

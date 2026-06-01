import { useEffect, useRef, useState } from "react";
import { ChevronRight, Loader2, Wrench } from "lucide-react";
import type { Block } from "../blocks";
import { buildSurfaces, SurfaceView } from "../a2ui/Surface";
import { useStickToBottom } from "./useStickToBottom";
import type { A2uiAction, A2uiComponent } from "../a2ui/types";

const A2UI_TOOL = "send_a2ui_json_to_client";

/** Hand-drawn "spark" icon for the thinking indicator. */
function SparkIcon({ className }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" width="15" height="15" fill="currentColor" aria-hidden>
      <path d="M12 2.2l1.7 5.1a3 3 0 0 0 1.9 1.9L20.8 11l-5.1 1.7a3 3 0 0 0-1.9 1.9L12 19.8l-1.7-5.1a3 3 0 0 0-1.9-1.9L3.2 11l5.1-1.7a3 3 0 0 0 1.9-1.9L12 2.2z" />
    </svg>
  );
}

export function ThinkingBlock({ text, done }: { text: string; done: boolean }) {
  // Expanded while thinking; auto-collapses when done. A manual toggle wins.
  const [open, setOpen] = useState(!done);
  const touched = useRef(false);
  useEffect(() => {
    if (!touched.current) setOpen(!done);
  }, [done]);
  const toggle = () => {
    touched.current = true;
    setOpen((o) => !o);
  };
  const body = text.replace(/^\s+/, "");
  const { ref, onScroll } = useStickToBottom<HTMLDivElement>(body);
  return (
    <div className="block-thinking">
      <button className="think-head" onClick={toggle} type="button">
        <SparkIcon className={`spark ${done ? "" : "pulse"}`} />
        <span className={`think-label ${done ? "think-label--done" : "shimmer"}`}>
          {done ? "已完成思考" : "思考中"}
        </span>
        <ChevronRight className={`chev ${open ? "open" : ""}`} />
      </button>
      <div className={`think-collapse ${open && body ? "open" : ""}`}>
        <div className="think-collapse-inner">
          <div className="think-body scroll" ref={ref} onScroll={onScroll}>
            {body}
          </div>
        </div>
      </div>
    </div>
  );
}

/** Shown immediately after sending — identical head to ThinkingBlock so there
 *  is no layout jump when real content streams in. */
export function ThinkingPlaceholder() {
  return <ThinkingBlock text="" done={false} />;
}

function ToolBlock({ name, args, done }: { name: string; args?: unknown; done: boolean }) {
  const [open, setOpen] = useState(false);
  const label = name === A2UI_TOOL ? "渲染 UI" : name;
  return (
    <div className="block-tool">
      <button className="tool-head" onClick={() => setOpen((o) => !o)} type="button">
        {done ? <Wrench className="chev" /> : <Loader2 className="chev spin" />}
        <span className="tool-name">{label}</span>
        <ChevronRight className={`chev ${open ? "open" : ""}`} />
      </button>
      <div className={`think-collapse ${open ? "open" : ""}`}>
        <div className="think-collapse-inner">
          {args != null && <pre className="tool-args">{JSON.stringify(args, null, 2)}</pre>}
        </div>
      </div>
    </div>
  );
}

export interface BlocksProps {
  blocks: Block[];
  onAction: (action: A2uiAction | undefined, node: A2uiComponent) => void;
}

export function Blocks({ blocks, onAction }: BlocksProps) {
  return (
    <>
      {blocks.map((b, i) => {
        switch (b.kind) {
          case "thinking":
            return <ThinkingBlock key={i} text={b.text} done={b.done} />;
          case "text": {
            const t = b.text.replace(/^\s+/, "");
            return t ? (
              <div key={i} className="bubble">
                {t}
              </div>
            ) : null;
          }
          case "tool":
            if (b.name === A2UI_TOOL && b.done) return null;
            return <ToolBlock key={i} name={b.name} args={b.args} done={b.done} />;
          case "a2ui":
            return buildSurfaces(b.messages).map((s) => (
              <SurfaceView key={`${i}-${s.surfaceId}`} surface={s} onAction={onAction} />
            ));
          default:
            return null;
        }
      })}
    </>
  );
}

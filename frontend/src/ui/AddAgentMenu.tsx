import type { ComponentType, ReactNode } from "react";
import { motion } from "motion/react";
import { ChevronRight } from "lucide-react";
import "./AddAgentMenu.css";

export interface StackCardDef {
  key: string;
  /** Any component that renders an svg/icon (lucide or a custom SVG). */
  icon: ComponentType<{ className?: string }>;
  title: string;
  desc: string;
  onClick: () => void;
  disabled?: boolean;
}

/** A vertical list of wide "long bar" cards — used for the 添加 Agent chooser
 *  and the create-mode picker. */
export function StackCards({ title, sub, cards, footer }: {
  title: string;
  sub?: string;
  cards: StackCardDef[];
  footer?: ReactNode;
}) {
  return (
    <div className="stk">
      <div className="stk-head">
        <h1 className="stk-title">{title}</h1>
        {sub && <p className="stk-sub">{sub}</p>}
      </div>
      <div className="stk-list">
        {cards.map((c, i) => (
          <motion.button
            key={c.key}
            type="button"
            className={`stk-card ${c.disabled ? "stk-card-disabled" : ""}`}
            onClick={c.disabled ? undefined : c.onClick}
            disabled={c.disabled}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.18, ease: "easeOut", delay: i * 0.04 }}
          >
            <span className="stk-card-icon">
              <c.icon />
            </span>
            <span className="stk-card-text">
              <span className="stk-card-title">{c.title}</span>
              <span className="stk-card-desc">{c.desc}</span>
            </span>
            <ChevronRight className="stk-card-arrow" />
          </motion.button>
        ))}
      </div>
      {footer && <div className="stk-footer">{footer}</div>}
    </div>
  );
}

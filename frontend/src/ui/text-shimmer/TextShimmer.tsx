import type { ElementType, HTMLAttributes } from "react";
import "./text-shimmer.css";

export type TextShimmerProps = HTMLAttributes<HTMLElement> & {
  as?: ElementType;
  duration?: number;
  spread?: number;
};

/** Prompt Kit-inspired neutral text shimmer, adapted to VeADK CSS tokens. */
export function TextShimmer({
  as: Component = "span",
  className = "",
  duration = 4,
  spread = 20,
  children,
  style,
  ...props
}: TextShimmerProps) {
  const dynamicSpread = Math.min(Math.max(spread, 5), 45);

  return (
    <Component
      className={`text-shimmer${className ? ` ${className}` : ""}`}
      style={{
        ...style,
        backgroundImage: `linear-gradient(to right, hsl(var(--muted-foreground)) ${
          50 - dynamicSpread
        }%, hsl(var(--foreground)) 50%, hsl(var(--muted-foreground)) ${
          50 + dynamicSpread
        }%)`,
        animationDuration: `${duration}s`,
      }}
      {...props}
    >
      {children}
    </Component>
  );
}

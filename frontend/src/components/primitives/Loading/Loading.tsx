import type { CSSProperties } from "react";
import { motion, useReducedMotion } from "motion/react";
import "./Loading.css";

export type LoadingProps = {
  /** infinity 为无限路径，ring 为旋转圆环 */
  variant?: "infinity" | "ring";
  /** 图形宽度，数字单位为 px，也支持 CSS 长度；无限路径高度为宽度的一半，圆环宽高相同 */
  size?: number | string;
  /** 仅供屏幕阅读器读取的加载状态文案 */
  label?: string;
  /** 作为按钮内图标等装饰时启用，由外层提供状态说明 */
  decorative?: boolean;
  className?: string;
  style?: CSSProperties;
};

const infinityPath = "M 15 15 C 15 5, 25 5, 30 15 C 35 25, 45 25, 45 15 C 45 5, 35 5, 30 15 C 25 25, 15 25, 15 15";

export function Loading({ variant = "infinity", size = variant === "ring" ? 20 : 32, label = "加载中", decorative = false, className = "", style }: LoadingProps) {
  const reducedMotion = useReducedMotion();
  const halfSize = typeof size === "number" ? size / 2 : `calc(${size} / 2)`;
  const ringBorderWidth = typeof size === "number" ? size * 3 / 40 : `calc(${size} * 3 / 40)`;

  return <span
    className={`studio-loading studio-loading--${variant} ${className}`.trim()}
    style={style}
    role={decorative ? undefined : "status"}
    aria-live={decorative ? undefined : "polite"}
    aria-hidden={decorative || undefined}
  >
    {variant === "infinity" ? <svg
      className="studio-loading__infinity"
      width={typeof size === "number" ? size : undefined}
      height={typeof halfSize === "number" ? halfSize : undefined}
      style={typeof size === "string" ? { width: size, height: halfSize } : undefined}
      viewBox="0 0 60 30"
      fill="none"
      aria-hidden="true"
    >
      <path className="studio-loading__track" d={infinityPath} strokeWidth="4" strokeLinecap="round" />
      <motion.path
        className="studio-loading__path"
        d={infinityPath}
        strokeWidth="4"
        strokeLinecap="round"
        strokeDasharray={reducedMotion ? undefined : "100"}
        initial={{ strokeDashoffset: 100 }}
        animate={{ strokeDashoffset: reducedMotion ? 0 : [100, -100] }}
        transition={{ duration: reducedMotion ? 0 : 2, repeat: reducedMotion ? 0 : Infinity, ease: "linear" }}
      />
    </svg> : <motion.div
      className="studio-loading__ring"
      style={{ width: size, height: size, borderWidth: ringBorderWidth }}
      aria-hidden="true"
      animate={{ rotate: reducedMotion ? 0 : 360 }}
      transition={{ duration: reducedMotion ? 0 : 1, repeat: reducedMotion ? 0 : Infinity, ease: "linear" }}
    />}
    {!decorative && <span className="studio-loading__label">{label}</span>}
  </span>;
}

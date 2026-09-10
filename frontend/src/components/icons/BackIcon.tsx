import type { SVGProps } from "react";
import arrow from "./assets/left-outlined.svg";

export function BackIcon(props: SVGProps<SVGSVGElement>) {
  return <svg viewBox="0 0 17 17" fill="none" aria-hidden="true" {...props}>
    <image href={arrow} x="4.25" y="1.4166666" width="7.4982653" height="14.166666" opacity="0.3" />
  </svg>;
}

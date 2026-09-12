import type { SVGProps } from "react";
import type { ToastVariant } from "./Toast";

export function ToastStatusIcon({ variant, ...props }: SVGProps<SVGSVGElement> & { variant: ToastVariant }) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...props}>
    {variant === "warning" ? <>
      <path d="m10.3 4.5-7.6 13a2 2 0 0 0 1.7 3h15.2a2 2 0 0 0 1.7-3l-7.6-13a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9v4m0 3.5h.01" />
    </> : <>
      <circle cx="12" cy="12" r="8.5" />
      {variant === "success" ? <path d="m8 12 2.7 2.7L16 9.4" />
        : variant === "error" ? <path d="m9.2 9.2 5.6 5.6m0-5.6-5.6 5.6" />
        : <path d="M12 11v5m0-8h.01" />}
    </>}
  </svg>;
}

export function ToastCloseIcon(props: SVGProps<SVGSVGElement>) {
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" aria-hidden="true" {...props}>
    <path d="m7 7 10 10M17 7 7 17" />
  </svg>;
}

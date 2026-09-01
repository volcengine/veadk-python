import {
  forwardRef,
  useCallback,
  useEffect,
  useRef,
  type ButtonHTMLAttributes,
  type CSSProperties,
  type HTMLAttributes,
  type InputHTMLAttributes,
  type KeyboardEvent,
  type MouseEvent as ReactMouseEvent,
  type ReactNode,
  type SVGProps,
} from "react";
import {
  ArrowLeft,
  ArrowRight,
  PlaySm,
  PlusLg18pxAdd,
} from "@openai/apps-sdk-ui/components/Icon";
import { LoadingIndicator } from "@openai/apps-sdk-ui/components/Indicator";
import { Select, type Option } from "@openai/apps-sdk-ui/components/Select";

import { TextShimmer } from "./text-shimmer/TextShimmer";
import "./ResourceCollection.css";

function joinClassNames(...values: Array<string | undefined | false>) {
  return values.filter(Boolean).join(" ");
}

const RESOURCE_IDENTITY_PALETTES = [
  ["14 90% 62%", "28 96% 80%", "3 44% 24%"],
  ["198 72% 56%", "217 88% 79%", "189 42% 24%"],
  ["263 66% 63%", "291 72% 81%", "242 39% 25%"],
  ["146 49% 52%", "169 66% 78%", "158 38% 23%"],
  ["334 72% 63%", "15 87% 80%", "350 41% 25%"],
] as const;

function resourceIdentityStyle(seed: string): CSSProperties {
  let hash = 2166136261;
  for (const character of seed) {
    hash ^= character.charCodeAt(0);
    hash = Math.imul(hash, 16777619);
  }
  const value = hash >>> 0;
  const [accent, glow, shadow] = RESOURCE_IDENTITY_PALETTES[value % RESOURCE_IDENTITY_PALETTES.length];
  return {
    "--resource-identity-accent": accent,
    "--resource-identity-glow": glow,
    "--resource-identity-shadow": shadow,
    "--resource-identity-x": `${20 + ((value >>> 7) % 61)}%`,
    "--resource-identity-y": `${18 + ((value >>> 15) % 57)}%`,
  } as CSSProperties;
}

export function ResourceIdentityMark({
  seed,
  className,
}: {
  seed: string;
  className?: string;
}) {
  return (
    <span
      className={joinClassNames("resource-card__identity-mark", className)}
      style={resourceIdentityStyle(seed)}
      aria-hidden="true"
    />
  );
}

function ResourceSearchIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 14 14" fill="none" aria-hidden="true" {...props}>
      <g transform="translate(0.875 0.875)">
        <path
          d="M5.869 10.719a4.849 4.849 0 1 0 0-9.698 4.849 4.849 0 0 0 0 9.698Z"
          stroke="currentColor"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        <path
          d="m11.229 11.229-1.021-1.021"
          stroke="currentColor"
          strokeWidth="0.984375"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </g>
    </svg>
  );
}

export function ResourcePageShell({
  className,
  ...props
}: HTMLAttributes<HTMLElement>) {
  return (
    <section
      className={joinClassNames("resource-page", className)}
      {...props}
    />
  );
}

export function ResourcePageHeader({
  title,
  description,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  className?: string;
}) {
  return (
    <header className={joinClassNames("resource-page__header", className)}>
      <h1>{title}</h1>
      {description ? <p>{description}</p> : null}
    </header>
  );
}

export function ResourceDetail({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return <div className={joinClassNames("resource-detail", className)} {...props} />;
}

export function ResourceDetailHeader({
  className,
  ...props
}: HTMLAttributes<HTMLElement>) {
  return <header className={joinClassNames("resource-detail__header", className)} {...props} />;
}

export function ResourceDetailHeading({
  title,
  description,
  backLabel,
  onBack,
}: {
  title: ReactNode;
  description?: ReactNode;
  backLabel: string;
  onBack: () => void;
}) {
  return (
    <div className="resource-detail__heading">
      <button type="button" className="resource-detail__back" onClick={onBack} aria-label={backLabel} title={backLabel}>
        <ArrowLeft aria-hidden="true" />
      </button>
      <div className="resource-detail__heading-copy">
        <h1>{title}</h1>
        {description ? <p>{description}</p> : null}
      </div>
    </div>
  );
}

export function ResourceDetailActions({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return <div className={joinClassNames("resource-detail__actions", className)} {...props} />;
}

export function ResourceDetailBody({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return <div className={joinClassNames("resource-detail__body", className)} {...props} />;
}

export function ResourceDetailSummary({
  className,
  ...props
}: HTMLAttributes<HTMLDListElement>) {
  return <dl className={joinClassNames("resource-detail__summary", className)} {...props} />;
}

export function ResourceDetailSectionHeader({
  title,
  description,
  actions,
  className,
}: {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header className={joinClassNames("resource-detail__section-header", className)}>
      <div>
        <h2>{title}</h2>
        {description ? <p>{description}</p> : null}
      </div>
      {actions}
    </header>
  );
}

export function ResourceToolbar({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={joinClassNames("resource-toolbar", className)}
      {...props}
    />
  );
}

export interface ResourceTabItem<T extends string> {
  id: T;
  label: ReactNode;
  disabled?: boolean;
  panelId?: string;
}

export function ResourceTabs<T extends string>({
  items,
  value,
  onChange,
  ariaLabel,
  idPrefix,
  className,
}: {
  items: readonly ResourceTabItem<T>[];
  value: T;
  onChange: (value: T) => void;
  ariaLabel: string;
  idPrefix: string;
  className?: string;
}) {
  const select = (item: ResourceTabItem<T>) => {
    if (!item.disabled) onChange(item.id);
  };
  const handleKeyDown = (
    event: KeyboardEvent<HTMLButtonElement>,
    item: ResourceTabItem<T>,
  ) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const enabledItems = items.filter((candidate) => !candidate.disabled);
    const currentIndex = enabledItems.findIndex((candidate) => candidate.id === item.id);
    const nextIndex = event.key === "Home"
      ? 0
      : event.key === "End"
        ? enabledItems.length - 1
        : (currentIndex + (event.key === "ArrowRight" ? 1 : -1) + enabledItems.length)
          % enabledItems.length;
    const next = enabledItems[nextIndex];
    if (!next) return;
    onChange(next.id);
    document.getElementById(`${idPrefix}-${next.id}-tab`)?.focus();
  };
  return (
    <nav
      className={joinClassNames("resource-tabs", className)}
      aria-label={ariaLabel}
      role="tablist"
    >
      {items.map((item) => (
        <button
          type="button"
          key={item.id}
          id={`${idPrefix}-${item.id}-tab`}
          className={value === item.id ? "is-active" : undefined}
          role="tab"
          aria-selected={value === item.id}
          aria-controls={item.panelId}
          tabIndex={value === item.id ? 0 : -1}
          disabled={item.disabled}
          onClick={() => select(item)}
          onKeyDown={(event) => handleKeyDown(event, item)}
        >
          {item.label}
        </button>
      ))}
    </nav>
  );
}

export function ResourceSearch({
  className,
  ...props
}: Omit<InputHTMLAttributes<HTMLInputElement>, "type">) {
  return (
    <label className={joinClassNames("resource-search", className)}>
      <ResourceSearchIcon />
      <input type="search" {...props} />
    </label>
  );
}

export type ResourceFilterOption<T extends string> = Option<T>;

const RESOURCE_FILTER_HOVER_OPEN_DELAY = 150;
const RESOURCE_FILTER_HOVER_CLOSE_DELAY = 200;

function toggleResourceFilter(trigger: HTMLElement) {
  trigger.dispatchEvent(new PointerEvent("pointerdown", {
    bubbles: true,
    cancelable: true,
    pointerType: "mouse",
    button: 0,
  }));
}

export function ResourceFilterSelect<T extends string>({
  id,
  ariaLabel,
  value,
  options,
  onChange,
  className,
  disabled = false,
}: {
  id: string;
  ariaLabel: string;
  value: T;
  options: Array<ResourceFilterOption<T>>;
  onChange: (value: T) => void;
  className?: string;
  disabled?: boolean;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const openTimerRef = useRef<number | null>(null);
  const closeTimerRef = useRef<number | null>(null);
  const hoverOpenedRef = useRef(false);

  const clearOpenTimer = useCallback(() => {
    if (openTimerRef.current === null) return;
    window.clearTimeout(openTimerRef.current);
    openTimerRef.current = null;
  }, []);

  const clearCloseTimer = useCallback(() => {
    if (closeTimerRef.current === null) return;
    window.clearTimeout(closeTimerRef.current);
    closeTimerRef.current = null;
  }, []);

  const getTrigger = useCallback(
    () => containerRef.current?.querySelector<HTMLElement>(".resource-filter-select__trigger") ?? null,
    [],
  );

  const closeHoverMenu = useCallback(() => {
    clearCloseTimer();
    const trigger = getTrigger();
    if (hoverOpenedRef.current && trigger?.getAttribute("data-state") === "open") {
      toggleResourceFilter(trigger);
    }
    hoverOpenedRef.current = false;
  }, [clearCloseTimer, getTrigger]);

  const scheduleHoverClose = useCallback(() => {
    if (!hoverOpenedRef.current) return;
    clearCloseTimer();
    closeTimerRef.current = window.setTimeout(
      closeHoverMenu,
      RESOURCE_FILTER_HOVER_CLOSE_DELAY,
    );
  }, [clearCloseTimer, closeHoverMenu]);

  const handleMouseEnter = useCallback((_event: ReactMouseEvent<HTMLDivElement>) => {
    if (
      disabled ||
      !window.matchMedia("(hover: hover) and (pointer: fine)").matches
    ) {
      return;
    }
    clearCloseTimer();
    const trigger = getTrigger();
    if (!trigger || trigger.getAttribute("data-state") === "open") return;
    const activeElement = document.activeElement;
    if (
      activeElement instanceof HTMLElement &&
      activeElement !== trigger &&
      !containerRef.current?.contains(activeElement) &&
      activeElement.matches("input, textarea, [contenteditable='true']")
    ) {
      return;
    }
    clearOpenTimer();
    openTimerRef.current = window.setTimeout(() => {
      const currentTrigger = getTrigger();
      if (!currentTrigger || currentTrigger.getAttribute("data-state") === "open") return;
      hoverOpenedRef.current = true;
      toggleResourceFilter(currentTrigger);
    }, RESOURCE_FILTER_HOVER_OPEN_DELAY);
  }, [clearCloseTimer, clearOpenTimer, disabled, getTrigger]);

  useEffect(() => {
    const handlePointerMove = (event: PointerEvent) => {
      if (!hoverOpenedRef.current) return;
      const trigger = getTrigger();
      if (!trigger || trigger.getAttribute("data-state") !== "open") {
        hoverOpenedRef.current = false;
        clearCloseTimer();
        return;
      }
      const target = event.target;
      if (!(target instanceof Node)) return;
      const menuId = trigger.getAttribute("aria-controls");
      const menu = menuId ? document.getElementById(menuId) : null;
      if (containerRef.current?.contains(target) || menu?.contains(target)) {
        clearCloseTimer();
        return;
      }
      scheduleHoverClose();
    };

    document.addEventListener("pointermove", handlePointerMove, { passive: true });
    return () => {
      document.removeEventListener("pointermove", handlePointerMove);
      clearOpenTimer();
      clearCloseTimer();
    };
  }, [clearCloseTimer, clearOpenTimer, getTrigger, scheduleHoverClose]);

  return (
    <div
      ref={containerRef}
      className={joinClassNames("resource-filter-select", className)}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={() => {
        clearOpenTimer();
        scheduleHoverClose();
      }}
    >
      <label className="sr-only" htmlFor={id}>{ariaLabel}</label>
      <Select
        id={id}
        value={value}
        options={options}
        size="md"
        variant="ghost"
        pill={false}
        block={false}
        align="end"
        listMinWidth={160}
        disabled={disabled}
        triggerClassName="resource-filter-select__trigger"
        onChange={(option) => onChange(option.value)}
      />
    </div>
  );
}

export const ResourceResults = forwardRef<
  HTMLElement,
  HTMLAttributes<HTMLElement>
>(function ResourceResults({ className, ...props }, ref) {
  return (
    <section
      ref={ref}
      className={joinClassNames("resource-results", className)}
      {...props}
    />
  );
});

export function ResourceLoadingState() {
  return (
    <div
      className="resource-loading-state"
      role="status"
      aria-live="polite"
      aria-busy="true"
    >
      <LoadingIndicator size={20} />
      <TextShimmer as="span" duration={2.4}>
        资源加载中，请稍候
      </TextShimmer>
    </div>
  );
}

export function ResourceGrid({
  className,
  ...props
}: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={joinClassNames("resource-grid", className)}
      {...props}
    />
  );
}

export function ResourceCard({
  className,
  footer,
  actions,
  activateLabel,
  onActivate,
  children,
  ...props
}: HTMLAttributes<HTMLElement> & {
  footer?: ReactNode;
  actions?: ReactNode;
  activateLabel?: string;
  onActivate?: () => void;
}) {
  return (
    <article
      className={joinClassNames("resource-card", onActivate && "is-interactive", className)}
      {...props}
    >
      {onActivate && activateLabel ? (
        <button
          type="button"
          className="resource-card__target"
          aria-label={activateLabel}
          title={activateLabel}
          onClick={onActivate}
        />
      ) : null}
      <div className="resource-card__content">{children}</div>
      {footer || actions ? (
        <footer className="resource-card__footer">
          {footer}
          {actions ? <div className="resource-card__actions">{actions}</div> : null}
        </footer>
      ) : null}
    </article>
  );
}

export function ResourceCardAction({
  className,
  iconOnly = false,
  tone = "secondary",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  iconOnly?: boolean;
  tone?: "primary" | "secondary" | "danger";
}) {
  return (
    <button
      type="button"
      className={joinClassNames(
        "resource-card__action",
        `is-${tone}`,
        iconOnly && "is-icon-only",
        className,
      )}
      {...props}
    />
  );
}

export function ResourceCardRevealAction({
  label,
  icon = "arrow",
  tone = "primary",
  className,
  children,
  title,
  ...props
}: Omit<ButtonHTMLAttributes<HTMLButtonElement>, "aria-label"> & {
  label: string;
  icon?: "arrow" | "play" | "plus";
  children?: ReactNode;
  tone?: "primary" | "secondary" | "danger";
}) {
  const defaultIcon = icon === "play"
    ? <PlaySm />
    : icon === "plus"
      ? <PlusLg18pxAdd />
      : <ArrowRight />;

  return (
    <ResourceCardAction
      className={className}
      iconOnly
      tone={tone}
      aria-label={label}
      title={title ?? label}
      {...props}
    >
      {children ?? defaultIcon}
    </ResourceCardAction>
  );
}

export function ResourceCardHeader({
  leading,
  title,
  titleText,
  subtitle,
  status,
}: {
  leading?: ReactNode;
  title: ReactNode;
  titleText?: string;
  subtitle?: ReactNode;
  status?: ReactNode;
}) {
  return (
    <div className="resource-card__header">
      <div className="resource-card__identity">
        {leading}
        <div className="resource-card__title-copy">
          <h3 title={titleText}>{title}</h3>
          {subtitle}
        </div>
      </div>
      {status}
    </div>
  );
}

export function ResourceCardDescription({
  children,
  title,
}: {
  children: ReactNode;
  title?: string;
}) {
  return (
    <p className="resource-card__description" title={title}>
      {children}
    </p>
  );
}

export interface ResourceCardMetadataItem {
  label: ReactNode;
  value: ReactNode;
  title?: string;
  className?: string;
  hideLabel?: boolean;
}

export function ResourceCardMetadata({
  items,
  className,
}: {
  items: readonly ResourceCardMetadataItem[];
  className?: string;
}) {
  return (
    <dl className={joinClassNames("resource-card__metadata", className)}>
      {items.map((item, index) => (
        <div
          key={`${String(item.label)}:${index}`}
          className={item.className}
        >
          <dt className={item.hideLabel ? "sr-only" : undefined}>{item.label}</dt>
          <dd title={item.title}>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function ResourceCreateCard({
  className,
  icon,
  children,
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  icon: ReactNode;
}) {
  return (
    <button
      type="button"
      className={joinClassNames("resource-create-card", className)}
      {...props}
    >
      <span className="resource-create-card__icon" aria-hidden="true">
        {icon}
      </span>
      <span>{children}</span>
    </button>
  );
}

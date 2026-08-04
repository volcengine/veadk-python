import { useEffect, useState, type SVGProps } from "react";

import {
  Carousel,
  type CarouselApi,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
} from "../carousel/Carousel";
import "./new-chat-feature-carousel.css";

type FeatureIllustrationKind = "agents" | "build" | "search" | "tools";

const FEATURE_CARDS: ReadonlyArray<{
  title: string;
  description: string;
  illustration: FeatureIllustrationKind;
}> = [
  { title: "随心应变", description: "支持多类 Agent", illustration: "agents" },
  { title: "一键成型", description: "自动构建 Agent", illustration: "build" },
  { title: "一搜即达", description: "全局搜索", illustration: "search" },
  { title: "开箱即用", description: "丰富内置工具", illustration: "tools" },
];

function CloseIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true" {...props}>
      <path
        d="m4.25 4.25 7.5 7.5m0-7.5-7.5 7.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

function FeatureIllustration({ kind }: { kind: FeatureIllustrationKind }) {
  if (kind === "agents") {
    return (
      <svg className="new-chat-feature-card__illustration" viewBox="0 0 86 64" aria-hidden="true">
        <g className="new-chat-feature-card__illustration-connectors">
          <path d="M43 27.5V33.5H22V38.5M43 33.5H64V38.5" />
        </g>
        <g className="new-chat-feature-card__illustration-surfaces">
          <rect x="33" y="6.5" width="20" height="21" rx="6" />
          <rect x="9" y="38.5" width="26" height="19" rx="6" />
          <rect x="51" y="38.5" width="26" height="19" rx="6" />
        </g>
        <g className="new-chat-feature-card__illustration-details">
          <circle className="new-chat-feature-card__illustration-dot" cx="40" cy="14.5" r="1.25" />
          <circle className="new-chat-feature-card__illustration-dot" cx="46" cy="14.5" r="1.25" />
          <path d="M39.5 21h7M17 46.5h10M17 51.5h7M59 46.5h10M59 51.5h7" />
        </g>
      </svg>
    );
  }

  if (kind === "build") {
    return (
      <svg className="new-chat-feature-card__illustration" viewBox="0 0 86 64" aria-hidden="true">
        <g className="new-chat-feature-card__illustration-connectors">
          <path d="M26.5 39H36M50 39h9.5" />
        </g>
        <g className="new-chat-feature-card__illustration-surfaces">
          <rect x="5.5" y="7.5" width="75" height="49" rx="7.5" />
          <rect x="12.5" y="31.5" width="14" height="15" rx="4" />
          <rect x="36" y="31.5" width="14" height="15" rx="4" />
          <rect x="59.5" y="31.5" width="14" height="15" rx="4" />
        </g>
        <g className="new-chat-feature-card__illustration-details">
          <path d="M6 20.5h74M13.5 14h.01m6 0h.01m6 0h.01M17 39h5m18.5 0h5m18-1 2.5 2.5 4-5" />
        </g>
      </svg>
    );
  }

  if (kind === "search") {
    return (
      <svg className="new-chat-feature-card__illustration" viewBox="0 0 86 64" aria-hidden="true">
        <g className="new-chat-feature-card__illustration-surfaces">
          <rect x="7.5" y="9.5" width="41" height="16" rx="5" />
          <rect x="7.5" y="35.5" width="34" height="18" rx="5" />
          <circle cx="61" cy="33" r="10.5" />
        </g>
        <g className="new-chat-feature-card__illustration-details">
          <path d="M14.5 16h21M14.5 21h14M14.5 42.5h17M14.5 47.5h11M68.5 40.5 77 49" />
        </g>
      </svg>
    );
  }

  return (
    <svg className="new-chat-feature-card__illustration" viewBox="0 0 86 64" aria-hidden="true">
      <g className="new-chat-feature-card__illustration-surfaces">
        <rect x="8.5" y="7.5" width="29" height="21" rx="6" />
        <rect x="48.5" y="7.5" width="29" height="21" rx="6" />
        <rect x="8.5" y="35.5" width="29" height="21" rx="6" />
        <rect x="48.5" y="35.5" width="29" height="21" rx="6" />
      </g>
      <g className="new-chat-feature-card__illustration-details">
        <path d="M23 13.5v9m-4.5-4.5h9M56.5 14.5h13M56.5 21.5h13M16.5 42.5h13M16.5 49.5h9M56.5 42.5h13M56.5 49.5h13" />
      </g>
    </svg>
  );
}

export function NewChatFeatureCarousel() {
  const [api, setApi] = useState<CarouselApi>();
  const [pointerPaused, setPointerPaused] = useState(false);
  const [focusPaused, setFocusPaused] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    if (!visible) return;
    const mediaQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const updateMotionPreference = () => setReducedMotion(mediaQuery.matches);
    updateMotionPreference();
    mediaQuery.addEventListener("change", updateMotionPreference);
    return () => mediaQuery.removeEventListener("change", updateMotionPreference);
  }, [visible]);

  useEffect(() => {
    if (!visible || !api || pointerPaused || focusPaused || reducedMotion) return;
    const intervalId = window.setInterval(() => api.scrollNext(), 6_000);
    return () => window.clearInterval(intervalId);
  }, [api, focusPaused, pointerPaused, reducedMotion, visible]);

  if (!visible) return null;

  return (
    <Carousel
      className="new-chat-feature-carousel"
      opts={{ align: "start", loop: true }}
      setApi={setApi}
      aria-label="新特性预览"
      onPointerEnter={() => setPointerPaused(true)}
      onPointerLeave={() => setPointerPaused(false)}
      onFocusCapture={() => setFocusPaused(true)}
      onBlurCapture={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setFocusPaused(false);
      }}
    >
      <CarouselPrevious aria-label="上一张新特性" />
      <CarouselContent>
        {FEATURE_CARDS.map((card, index) => (
          <CarouselItem
            key={card.title}
            aria-label={`${index + 1} / ${FEATURE_CARDS.length}`}
          >
            <article className="new-chat-feature-card">
              <div className="new-chat-feature-card__copy">
                <strong>{card.title}</strong>
                <span>{card.description}</span>
              </div>
              <FeatureIllustration kind={card.illustration} />
            </article>
          </CarouselItem>
        ))}
      </CarouselContent>
      <button
        type="button"
        className="new-chat-feature-carousel__close"
        aria-label="关闭新特性轮播"
        onClick={() => setVisible(false)}
      >
        <CloseIcon />
      </button>
      <CarouselNext aria-label="下一张新特性" />
    </Carousel>
  );
}

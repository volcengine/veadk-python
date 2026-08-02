import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselNext,
  CarouselPrevious,
} from "../carousel/Carousel";
import "./new-chat-feature-carousel.css";

const FEATURE_CARDS = [
  { title: "新特性 01", description: "功能预览占位" },
  { title: "新特性 02", description: "功能预览占位" },
  { title: "新特性 03", description: "功能预览占位" },
  { title: "新特性 04", description: "功能预览占位" },
] as const;

export function NewChatFeatureCarousel() {
  return (
    <Carousel
      className="new-chat-feature-carousel"
      opts={{ align: "start", loop: false }}
      aria-label="新特性预览"
    >
      <CarouselPrevious aria-label="上一张新特性" />
      <CarouselContent>
        {FEATURE_CARDS.map((card, index) => (
          <CarouselItem
            key={card.title}
            aria-label={`${index + 1} / ${FEATURE_CARDS.length}`}
          >
            <article className="new-chat-feature-card">
              <span className="new-chat-feature-card__index" aria-hidden="true">
                {String(index + 1).padStart(2, "0")}
              </span>
              <div>
                <strong>{card.title}</strong>
                <span>{card.description}</span>
              </div>
            </article>
          </CarouselItem>
        ))}
      </CarouselContent>
      <CarouselNext aria-label="下一张新特性" />
    </Carousel>
  );
}

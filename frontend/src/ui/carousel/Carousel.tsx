import * as React from "react";
import useEmblaCarousel, {
  type UseEmblaCarouselType,
} from "embla-carousel-react";
import "./carousel.css";

export type CarouselApi = UseEmblaCarouselType[1];
type UseCarouselParameters = Parameters<typeof useEmblaCarousel>;
type CarouselOptions = UseCarouselParameters[0];
type CarouselPlugin = UseCarouselParameters[1];

type CarouselProps = {
  opts?: CarouselOptions;
  plugins?: CarouselPlugin;
  orientation?: "horizontal" | "vertical";
  setApi?: (api: CarouselApi) => void;
};

type CarouselContextProps = {
  carouselRef: ReturnType<typeof useEmblaCarousel>[0];
  api: ReturnType<typeof useEmblaCarousel>[1];
  scrollPrev: () => void;
  scrollNext: () => void;
  canScrollPrev: boolean;
  canScrollNext: boolean;
} & CarouselProps;

const CarouselContext = React.createContext<CarouselContextProps | null>(null);

function classNames(...values: Array<string | undefined>) {
  return values.filter(Boolean).join(" ");
}

function useCarousel() {
  const context = React.useContext(CarouselContext);
  if (!context) throw new Error("useCarousel must be used within a <Carousel />");
  return context;
}

export function Carousel({
  orientation = "horizontal",
  opts,
  setApi,
  plugins,
  className,
  children,
  ...props
}: React.ComponentProps<"div"> & CarouselProps) {
  const [carouselRef, api] = useEmblaCarousel(
    {
      ...opts,
      axis: orientation === "horizontal" ? "x" : "y",
    },
    plugins,
  );
  const [canScrollPrev, setCanScrollPrev] = React.useState(false);
  const [canScrollNext, setCanScrollNext] = React.useState(false);

  const onSelect = React.useCallback((nextApi: CarouselApi) => {
    if (!nextApi) return;
    setCanScrollPrev(nextApi.canScrollPrev());
    setCanScrollNext(nextApi.canScrollNext());
  }, []);

  const scrollPrev = React.useCallback(() => api?.scrollPrev(), [api]);
  const scrollNext = React.useCallback(() => api?.scrollNext(), [api]);

  const handleKeyDown = React.useCallback(
    (event: React.KeyboardEvent<HTMLDivElement>) => {
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        scrollPrev();
      } else if (event.key === "ArrowRight") {
        event.preventDefault();
        scrollNext();
      }
    },
    [scrollNext, scrollPrev],
  );

  React.useEffect(() => {
    if (api && setApi) setApi(api);
  }, [api, setApi]);

  React.useEffect(() => {
    if (!api) return;
    onSelect(api);
    api.on("reInit", onSelect);
    api.on("select", onSelect);
    return () => {
      api.off("reInit", onSelect);
      api.off("select", onSelect);
    };
  }, [api, onSelect]);

  return (
    <CarouselContext.Provider
      value={{
        carouselRef,
        api,
        opts,
        orientation,
        plugins,
        setApi,
        scrollPrev,
        scrollNext,
        canScrollPrev,
        canScrollNext,
      }}
    >
      <div
        onKeyDownCapture={handleKeyDown}
        className={classNames("ui-carousel", className)}
        role="region"
        aria-roledescription="carousel"
        aria-orientation={orientation}
        data-slot="carousel"
        {...props}
      >
        {children}
      </div>
    </CarouselContext.Provider>
  );
}

export function CarouselContent({
  className,
  ...props
}: React.ComponentProps<"div">) {
  const { carouselRef, orientation } = useCarousel();
  return (
    <div
      ref={carouselRef}
      className="ui-carousel__viewport"
      data-slot="carousel-content"
    >
      <div
        className={classNames(
          "ui-carousel__track",
          orientation === "vertical" ? "is-vertical" : undefined,
          className,
        )}
        {...props}
      />
    </div>
  );
}

export function CarouselItem({
  className,
  ...props
}: React.ComponentProps<"div">) {
  const { orientation } = useCarousel();
  return (
    <div
      role="group"
      aria-roledescription="slide"
      data-slot="carousel-item"
      className={classNames(
        "ui-carousel__item",
        orientation === "vertical" ? "is-vertical" : undefined,
        className,
      )}
      {...props}
    />
  );
}

function CarouselArrowIcon({ direction }: { direction: "left" | "right" }) {
  return (
    <svg viewBox="0 0 16 16" fill="none" aria-hidden="true">
      <path
        d={direction === "left" ? "m10 3.75-4.25 4.25L10 12.25" : "m6 3.75 4.25 4.25L6 12.25"}
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function CarouselPrevious({
  className,
  ...props
}: React.ComponentProps<"button">) {
  const { orientation, scrollPrev, canScrollPrev } = useCarousel();
  return (
    <button
      type="button"
      data-slot="carousel-previous"
      className={classNames(
        "ui-carousel__control ui-carousel__control--previous",
        orientation === "vertical" ? "is-vertical" : undefined,
        className,
      )}
      disabled={!canScrollPrev}
      onClick={scrollPrev}
      aria-label="上一张"
      {...props}
    >
      <CarouselArrowIcon direction="left" />
    </button>
  );
}

export function CarouselNext({
  className,
  ...props
}: React.ComponentProps<"button">) {
  const { orientation, scrollNext, canScrollNext } = useCarousel();
  return (
    <button
      type="button"
      data-slot="carousel-next"
      className={classNames(
        "ui-carousel__control ui-carousel__control--next",
        orientation === "vertical" ? "is-vertical" : undefined,
        className,
      )}
      disabled={!canScrollNext}
      onClick={scrollNext}
      aria-label="下一张"
      {...props}
    >
      <CarouselArrowIcon direction="right" />
    </button>
  );
}

export { useCarousel };

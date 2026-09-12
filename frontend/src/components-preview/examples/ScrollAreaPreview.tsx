import { useState } from "react";
import { ScrollArea } from "../../components/primitives/ScrollArea";
import { ComponentApi } from "../api/ComponentApi";
import "./ScrollAreaPreview.css";

export function ScrollAreaPreview() {
  const [count, setCount] = useState(20);
  async function loadMore(signal: AbortSignal) {
    await new Promise<void>((resolve, reject) => {
      if (signal.aborted) { reject(signal.reason); return; }
      const abort = () => { clearTimeout(timer); reject(signal.reason); };
      const timer = setTimeout(() => { signal.removeEventListener("abort", abort); resolve(); }, 700);
      signal.addEventListener("abort", abort, { once: true });
    });
    if (!signal.aborted) setCount(current => Math.min(current + 10, 50));
  }
  return <section aria-labelledby="scroll-area-preview-title">
    <h2 id="scroll-area-preview-title" className="component-preview-title">Scroll Area</h2>
    <div className="scroll-area-preview__examples">
      <section aria-labelledby="scroll-area-vertical-title">
        <h3 id="scroll-area-vertical-title" className="scroll-area-preview__title">纵向滚动与加载</h3>
        <ScrollArea hasMore={count < 50} onLoadMore={loadMore} maxHeight={240} className="scroll-area-preview" contentClassName="scroll-area-preview__items" tabIndex={0} role="region" aria-label="滚动列表">
          {Array.from({ length: count }, (_, index) => <div className="scroll-area-preview__item" key={index}>Item {String(index + 1).padStart(2, "0")}</div>)}
        </ScrollArea>
      </section>
      <section aria-labelledby="scroll-area-horizontal-title">
        <h3 id="scroll-area-horizontal-title" className="scroll-area-preview__title">横向滚动</h3>
        <ScrollArea orientation="horizontal" className="scroll-area-preview" contentClassName="scroll-area-preview__items scroll-area-preview__items--horizontal" tabIndex={0} role="region" aria-label="横向滚动列表">
          {Array.from({ length: 12 }, (_, index) => <div className="scroll-area-preview__item" key={index}>Item {String(index + 1).padStart(2, "0")}</div>)}
        </ScrollArea>
      </section>
    </div>
    <ComponentApi names={["ScrollArea"]} />
  </section>;
}

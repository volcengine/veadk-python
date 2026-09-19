import { useState } from "react";
import { ScrollArea } from "../../components/primitives/ScrollArea";
import { Button } from "../../components/primitives/Button";

import "./ScrollAreaPreview.css";

export function ScrollAreaPreview() {
  const [count, setCount] = useState(20);
  const [fadeEdges, setFadeEdges] = useState(true);
  async function loadMore(signal: AbortSignal) {
    await new Promise<void>((resolve, reject) => {
      if (signal.aborted) { reject(signal.reason); return; }
      const abort = () => { clearTimeout(timer); reject(signal.reason); };
      const timer = setTimeout(() => { signal.removeEventListener("abort", abort); resolve(); }, 700);
      signal.addEventListener("abort", abort, { once: true });
    });
    if (!signal.aborted) setCount(current => Math.min(current + 10, 50));
  }
  return <section aria-labelledby="component-page-title">
    <div className="scroll-area-preview__examples">
      <section aria-labelledby="scroll-area-fade-title">
        <h2 data-preview-heading tabIndex={-1} id="scroll-area-fade-title" className="scroll-area-preview__title">上下渐隐</h2>
        <Button variant="link" aria-pressed={fadeEdges} onClick={() => setFadeEdges(value => !value)}>{fadeEdges ? "关闭渐隐" : "开启渐隐"}</Button>
        <ScrollArea fadeEdges={fadeEdges} maxHeight={240} className="scroll-area-preview" contentClassName="scroll-area-preview__items" tabIndex={0} role="region" aria-label="上下渐隐列表">
          {Array.from({ length: 20 }, (_, index) => <div className="scroll-area-preview__item" key={index}>Item {String(index + 1).padStart(2, "0")}</div>)}
        </ScrollArea>
      </section>
      <section aria-labelledby="scroll-area-vertical-title">
        <h2 data-preview-heading tabIndex={-1} id="scroll-area-vertical-title" className="scroll-area-preview__title">纵向滚动与加载</h2>
        <ScrollArea hasMore={count < 50} onLoadMore={loadMore} maxHeight={240} className="scroll-area-preview" contentClassName="scroll-area-preview__items" tabIndex={0} role="region" aria-label="滚动列表">
          {Array.from({ length: count }, (_, index) => <div className="scroll-area-preview__item" key={index}>Item {String(index + 1).padStart(2, "0")}</div>)}
        </ScrollArea>
      </section>
      <section aria-labelledby="scroll-area-horizontal-title">
        <h2 data-preview-heading tabIndex={-1} id="scroll-area-horizontal-title" className="scroll-area-preview__title">横向滚动</h2>
        <ScrollArea orientation="horizontal" className="scroll-area-preview" contentClassName="scroll-area-preview__items scroll-area-preview__items--horizontal" tabIndex={0} role="region" aria-label="横向滚动列表">
          {Array.from({ length: 12 }, (_, index) => <div className="scroll-area-preview__item" key={index}>Item {String(index + 1).padStart(2, "0")}</div>)}
        </ScrollArea>
      </section>
    </div>
  </section>;
}

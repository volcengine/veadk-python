import { useEffect, useRef, useState, type RefObject } from "react";
import { ScrollArea } from "../components/primitives/ScrollArea";

type Heading = { id: string; label: string };

export function PreviewContents({ scrollRef, componentId, sectionId }: {
  scrollRef: RefObject<HTMLDivElement | null>;
  componentId: string;
  sectionId: string;
}) {
  const [headings, setHeadings] = useState<Heading[]>([]);
  const [activeId, setActiveId] = useState("");
  const mobileRef = useRef<HTMLDetailsElement>(null);

  useEffect(() => {
    const scroll = scrollRef.current;
    if (!scroll) return;
    const nodes = Array.from(scroll.querySelectorAll<HTMLHeadingElement>("h2[data-preview-heading]"));
    setHeadings(nodes.map(node => ({ id: node.id, label: node.textContent?.trim() || "" })));
    let frame = 0;
    function updateActive() {
      frame = 0;
      const top = scroll!.getBoundingClientRect().top + 40;
      let current = nodes[0];
      for (const node of nodes) {
        if (node.getBoundingClientRect().top <= top) current = node;
      }
      setActiveId(current?.id || "");
    }
    function scheduleUpdate() {
      if (!frame) frame = requestAnimationFrame(updateActive);
    }
    scroll.addEventListener("scroll", scheduleUpdate, { passive: true });
    const observer = new ResizeObserver(scheduleUpdate);
    observer.observe(scroll);
    if (scroll.firstElementChild) observer.observe(scroll.firstElementChild);
    updateActive();
    return () => {
      scroll.removeEventListener("scroll", scheduleUpdate);
      observer.disconnect();
      cancelAnimationFrame(frame);
    };
  }, [componentId, scrollRef]);

  useEffect(() => {
    const scroll = scrollRef.current;
    if (!scroll) return;
    if (mobileRef.current) mobileRef.current.open = false;
    const heading = Array.from(scroll.querySelectorAll<HTMLHeadingElement>("h2[data-preview-heading]")).find(node => node.id === sectionId);
    if (heading) {
      heading.tabIndex = -1;
      heading.focus({ preventScroll: true });
      scroll.scrollTo({ top: heading.getBoundingClientRect().top - scroll.getBoundingClientRect().top + scroll.scrollTop - 24 });
      setActiveId(heading.id);
    } else {
      scroll.scrollTo({ top: 0 });
    }
  }, [componentId, sectionId, scrollRef]);

  const links = <nav aria-label="本页目录">
    {headings.map(heading => <a key={heading.id} href={`#${componentId}/${heading.id}`} aria-current={activeId === heading.id ? "location" : undefined}
      onClick={() => {
        if (mobileRef.current) mobileRef.current.open = false;
        if (sectionId === heading.id) {
          const scroll = scrollRef.current;
          const target = scroll?.querySelector<HTMLHeadingElement>(`[id="${heading.id}"]`);
          if (scroll && target) {
            target.tabIndex = -1;
            target.focus({ preventScroll: true });
            scroll.scrollTo({ top: target.getBoundingClientRect().top - scroll.getBoundingClientRect().top + scroll.scrollTop - 24 });
          }
        }
      }}>{heading.label}</a>)}
  </nav>;

  return <>
    <ScrollArea className="components-preview-contents" role="complementary" aria-label="本页目录">
      <p className="components-preview-contents-label">本页目录</p>
      {links}
    </ScrollArea>
    <details ref={mobileRef} className="components-preview-contents-mobile">
      <summary>本页目录</summary>
      {links}
    </details>
  </>;
}

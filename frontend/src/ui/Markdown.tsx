import { memo } from "react";
import { Maximize2 } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { PhotoView } from "react-photo-view";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import "highlight.js/styles/github.css";

/** Reusable GFM markdown renderer used by both user and assistant message
 *  bodies. Styled via plain CSS (`.md` in styles.css) to match the theme;
 *  syntax highlighting comes from rehype-highlight (highlight.js).
 *
 *  Streaming-safe: re-renders cleanly as `text` grows. Links open in a new
 *  tab. Memoized so unrelated turn re-renders don't re-parse the tree. */
function MarkdownImpl({ text, className }: { text: string; className?: string }) {
  return (
    <div className={className ? `md ${className}` : "md"}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeHighlight]}
        components={{
          a: ({ node, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" />
          ),
          img: ({ node, src, alt, ...props }) => {
            const image = (
              <img {...props} src={src} alt={alt ?? ""} loading="lazy" />
            );
            if (!src) return image;
            return (
              <PhotoView src={src}>
                <button
                  type="button"
                  className="image-preview-trigger"
                  aria-label={`放大预览：${alt || "图片"}`}
                >
                  {image}
                  <span className="image-preview-hint" aria-hidden="true">
                    <Maximize2 />
                  </span>
                </button>
              </PhotoView>
            );
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}

export const Markdown = memo(MarkdownImpl);

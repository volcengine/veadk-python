import { memo, useState } from "react";
import { Maximize2, X, Download } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { PhotoView } from "react-photo-view";
import remarkGfm from "remark-gfm";
import rehypeHighlight from "rehype-highlight";
import rehypeRaw from "rehype-raw";
import "highlight.js/styles/github.css";

interface VideoData {
  src: string;
  title?: string;
}

const VIDEO_EXTENSIONS = [".mp4", ".webm", ".mov", ".m4v", ".ogg", ".avi"];

function isVideoUrl(url: string): boolean {
  if (!url) return false;
  try {
    const urlLower = url.toLowerCase();
    return VIDEO_EXTENSIONS.some((ext) => urlLower.includes(ext));
  } catch {
    return false;
  }
}

function isVideoLink(node: any): boolean {
  const href = node?.properties?.href;
  if (!href) return false;

  // Check if the URL has a video extension
  if (isVideoUrl(href)) return true;

  // Also check if the link text looks like a video file
  const children = node?.children;
  if (children && Array.isArray(children)) {
    const text = children
      .map((c: any) => c?.value || "")
      .join("")
      .toLowerCase();
    return VIDEO_EXTENSIONS.some((ext) => text.includes(ext));
  }
  return false;
}

/** Reusable GFM markdown renderer used by both user and assistant message
 *  bodies. Styled via plain CSS (`.md` in styles.css) to match the theme;
 *  syntax highlighting comes from rehype-highlight (highlight.js).
 *
 *  Streaming-safe: re-renders cleanly as `text` grows. Links open in a new
 *  tab. Memoized so unrelated turn re-renders don't re-parse the tree. */
function MarkdownImpl({ text, className }: { text: string; className?: string }) {
  const [videoViewerOpen, setVideoViewerOpen] = useState<VideoData | null>(null);

  // Extract video src from props or source children
  const extractVideoSrc = (props: any, children: any): string => {
    if (props.src) return props.src;
    // Try to find src from source children if present
    if (children) {
      const findSource = (child: any): string | null => {
        if (!child) return null;
        if (child.type === "source" && child.properties?.src) {
          return child.properties.src;
        }
        if (child.children) {
          for (const c of child.children) {
            const found = findSource(c);
            if (found) return found;
          }
        }
        return null;
      };
      const sourceSrc = findSource({ children });
      if (sourceSrc) return sourceSrc;
    }
    return "";
  };

  // Extract video filename from URL for display
  const getVideoFilename = (src: string): string => {
    try {
      const url = new URL(src);
      const pathParts = url.pathname.split("/");
      const filename = pathParts[pathParts.length - 1];
      return filename || "video.mp4";
    } catch {
      return "video.mp4";
    }
  };

  // Extract link text from node children
  const getLinkText = (children: any): string => {
    if (!children) return "video";
    if (Array.isArray(children)) {
      return children.map((c: any) => c?.value || "").join("") || "video";
    }
    return children?.value || "video";
  };

  return (
    <div className={className ? `md ${className}` : "md"}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        rehypePlugins={[rehypeRaw, rehypeHighlight]}
        components={{
          a: ({ node, ...props }) => {
            const href = props.href;
            if (href && (isVideoUrl(href) || isVideoLink(node))) {
              const videoSrc = href;
              const linkText = getLinkText(node?.children);
              return (
                <div className="video-container">
                  <button
                    type="button"
                    className="video-preview-trigger"
                    aria-label={`点击播放视频: ${linkText}`}
                    onClick={() => setVideoViewerOpen({ src: videoSrc, title: linkText })}
                  >
                    <video
                      src={videoSrc}
                      playsInline
                      className="video-thumbnail"
                      preload="metadata"
                    />
                    <span className="video-preview-hint" aria-hidden="true">
                      <Maximize2 />
                    </span>
                  </button>
                  <div className="video-caption">
                    <a
                      href={videoSrc}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="video-link-text"
                    >
                      {linkText}
                    </a>
                  </div>
                </div>
              );
            }
            return <a {...props} target="_blank" rel="noopener noreferrer" />;
          },
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
          video: ({ node, src, children, ...props }) => {
            const videoSrc = extractVideoSrc({ src }, children);
            if (!videoSrc) {
              // If no src found, render as-is with controls
              return (
                <video
                  src={src}
                  controls
                  playsInline
                  className="video-inline"
                  {...props}
                >
                  {children}
                </video>
              );
            }
            return (
              <div className="video-container">
                <button
                  type="button"
                  className="video-preview-trigger"
                  aria-label="点击放大视频"
                  onClick={() => setVideoViewerOpen({ src: videoSrc })}
                >
                  <video
                    src={videoSrc}
                    {...props}
                    playsInline
                    className="video-thumbnail"
                  >
                    {children}
                  </video>
                  <span className="video-preview-hint" aria-hidden="true">
                    <Maximize2 />
                  </span>
                </button>
              </div>
            );
          },
        }}
      >
        {text}
      </ReactMarkdown>

      {/* Video viewer modal */}
      {videoViewerOpen && (
        <div
          className="video-viewer-backdrop"
          role="dialog"
          aria-modal="true"
          aria-label="视频预览"
          onClick={() => setVideoViewerOpen(null)}
        >
          <div className="video-viewer" onClick={(e) => e.stopPropagation()}>
            <div className="video-viewer-header">
              <div className="video-viewer-title">
                {videoViewerOpen.title || getVideoFilename(videoViewerOpen.src)}
              </div>
              <nav className="video-viewer-nav">
                <a
                  href={videoViewerOpen.src}
                  download={videoViewerOpen.title || getVideoFilename(videoViewerOpen.src)}
                  aria-label="下载视频"
                  title="下载视频"
                  className="video-viewer-download"
                >
                  <Download />
                </a>
                <button
                  type="button"
                  className="video-viewer-close"
                  aria-label="关闭"
                  onClick={() => setVideoViewerOpen(null)}
                >
                  <X />
                </button>
              </nav>
            </div>
            <div className="video-viewer-body">
              <video
                src={videoViewerOpen.src}
                controls
                autoPlay
                playsInline
                className="video-fullscreen"
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export const Markdown = memo(MarkdownImpl);

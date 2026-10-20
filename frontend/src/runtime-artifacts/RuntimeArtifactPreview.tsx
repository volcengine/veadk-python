import { useEffect, useRef, useState } from "react";
import { getRuntimeArtifact, MAX_ARTIFACT_PREVIEW_BYTES, type RuntimeArtifact, type RuntimeArtifactScope } from "../adk/runtimeArtifacts";
import { Button } from "../components/primitives/Button";
import { EmptyState } from "../components/primitives/EmptyState";
import { ErrorState } from "../components/primitives/ErrorState";
import { ScrollArea } from "../components/primitives/ScrollArea";
import { CodeBlock } from "../components/composites/CodeBlock";
import { ConversationMarkdown } from "../components/ai-app/ConversationFlow/ConversationRichContent";
import { TextShimmer } from "../ui/text-shimmer/TextShimmer";
import { artifactPreviewKind, artifactSize, prepareArtifactHtml } from "./artifactPreview";
import { ArtifactDownloadIcon } from "./RuntimeArtifactsIcons";

interface PreviewContent { text?: string; url?: string }

export function RuntimeArtifactPreview({ scope, file, loadPreview }: { scope: RuntimeArtifactScope; file?: RuntimeArtifact; loadPreview: (path: string) => Promise<Blob> }) {
  const [content, setContent] = useState<PreviewContent | null>(null);
  const [error, setError] = useState("");
  const [imageError, setImageError] = useState("");
  const [loadingImages, setLoadingImages] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState("");
  const [zoom, setZoom] = useState(1);
  const downloadController = useRef<AbortController | null>(null);
  const downloadUrls = useRef(new Map<number, string>());
  const kind = file ? artifactPreviewKind(file.mimeType, file.path) : "download";
  const tooLarge = Boolean(file && file.sizeBytes > MAX_ARTIFACT_PREVIEW_BYTES);

  useEffect(() => {
    if (!file || kind === "download" || tooLarge) return;
    const controller = new AbortController();
    let objectUrl: string | undefined;
    setContent(null);
    setError("");
    setImageError("");
    setLoadingImages(false);
    let bodyReady = false;
    void loadPreview(file.path).then(async blob => {
      if (controller.signal.aborted) return;
      if (kind === "image") {
        objectUrl = URL.createObjectURL(blob);
        if (!controller.signal.aborted) setContent({ url: objectUrl });
        else URL.revokeObjectURL(objectUrl);
      } else {
        const text = await blob.text();
        if (controller.signal.aborted) return;
        const preview = kind === "html" ? await prepareArtifactHtml(text, file.path, path => {
          if (controller.signal.aborted) throw new DOMException("Aborted", "AbortError");
          return loadPreview(path);
        }, html => {
          bodyReady = true;
          if (!controller.signal.aborted) { setContent({ text: html }); setLoadingImages(true); }
        }) : text;
        if (!controller.signal.aborted) { setContent({ text: preview }); setLoadingImages(false); }
      }
    }).catch(cause => {
      if (!controller.signal.aborted) {
        const message = cause instanceof Error ? cause.message : "无法加载文件，请重试";
        if (bodyReady) setImageError(message);
        else setError(message);
        setLoadingImages(false);
      }
    });
    return () => { controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl); };
  }, [loadPreview, file?.path, file?.updatedAt, kind, tooLarge, attempt]);

  useEffect(() => { setZoom(1); }, [file?.path]);

  useEffect(() => {
    return () => {
      downloadController.current?.abort();
      for (const [timer, url] of downloadUrls.current) { clearTimeout(timer); URL.revokeObjectURL(url); }
      downloadUrls.current.clear();
    };
  }, []);

  async function download() {
    if (!file || downloading) return;
    const controller = new AbortController();
    downloadController.current = controller;
    setDownloading(true);
    setDownloadError("");
    try {
      const blob = await getRuntimeArtifact(scope, file.path, controller.signal, true);
      if (controller.signal.aborted) return;
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = url;
      anchor.download = file.name;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      const timer = window.setTimeout(() => { URL.revokeObjectURL(url); downloadUrls.current.delete(timer); }, 1000);
      downloadUrls.current.set(timer, url);
    } catch (cause) {
      if (!controller.signal.aborted) setDownloadError(cause instanceof Error ? cause.message : "下载失败，请重试");
    } finally {
      if (!controller.signal.aborted) setDownloading(false);
    }
  }

  if (!file) return <div className="runtime-artifact-preview__empty"><EmptyState title="选择文件查看预览" description="从左侧目录选择当前会话的产物" /></div>;
  return <section className="runtime-artifact-preview" aria-label={`${file.name} 预览`}>
    <header className="runtime-artifact-preview__header">
      <div className="runtime-artifact-preview__identity"><span title={file.path}>{file.path}</span><small>{artifactSize(file.sizeBytes)}</small></div>
      <Button variant="ghost" loading={downloading} startIcon={<ArtifactDownloadIcon />} onClick={() => void download()}>下载</Button>
    </header>
    {downloadError && <div className="runtime-artifact-preview__error" role="alert">{downloadError}</div>}
    {loadingImages && <div className="runtime-artifact-preview__resource-status" role="status"><TextShimmer>正在加载图片</TextShimmer></div>}
    {imageError && <div className="runtime-artifact-preview__error" role="alert">图片暂未加载：{imageError} <Button variant="ghost" onClick={() => setAttempt(value => value + 1)}>重试图片</Button></div>}
    {tooLarge || kind === "download" ? <div className="runtime-artifact-preview__empty"><EmptyState title={tooLarge ? "文件较大" : "此格式暂不支持预览"} description={tooLarge ? "超过 5 MB 的文件请下载后查看" : "下载文件后使用对应应用打开"} /></div>
      : error ? <div className="runtime-artifact-preview__empty"><ErrorState title="预览加载失败" description={error} /><Button variant="outline" onClick={() => setAttempt(value => value + 1)}>重试</Button></div>
        : !content ? <div className="runtime-artifact-preview__empty" role="status"><TextShimmer>正在加载预览</TextShimmer></div>
          : kind === "html" ? <iframe className="runtime-artifact-preview__html" title={`${file.name} HTML 预览`} sandbox="" referrerPolicy="no-referrer" srcDoc={content.text} />
            : kind === "image" ? <>
              <ScrollArea orientation="both" className="runtime-artifact-preview__image-scroll" tabIndex={0} aria-label="图片预览滚动区域"><img className="runtime-artifact-preview__image" src={content.url} alt={file.name} style={{ width: `${zoom * 100}%`, maxWidth: zoom === 1 ? "100%" : "none" }} onError={() => setError("无法显示此图片，请下载后查看")} /></ScrollArea>
              <div className="runtime-artifact-preview__zoom" role="group" aria-label="图片缩放"><Button variant="ghost" disabled={zoom <= .5} onClick={() => setZoom(value => Math.max(.5, value - .25))}>缩小</Button><span>{Math.round(zoom * 100)}%</span><Button variant="ghost" disabled={zoom >= 3} onClick={() => setZoom(value => Math.min(3, value + .25))}>放大</Button><Button variant="ghost" onClick={() => setZoom(1)}>适应宽度</Button></div>
            </>
              : <ScrollArea className="runtime-artifact-preview__document" tabIndex={0} aria-label="文件预览内容">{kind === "markdown" ? <ConversationMarkdown text={content.text ?? ""} /> : <CodeBlock title={file.name} language={file.path.endsWith(".json") ? "json" : "plaintext"} lines={(content.text ?? "").split("\n")} wordWrap />}</ScrollArea>}
  </section>;
}

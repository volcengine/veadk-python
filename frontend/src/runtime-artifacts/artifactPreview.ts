import type { RuntimeArtifact } from "../adk/runtimeArtifacts";
import type { FileExplorerEntry, FileExplorerFolder } from "../components/composites/FileExplorer";

export function artifactEntries(items: readonly RuntimeArtifact[]): FileExplorerEntry[] {
  const root: FileExplorerEntry[] = [];
  const folders = new Map<string, FileExplorerFolder>();
  for (const item of items) {
    const parts = item.path.split("/");
    let entries = root;
    let prefix = "";
    for (const part of parts.slice(0, -1)) {
      prefix = prefix ? `${prefix}/${part}` : part;
      let folder = folders.get(prefix);
      if (!folder) {
        folder = { id: `folder:${prefix}`, name: part, type: "folder", children: [] };
        folders.set(prefix, folder);
        entries.push(folder);
      }
      entries = folder.children as FileExplorerEntry[];
    }
    entries.push({ id: item.path, name: item.name, type: "file", content: "" });
  }
  function sort(entries: FileExplorerEntry[]) {
    entries.sort((a, b) => a.type === b.type ? a.name.localeCompare(b.name) : a.type === "folder" ? -1 : 1);
    for (const entry of entries) if (entry.type === "folder") sort(entry.children as FileExplorerEntry[]);
  }
  sort(root);
  return root;
}

export function artifactPreviewKind(mimeType: string, path: string): "html" | "markdown" | "image" | "text" | "download" {
  const mime = mimeType.split(";", 1)[0].toLowerCase();
  if (mime === "text/html" || /\.html?$/i.test(path)) return "html";
  if (mime === "text/markdown" || /\.(md|markdown)$/i.test(path)) return "markdown";
  if (/^image\/(png|jpeg|gif|webp|svg\+xml|avif|bmp)$/.test(mime)) return "image";
  if (mime.startsWith("text/") || mime === "application/json" || /\.(txt|json|csv|yaml|yml|py|js|ts|css|log)$/i.test(path)) return "text";
  return "download";
}

/** Resolve only relative files within the current session, without accepting URL authorities. */
export function resolveArtifactResource(documentPath: string, reference: string): string | null {
  let path: string;
  try { path = decodeURIComponent(reference.split(/[?#]/, 1)[0]); } catch { return null; }
  if (!path || /^[\/\\]/.test(path) || /[:\\\u0000-\u001f]/.test(path)) return null;
  const segments = documentPath.split("/").slice(0, -1);
  for (const segment of path.split("/")) {
    if (!segment || segment === ".") continue;
    if (segment === "..") {
      if (segments.length === 0) return null;
      segments.pop();
    } else segments.push(segment);
  }
  return segments.join("/") || null;
}

function dataUrl(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("无法读取预览图片"));
    reader.readAsDataURL(blob);
  });
}

/** HTML stays in a scriptless sandbox; only explicitly fetched same-session images are embedded. */
export async function prepareArtifactHtml(source: string, path: string, load: (path: string) => Promise<Blob>, onBodyReady?: (html: string) => void): Promise<string> {
  const document = new DOMParser().parseFromString(source, "text/html");
  for (const element of document.querySelectorAll("script,iframe,frame,object,embed,base,link,meta[http-equiv],form")) element.remove();
  for (const element of document.querySelectorAll("*")) {
    for (const attribute of Array.from(element.attributes)) {
      if (/^on/i.test(attribute.name) || ["srcset", "srcdoc", "action", "formaction", "ping"].includes(attribute.name)) element.removeAttribute(attribute.name);
    }
    if (element.tagName !== "IMG") element.removeAttribute("src");
    if (element.hasAttribute("href")) element.removeAttribute("href");
  }
  const images = Array.from(document.querySelectorAll("img[src]"));
  if (images.length > 32) throw new Error("此页面图片较多，请下载完整文件后查看");
  const pendingImages = images.map(image => {
    const reference = image.getAttribute("src") ?? "";
    image.removeAttribute("src");
    if (/^data:image\/(png|jpeg|gif|webp|avif);base64,[a-z\d+/=\s]+$/i.test(reference)) {
      image.setAttribute("src", reference);
      return null;
    }
    const resource = resolveArtifactResource(path, reference);
    return resource ? { image, resource } : null;
  }).filter(item => item !== null);
  const policy = document.createElement("meta");
  policy.httpEquiv = "Content-Security-Policy";
  policy.content = "default-src 'none'; img-src data:; style-src 'unsafe-inline'; font-src data:; base-uri 'none'; form-action 'none'";
  document.head.prepend(policy);
  const serialize = () => `<!doctype html>${document.documentElement.outerHTML}`;
  // No original image URL, active element, or event handler reaches this first paint
  onBodyReady?.(serialize());
  let bytes = 0;
  const cache = new Map<string, Promise<string>>();
  async function embed({ image, resource }: NonNullable<typeof pendingImages[number]>) {
    let pending = cache.get(resource);
    if (!pending) {
      pending = load(resource).then(async blob => {
        bytes += blob.size;
        if (bytes > 20 * 1024 * 1024) throw new Error("页面图片超过 20 MB，请下载后查看");
        if (artifactPreviewKind(blob.type, resource) !== "image") throw new Error("HTML 引用的资源不是支持的图片");
        return dataUrl(blob);
      });
      cache.set(resource, pending);
    }
    image.setAttribute("src", await pending);
  }
  for (let index = 0; index < pendingImages.length; index += 4) {
    await Promise.all(pendingImages.slice(index, index + 4).map(embed));
  }
  return serialize();
}

export function artifactSize(size: number): string {
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / 1024 / 1024).toFixed(1)} MB`;
}

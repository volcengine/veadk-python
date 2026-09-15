export type FileExplorerIconKind = "react" | "script" | "style" | "markup" | "json" | "config" | "lock" | "markdown" | "text" | "python" | "go" | "rust" | "java" | "terminal" | "environment" | "image" | "pdf" | "archive" | "file";

interface FilePresentation { icon: FileExplorerIconKind; language: string }

const types: Record<string, FilePresentation> = {
  tsx: { icon: "react", language: "typescript" }, jsx: { icon: "react", language: "javascript" },
  ts: { icon: "script", language: "typescript" }, mts: { icon: "script", language: "typescript" }, cts: { icon: "script", language: "typescript" },
  js: { icon: "script", language: "javascript" }, mjs: { icon: "script", language: "javascript" }, cjs: { icon: "script", language: "javascript" },
  css: { icon: "style", language: "css" }, scss: { icon: "style", language: "scss" }, sass: { icon: "style", language: "scss" },
  html: { icon: "markup", language: "xml" }, htm: { icon: "markup", language: "xml" }, xml: { icon: "markup", language: "xml" }, vue: { icon: "markup", language: "xml" }, svelte: { icon: "markup", language: "xml" },
  json: { icon: "json", language: "json" }, jsonc: { icon: "json", language: "json" },
  yaml: { icon: "config", language: "yaml" }, yml: { icon: "config", language: "yaml" }, toml: { icon: "config", language: "ini" }, ini: { icon: "config", language: "ini" }, config: { icon: "config", language: "ini" }, conf: { icon: "config", language: "ini" }, cfg: { icon: "config", language: "ini" },
  md: { icon: "markdown", language: "markdown" }, mdx: { icon: "markdown", language: "markdown" }, markdown: { icon: "markdown", language: "markdown" },
  txt: { icon: "text", language: "plaintext" }, log: { icon: "text", language: "plaintext" }, csv: { icon: "text", language: "plaintext" },
  py: { icon: "python", language: "python" }, pyi: { icon: "python", language: "python" }, go: { icon: "go", language: "go" }, rs: { icon: "rust", language: "rust" }, java: { icon: "java", language: "java" },
  sh: { icon: "terminal", language: "bash" }, bash: { icon: "terminal", language: "bash" }, zsh: { icon: "terminal", language: "bash" },
  svg: { icon: "image", language: "xml" }, png: { icon: "image", language: "plaintext" }, jpg: { icon: "image", language: "plaintext" }, jpeg: { icon: "image", language: "plaintext" }, gif: { icon: "image", language: "plaintext" }, webp: { icon: "image", language: "plaintext" }, avif: { icon: "image", language: "plaintext" }, ico: { icon: "image", language: "plaintext" },
  pdf: { icon: "pdf", language: "plaintext" },
  zip: { icon: "archive", language: "plaintext" }, tar: { icon: "archive", language: "plaintext" }, gz: { icon: "archive", language: "plaintext" }, tgz: { icon: "archive", language: "plaintext" }, bz2: { icon: "archive", language: "plaintext" }, xz: { icon: "archive", language: "plaintext" }, rar: { icon: "archive", language: "plaintext" }, "7z": { icon: "archive", language: "plaintext" },
  sql: { icon: "json", language: "sql" }, diff: { icon: "script", language: "diff" }, patch: { icon: "script", language: "diff" },
};

export function filePresentation(name: string): FilePresentation {
  const filename = name.split(/[\\/]/).pop()?.toLowerCase() ?? name.toLowerCase();
  if (filename === ".env" || filename.startsWith(".env.")) return { icon: "environment", language: "ini" };
  if (filename === "dockerfile" || filename.startsWith("dockerfile.")) return { icon: "config", language: "dockerfile" };
  if (filename === "makefile" || filename === "gnumakefile") return { icon: "config", language: "makefile" };
  if (["license", "licence", "notice"].includes(filename)) return { icon: "text", language: "plaintext" };
  if ([".gitignore", ".dockerignore", ".npmrc", ".editorconfig"].includes(filename)) return { icon: "config", language: filename.endsWith("ignore") ? "plaintext" : "ini" };
  if ([".eslintrc", ".prettierrc", ".babelrc"].includes(filename)) return { icon: "config", language: "json" };
  const extension = filename.includes(".") ? filename.split(".").pop() ?? "" : "";
  const presentation: FilePresentation = Object.prototype.hasOwnProperty.call(types, extension)
    ? types[extension]
    : { icon: "file", language: "plaintext" };
  if (filename.endsWith(".lock") || filename.endsWith("-lock.json") || filename === "pnpm-lock.yaml") {
    const lockLanguage = ["cargo.lock", "poetry.lock", "uv.lock"].includes(filename) ? "ini" : filename === "yarn.lock" ? "yaml" : filename === "bun.lock" ? "json" : presentation.language;
    return { icon: "lock", language: lockLanguage };
  }
  if (filename.includes(".config.") || filename.startsWith("tsconfig") || filename.startsWith("jsconfig")) return { ...presentation, icon: "config" };
  return presentation;
}

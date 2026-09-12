import type { Plugin } from "prettier";

function parserFor(name: string, language?: string): string | undefined {
  if (language === "plaintext" || language === "text") return undefined;
  const extension = name.toLowerCase().split(".").pop();
  const parsers: Record<string, string> = {
    js: "babel", jsx: "babel", javascript: "babel", mjs: "babel", cjs: "babel",
    ts: "typescript", tsx: "typescript", typescript: "typescript", mts: "typescript", cts: "typescript",
    json: "json", jsonc: "jsonc", json5: "json5",
    css: "css", scss: "scss", less: "less", html: "html",
    yaml: "yaml", yml: "yaml", md: "markdown", markdown: "markdown",
  };
  const explicitParser = language && Object.prototype.hasOwnProperty.call(parsers, language) ? parsers[language] : undefined;
  return explicitParser ?? (extension && Object.prototype.hasOwnProperty.call(parsers, extension) ? parsers[extension] : undefined);
}

async function pluginsFor(parser: string): Promise<Plugin[]> {
  // Prettier 的 estree 声明文件为空，运行时模块实际提供 printers
  const estree = () => import("prettier/plugins/estree").then(plugin => plugin as Plugin);
  if (parser === "typescript") return Promise.all([import("prettier/plugins/typescript"), estree()]);
  if (["babel", "json", "jsonc", "json5"].includes(parser)) return Promise.all([import("prettier/plugins/babel"), estree()]);
  if (["css", "scss", "less"].includes(parser)) return [await import("prettier/plugins/postcss")];
  if (parser === "html") return [await import("prettier/plugins/html")];
  if (parser === "yaml") return [await import("prettier/plugins/yaml")];
  return [await import("prettier/plugins/markdown")];
}

/** 不支持的语言保留原文；语法错误交给调用方提示，不修改文件 */
export async function formatFileContent(content: string, name: string, language?: string): Promise<string> {
  const parser = parserFor(name, language);
  if (!parser || !content.trim()) return content;
  const [{ format }, plugins] = await Promise.all([import("prettier/standalone"), pluginsFor(parser)]);
  return format(content, { parser, plugins, printWidth: 80, tabWidth: 2, embeddedLanguageFormatting: "off" });
}

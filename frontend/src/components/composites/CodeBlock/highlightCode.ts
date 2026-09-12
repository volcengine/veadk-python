import hljs from "highlight.js/lib/core";
import type { Emitter, LanguageFn } from "highlight.js";
import bash from "highlight.js/lib/languages/bash";
import css from "highlight.js/lib/languages/css";
import diff from "highlight.js/lib/languages/diff";
import dockerfile from "highlight.js/lib/languages/dockerfile";
import go from "highlight.js/lib/languages/go";
import ini from "highlight.js/lib/languages/ini";
import java from "highlight.js/lib/languages/java";
import javascript from "highlight.js/lib/languages/javascript";
import json from "highlight.js/lib/languages/json";
import makefile from "highlight.js/lib/languages/makefile";
import markdown from "highlight.js/lib/languages/markdown";
import plaintext from "highlight.js/lib/languages/plaintext";
import python from "highlight.js/lib/languages/python";
import rust from "highlight.js/lib/languages/rust";
import scss from "highlight.js/lib/languages/scss";
import sql from "highlight.js/lib/languages/sql";
import typescript from "highlight.js/lib/languages/typescript";
import xml from "highlight.js/lib/languages/xml";
import yaml from "highlight.js/lib/languages/yaml";

type SyntaxColor = "comment" | "keyword" | "string" | "function" | "number" | "variable" | "constant";
export interface CodeSyntaxToken { text: string; color?: SyntaxColor }

function scopeColor(scope: string): SyntaxColor | undefined {
  if (scope.startsWith("title.class")) return "constant";
  const name = scope.split(".")[0];
  if (["comment", "doctag"].includes(name)) return "comment";
  if (["keyword", "meta", "selector-tag", "selector-pseudo"].includes(name)) return "keyword";
  if (["string", "regexp", "char", "escape", "addition", "link"].includes(name)) return "string";
  if (["title", "built_in", "section"].includes(name)) return "function";
  if (["number", "literal", "symbol", "bullet"].includes(name)) return "number";
  if (["variable", "property", "name", "tag", "deletion", "selector-class", "selector-id"].includes(name)) return "variable";
  if (["type", "attr", "attribute", "template-tag"].includes(name)) return "constant";
}

/** Collect the parser's text tokens directly so user code never becomes HTML */
class ReactTokenEmitter implements Emitter {
  readonly tokens: CodeSyntaxToken[] = [];
  private scopes: string[] = [];

  private append(text: string, color?: SyntaxColor) {
    if (!text) return;
    const previous = this.tokens[this.tokens.length - 1];
    if (previous && previous.color === color) previous.text += text;
    else this.tokens.push({ text, color });
  }

  addText(text: string) {
    const color = [...this.scopes].reverse().map(scopeColor).find(value => value !== undefined);
    this.append(text, color);
  }

  startScope(scope: string) { this.scopes.push(scope); }
  endScope() { this.scopes.pop(); }
  openNode(scope: string) { this.startScope(scope); }
  closeNode() { this.endScope(); }
  finalize() { this.scopes = []; }
  toHTML() { return ""; }

  __addSublanguage(emitter: Emitter) {
    if (emitter instanceof ReactTokenEmitter) {
      for (const token of emitter.tokens) this.append(token.text, token.color);
    }
  }
}

// Use a separate parser instance so other highlight.js consumers keep their renderer
const highlighter = hljs.newInstance();
const languages: Record<string, LanguageFn> = {
  bash, css, diff, dockerfile, go, ini, java, javascript, json, makefile,
  markdown, plaintext, python, rust, scss, sql, typescript, xml, yaml,
};
for (const [name, definition] of Object.entries(languages)) highlighter.registerLanguage(name, definition);
highlighter.configure({ __emitter: ReactTokenEmitter });

function splitTokens(tokens: readonly CodeSyntaxToken[]): CodeSyntaxToken[][] {
  const lines: CodeSyntaxToken[][] = [[]];
  for (const token of tokens) {
    token.text.split("\n").forEach((text, index) => {
      if (index > 0) lines.push([]);
      if (text) lines[lines.length - 1].push({ text, color: token.color });
    });
  }
  for (const line of lines) {
    const last = line[line.length - 1];
    if (last?.text.endsWith("\r")) last.text = last.text.slice(0, -1);
  }
  return lines;
}

export function highlightCode(code: string, language = "auto"): CodeSyntaxToken[][] {
  const requested = language.trim().toLowerCase();
  if (requested === "plaintext" || requested === "text" || requested === "txt" || requested !== "auto" && !highlighter.getLanguage(requested)) {
    return splitTokens([{ text: code }]);
  }
  const result = requested === "auto"
    ? highlighter.highlightAuto(code)
    : highlighter.highlight(code, { language: requested, ignoreIllegals: true });
  const tokens = result._emitter instanceof ReactTokenEmitter ? result._emitter.tokens : [];
  return splitTokens(tokens.map(token => token.text).join("") === code ? tokens : [{ text: code }]);
}

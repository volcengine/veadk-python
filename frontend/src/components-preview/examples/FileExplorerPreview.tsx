import { useState } from "react";
import { FileExplorer, type FileExplorerEntry } from "../../components/composites/FileExplorer";
import { ComponentApi } from "../api/ComponentApi";
import "./FileExplorerPreview.css";

const demoFiles: readonly FileExplorerEntry[] = [
  {
    id: "src", name: "src", type: "folder", children: [
      {
        id: "src/components", name: "components", type: "folder", children: [
          {
            id: "src/components/button.tsx", name: "button.tsx", type: "file", content: [
              'import type { ButtonHTMLAttributes, ReactNode } from "react";',
              'import { cn } from "../utils/cn";',
              'import "./button.css";',
              '',
              'export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {',
              '  variant?: "primary" | "secondary";',
              '  startIcon?: ReactNode;',
              '}',
              '',
              'export function Button({',
              '  variant = "primary",',
              '  startIcon,',
              '  children,',
              '  className,',
              '  disabled,',
              '  type = "button",',
              '  ...props',
              '}: ButtonProps) {',
              '  return (',
              '    <button',
              '      {...props}',
              '      type={type}',
              '      disabled={disabled}',
              '      className={cn("button", variant === "primary" ? "button-primary" : "button-secondary", disabled && "button-disabled", className)}',
              '    >',
              '      {startIcon && (',
              '        <span className="button-icon" aria-hidden="true">',
              '          {startIcon}',
              '        </span>',
              '      )}',
              '      <span className="button-label">',
              '        {children}',
              '      </span>',
              '    </button>',
              '  );',
              '}',
            ],
          },
          {
            id: "src/components/card.tsx", name: "card.tsx", type: "file", content: [
              'import type { HTMLAttributes, ReactNode } from "react";',
              '',
              'interface CardProps extends HTMLAttributes<HTMLElement> {',
              '  heading: ReactNode;',
              '}',
              '',
              'export function Card({ heading, children, ...props }: CardProps) {',
              '  return (',
              '    <article {...props} className="card">',
              '      <h3>{heading}</h3>',
              '      <div className="card-body">{children}</div>',
              '    </article>',
              '  );',
              '}',
            ],
          },
          {
            id: "src/components/button.css", name: "button.css", type: "file", content: [
              '.button {',
              '  display: inline-flex;',
              '  align-items: center;',
              '  justify-content: center;',
              '  gap: 8px;',
              '  height: 32px;',
              '  padding: 0 12px;',
              '  border: 1px solid transparent;',
              '  border-radius: 8px;',
              '  font: inherit;',
              '  cursor: pointer;',
              '  transition: background-color 140ms ease-out;',
              '}',
              '',
              '.button:disabled {',
              '  cursor: not-allowed;',
              '  opacity: .5;',
              '}',
              '',
              '@media (prefers-reduced-motion: reduce) {',
              '  .button { transition: none; }',
              '}',
            ],
          },
        ],
      },
      {
        id: "src/utils", name: "utils", type: "folder", children: [
          {
            id: "src/utils/compose.ts", name: "compose.ts", type: "file", content: [
              'export function compose<T>(',
              '  first: (value: T) => T,',
              '  second: (value: T) => T,',
              '): (value: T) => T {',
              '  return value => second(first(value));',
              '}',
            ],
          },
          {
            id: "src/utils/cn.ts", name: "cn.ts", type: "file", content: [
              'type ClassName = string | false | null | undefined;',
              '',
              'export function cn(...values: ClassName[]): string {',
              '  return values.filter(Boolean).join(" ");',
              '}',
            ],
          },
        ],
      },
      {
        id: "src/index.ts", name: "index.ts", type: "file", content: [
          'export { Button, type ButtonProps } from "./components/button";',
          'export { Card } from "./components/card";',
          'export { cn } from "./utils/cn";',
          'export { compose } from "./utils/compose";',
        ],
      },
    ],
  },
  {
    id: "examples", name: "examples", type: "folder", children: [
      { id: "examples/agent.py", name: "agent.py", type: "file", content: 'from dataclasses import dataclass\n\n@dataclass\nclass Agent:\n    name: str\n    enabled: bool = True\n\n    def run(self, prompt: str) -> str:\n        return f"{self.name}: {prompt}"\n' },
      { id: "examples/main.go", name: "main.go", type: "file", content: 'package main\n\nimport "fmt"\n\nfunc main() {\n    fmt.Println("Hello, Studio")\n}\n' },
      { id: "examples/lib.rs", name: "lib.rs", type: "file", content: 'pub fn greet(name: &str) -> String {\n    format!("Hello, {}", name)\n}\n' },
      { id: "examples/App.java", name: "App.java", type: "file", content: 'public class App {\n    public static void main(String[] args) {\n        System.out.println("Hello, Studio");\n    }\n}\n' },
      { id: "examples/theme.scss", name: "theme.scss", type: "file", content: '$spacing: 8px;\n\n.card {\n  padding: $spacing * 2;\n\n  &:hover {\n    opacity: .9;\n  }\n}\n' },
      { id: "examples/index.html", name: "index.html", type: "file", content: '<!doctype html>\n<html lang="en">\n  <body>\n    <button class="primary">Create resource</button>\n  </body>\n</html>\n' },
      { id: "examples/settings.yaml", name: "settings.yaml", type: "file", content: '# Preview settings\nname: component-demo\nenabled: true\nresources:\n  - agents\n  - documents\n' },
      { id: "examples/project.toml", name: "project.toml", type: "file", content: '[project]\nname = "component-demo"\nversion = "1.0.0"\n\n[preview]\nenabled = true\nport = 5186\n' },
      { id: "examples/run.sh", name: "run.sh", type: "file", content: '#!/usr/bin/env bash\nset -eu\n\nMODE="preview"\necho "Starting ${MODE}"\nnpm run dev\n' },
      { id: "examples/notes.txt", name: "notes.txt", type: "file", content: 'Component notes\n\nKeep controls aligned and use the shared design tokens.\n' },
      { id: "examples/logo.svg", name: "logo.svg", type: "file", content: '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">\n  <rect x="4" y="4" width="16" height="16" rx="4" fill="currentColor" />\n</svg>\n' },
      { id: "examples/guide.pdf", name: "guide.pdf", type: "file", content: "" },
      { id: "examples/release.zip", name: "release.zip", type: "file", content: "" },
      { id: "examples/Cargo.lock", name: "Cargo.lock", type: "file", content: '# Demo dependency lock\nversion = 3\n\n[[package]]\nname = "component-demo"\nversion = "1.0.0"\n' },
      { id: "examples/data.bin", name: "data.bin", type: "file", content: "" },
    ],
  },
  {
    id: "package.json", name: "package.json", type: "file", content: [
      '{',
      '  "name": "component-demo",',
      '  "version": "1.0.0",',
      '  "private": true,',
      '  "type": "module",',
      '  "scripts": {',
      '    "dev": "vite",',
      '    "build": "tsc && vite build"',
      '  }',
      '}',
    ],
  },
  {
    id: "tsconfig.json", name: "tsconfig.json", type: "file", content: [
      '{',
      '  "compilerOptions": {',
      '    "target": "ES2020",',
      '    "module": "ESNext",',
      '    "jsx": "react-jsx",',
      '    "strict": true,',
      '    "noEmit": true',
      '  },',
      '  "include": ["src"]',
      '}',
    ],
  },
  {
    id: "README.md", name: "README.md", type: "file", content: [
      '# Component demo',
      '',
      'A small collection of reusable interface components.',
      '',
      '## Development',
      '',
      'Install dependencies with npm install.',
      'Start the preview with npm run dev.',
      '',
      '## Components',
      '',
      '- Button: primary and secondary actions',
      '- Card: a title and body content',
    ],
  },
  {
    id: ".env", name: ".env", type: "file", content: [
      '# Demo configuration',
      'APP_NAME=component-demo',
      'APP_MODE=preview',
      'PUBLIC_BASE_URL=https://example.com',
    ],
  },
];

export function FileExplorerPreview() {
  const [editableFiles, setEditableFiles] = useState<readonly FileExplorerEntry[]>([
    { id: "settings.json", name: "settings.json", type: "file", content: '{"name":"component-demo","enabled":true,"resources":["agents","documents"],"description":"Keep controls aligned and use the shared design tokens. Long descriptions automatically wrap to the available width without adding extra line numbers."}' },
    { id: "agent.ts", name: "agent.ts", type: "file", content: 'export function createAgent(name: string) { return { name, enabled: true, tools: ["search", "summarize"], description: "An assistant that finds relevant documents and summarizes project progress for your team" }; }' },
  ]);
  const [editStatus, setEditStatus] = useState("");
  return (
    <section className="file-explorer-preview" aria-labelledby="file-explorer-preview-title">
      <h2 className="component-preview-title" id="file-explorer-preview-title">File Explorer</h2>
      <h3 className="file-explorer-preview__heading">只读 · 自动格式化与换行</h3>
      <FileExplorer
        entries={demoFiles}
        defaultSelectedId="src/components/button.tsx"
        defaultExpandedIds={["src", "src/components", "examples"]}
      />
      <h3 className="file-explorer-preview__heading">编辑与保存</h3>
      <FileExplorer
        allowEdit
        entries={editableFiles}
        defaultSelectedId="settings.json"
        onEdit={(_, __, file) => setEditStatus(`${file.name} 有未保存的修改`)}
        onSave={(id, content, file) => {
          setEditableFiles(previous => previous.map(entry => entry.id === id && entry.type === "file" ? { ...entry, content } : entry));
          setEditStatus(`已保存 ${file.name}`);
        }}
        style={{ height: 360 }}
      />
      <p className="file-explorer-preview__status" role="status">{editStatus}</p>
      <ComponentApi names={["FileExplorer"]} />
    </section>
  );
}

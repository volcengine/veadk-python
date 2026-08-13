import assert from "node:assert/strict";
import test from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { createServer } from "vite";

const server = await createServer({
  configFile: new URL("../vite.config.ts", import.meta.url).pathname,
  appType: "custom",
  logLevel: "silent",
  server: { middlewareMode: true, hmr: false, port: 0 },
});

test.after(async () => {
  await server.close();
});

const { Button } = await server.ssrLoadModule(
  "/src/a2ui/components/Button/Button.tsx",
);
const { Blocks } = await server.ssrLoadModule("/src/ui/Blocks.tsx");

test("A2UI Button disables actions only in a read-only render context", () => {
  const node = {
    id: "authorize",
    component: "Button",
    child: "label",
    action: { name: "authorize" },
  };
  const context = (readOnly) => ({
    readOnly,
    render: () => "Authorize",
    dispatchAction: () => {},
  });

  const readOnlyButton = Button({ node, ctx: context(true) });
  const interactiveButton = Button({ node, ctx: context(false) });

  assert.equal(readOnlyButton.props.disabled, true);
  assert.equal(interactiveButton.props.disabled, false);
});

test("OAuth authorization remains visible but disabled in a read-only transcript", () => {
  const block = {
    kind: "auth",
    label: "企业知识库",
    authUri: "https://accounts.example.com/oauth/authorize",
    done: false,
  };
  const render = (readOnly) =>
    renderToStaticMarkup(
      React.createElement(Blocks, {
        blocks: [block],
        readOnly,
        onAction: () => {},
        onAuth: async () => {},
      }),
    );

  const readOnlyHtml = render(true);
  const interactiveHtml = render(false);

  assert.match(readOnlyHtml, /<button[^>]*class="auth-card-btn"[^>]*disabled/);
  assert.match(readOnlyHtml, />去授权<\/button>/);
  assert.doesNotMatch(
    interactiveHtml,
    /<button[^>]*class="auth-card-btn"[^>]*disabled/,
  );
});

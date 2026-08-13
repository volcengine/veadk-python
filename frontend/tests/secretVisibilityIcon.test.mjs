import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { build } from "esbuild";
import { renderToStaticMarkup } from "react-dom/server";

async function loadComponent(relativePath) {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(relativePath, import.meta.url))],
    bundle: true,
    format: "esm",
    platform: "node",
    target: "node20",
    write: false,
  });
  const source = Buffer.from(result.outputFiles[0].contents).toString("base64");
  return import(`data:text/javascript;base64,${source}`);
}

const { SecretVisibilityIcon } = await loadComponent(
  "../src/ui/icons/SecretVisibilityIcon.tsx",
);

test("repository visibility icon distinguishes visible and hidden secret states", () => {
  const visible = renderToStaticMarkup(
    SecretVisibilityIcon({ visible: true, className: "secret-icon" }),
  );
  const hidden = renderToStaticMarkup(
    SecretVisibilityIcon({ visible: false, className: "secret-icon" }),
  );

  assert.match(visible, /aria-hidden="true"/);
  assert.match(visible, /class="secret-icon"/);
  assert.equal((visible.match(/<path/g) ?? []).length, 1);
  assert.equal((hidden.match(/<path/g) ?? []).length, 2);
});

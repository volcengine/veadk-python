import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const mediaSource = readFileSync(
  new URL("../src/ui/Media.tsx", import.meta.url),
  "utf8",
);

test("image attachments open only the shared photo viewer", () => {
  assert.match(
    mediaSource,
    /onClick=\{kind === "image" \? undefined : \(\) => setOpen\(item\)\}/,
  );
  assert.match(
    mediaSource,
    /kind === "image" && !disabled[\s\S]*?<PhotoView src=\{source\}>\{previewButton\}<\/PhotoView>/,
  );
});

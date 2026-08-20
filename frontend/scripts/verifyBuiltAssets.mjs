import assert from "node:assert/strict";
import { readFile, readdir, stat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const webuiRoot = fileURLToPath(new URL("../../veadk/webui/", import.meta.url));
const baseUrl = process.argv[2]
  ? new URL(process.argv[2].endsWith("/") ? process.argv[2] : `${process.argv[2]}/`)
  : undefined;

const expectedDirectories = [
  "assets/app",
  "assets/chunks",
  "assets/media",
  "assets/styles",
  "assets/visualizations/echarts",
  "assets/visualizations/mermaid",
];

async function filesUnder(directory) {
  const entries = await readdir(directory, { withFileTypes: true });
  const files = [];
  for (const entry of entries) {
    const absolutePath = path.join(directory, entry.name);
    if (entry.isDirectory()) files.push(...await filesUnder(absolutePath));
    else if (entry.isFile()) files.push(absolutePath);
  }
  return files;
}

for (const directory of expectedDirectories) {
  assert.ok((await stat(path.join(webuiRoot, directory))).isDirectory(), `${directory} is missing`);
}

const rootAssets = await readdir(path.join(webuiRoot, "assets"), { withFileTypes: true });
assert.equal(
  rootAssets.filter((entry) => entry.isFile()).length,
  0,
  "built assets should not be placed directly under assets/",
);

const files = await filesUnder(webuiRoot);
const relativeFiles = files.map((file) => path.relative(webuiRoot, file).split(path.sep).join("/"));
const packagedFiles = new Set(relativeFiles);
const index = await readFile(path.join(webuiRoot, "index.html"), "utf8");
assert.match(index, /\/assets\/app\/[^"']+\.js/);
assert.match(index, /\/assets\/styles\/[^"']+\.css/);
assert.ok(relativeFiles.some((file) => file.startsWith("assets/visualizations/mermaid/")));
assert.ok(relativeFiles.some((file) => file.startsWith("assets/visualizations/echarts/")));

let verifiedReferences = 0;
function verifyReference(fromFile, reference) {
  const cleanReference = reference.split(/[?#]/, 1)[0];
  if (!cleanReference || /^(?:[a-z]+:|#)/i.test(cleanReference)) return;
  if (!cleanReference.startsWith("/") && !cleanReference.startsWith(".")) return;
  const resolved = cleanReference.startsWith("/")
    ? cleanReference.slice(1)
    : path.posix.normalize(path.posix.join(path.posix.dirname(fromFile), cleanReference));
  assert.ok(packagedFiles.has(resolved), `${fromFile} references missing asset ${resolved}`);
  verifiedReferences += 1;
}

for (const relativeFile of relativeFiles) {
  if (!/\.(?:html|css|js)$/.test(relativeFile)) continue;
  const contents = await readFile(path.join(webuiRoot, relativeFile), "utf8");
  const patterns = relativeFile.endsWith(".html")
    ? [/(?:src|href)=["']([^"']+)["']/g]
    : relativeFile.endsWith(".css")
      ? [/url\(\s*["']?([^"')]+)["']?\s*\)/g]
      : [/(?:\bfrom\s*|\bimport\s*\(\s*)["']([^"']+)["']/g];
  for (const pattern of patterns) {
    for (const match of contents.matchAll(pattern)) verifyReference(relativeFile, match[1]);
  }
}
assert.ok(verifiedReferences > 10, "too few built asset references were verified");

if (baseUrl) {
  for (const relativeFile of relativeFiles) {
    const response = await fetch(new URL(relativeFile, baseUrl));
    assert.equal(response.status, 200, `${relativeFile} returned ${response.status}`);
    const local = await readFile(path.join(webuiRoot, relativeFile));
    const served = Buffer.from(await response.arrayBuffer());
    assert.equal(Buffer.compare(local, served), 0, `${relativeFile} was not served byte-for-byte`);
  }
}

console.log(
  `Verified ${relativeFiles.length} packaged WebUI files and ${verifiedReferences} internal references${baseUrl ? ` through ${baseUrl.origin}` : ""}.`,
);

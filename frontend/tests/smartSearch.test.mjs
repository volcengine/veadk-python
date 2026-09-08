import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const searchViewSource = readFileSync(
  new URL("../src/ui/Search.tsx", import.meta.url),
  "utf8",
);
const searchSource = readFileSync(
  new URL("../src/adk/search.ts", import.meta.url),
  "utf8",
);
const clientSource = readFileSync(
  new URL("../src/adk/client.ts", import.meta.url),
  "utf8",
);

test("smart search enables only retrieval sources mounted on the Agent", () => {
  assert.match(searchViewSource, /agentInfo\?\.searchSources/);
  assert.match(searchViewSource, /mounted\.has\("knowledge"\)/);
  assert.match(searchViewSource, /mounted\.has\("memory"\)/);
  assert.match(searchViewSource, /mounted\.has\("web"\)/);
  assert.match(searchViewSource, /t\("search\.notMounted", \{ label \}\)/);
  assert.match(searchViewSource, /t\("search\.webDescription"\)/);
  assert.match(searchViewSource, /aria-haspopup="listbox"/);
  assert.match(searchViewSource, /t\("search\.placeholder\.knowledge"/);
  assert.match(searchViewSource, /t\("search\.placeholder\.memory"/);
  assert.doesNotMatch(searchViewSource, /className="search-sources"/);
});

test("knowledge and memory searches use the selected Agent endpoint", () => {
  assert.match(searchSource, /componentSearch\(appId, source, query\.trim\(\), userId\)/);
  assert.match(clientSource, /export async function componentSearch/);
  assert.match(clientSource, /apiFetch\(`\/web\/search\?\$\{params\.toString\(\)\}`, \{\}, ep\)/);
});

test("sidebar uses the Figma search icon while submit keeps its restrained glyph", () => {
  assert.match(searchViewSource, /function SearchGlyph/);
  assert.match(searchViewSource, /import \{ SidebarSearchIcon \} from "\.\/icons\/SidebarIcons"/);
  assert.match(searchViewSource, /<SidebarSearchIcon className="icon" \/>/);
  assert.match(searchViewSource, /<SearchGlyph className="icon" \/>/);
  assert.doesNotMatch(searchViewSource, /import \{[^}]*\bSearch\b[^}]*\} from "lucide-react"/s);
});

test("editing a query or changing source waits for an explicit search", () => {
  assert.match(searchViewSource, /function updateQuery/);
  assert.match(searchViewSource, /onChange=\{\(e\) => updateQuery\(e\.target\.value\)\}/);
  assert.match(searchViewSource, /setSearched\(false\)/);
  assert.doesNotMatch(searchViewSource, /void doSearch\(query, src\)/);
});

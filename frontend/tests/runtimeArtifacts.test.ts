// @vitest-environment jsdom
import { expect, it } from "vitest";
import { artifactEntries, artifactPreviewKind, resolveArtifactResource, prepareArtifactHtml } from "../src/runtime-artifacts/artifactPreview";

it("keeps nested artifact directories and file selection identities", () => {
  const entries = artifactEntries([
    { path: "reports/index.html", name: "index.html", sizeBytes: 12, mimeType: "text/html", updatedAt: "" },
    { path: "reports/images/chart.svg", name: "chart.svg", sizeBytes: 12, mimeType: "image/svg+xml", updatedAt: "" },
  ]);
  expect(entries[0]).toMatchObject({ id: "folder:reports", name: "reports", type: "folder" });
  expect(JSON.stringify(entries)).toContain('"id":"reports/images/chart.svg"');
});

it("resolves relative resources within the session and rejects external or escaping references", () => {
  expect(resolveArtifactResource("reports/index.html", "../images/chart.svg")).toBe("images/chart.svg");
  expect(resolveArtifactResource("index.html", "./images/chart.svg")).toBe("images/chart.svg");
  for (const path of ["../../private.txt", "https://example.org/x", "//example.org/x", "/web/auth", "%2e%2e/private", "javascript:alert(1)", "..\\private"]) {
    expect(resolveArtifactResource("index.html", path)).toBeNull();
  }
});

it("previews known file formats and treats unknown binary files as downloads", () => {
  expect(artifactPreviewKind("image/svg+xml", "plot.svg")).toBe("image");
  expect(artifactPreviewKind("text/html", "report.html")).toBe("html");
  expect(artifactPreviewKind("text/plain", "README.md")).toBe("markdown");
  expect(artifactPreviewKind("application/json", "data.json")).toBe("text");
  expect(artifactPreviewKind("application/zip", "data.zip")).toBe("download");
});

it("embeds only authenticated same-session images and blocks active HTML", async () => {
  const requested: string[] = [];
  const html = await prepareArtifactHtml('<html><head><base href="https://example.org"><meta http-equiv="refresh" content="0;url=https://example.org"></head><body onload="alert(1)"><script>alert(1)</script><img src="images/chart.svg"><img src="https://example.org/pixel"><iframe src="/web/auth"></iframe></body></html>', "reports/index.html", async path => {
    requested.push(path);
    return new Blob(['<svg xmlns="http://www.w3.org/2000/svg"/>'], { type: "image/svg+xml" });
  });
  expect(requested).toEqual(["reports/images/chart.svg"]);
  expect(html).toContain("data:image/svg+xml;base64,");
  expect(html).toContain("default-src 'none'");
  expect(html).not.toMatch(/<script|<iframe|<base|onload=|http-equiv="refresh"|src="https:/);
});

it("publishes a fully isolated HTML body before waiting for relative images", async () => {
  let finish!: (blob: Blob) => void;
  let initial = "";
  const pending = prepareArtifactHtml('<h1>Read this immediately</h1><img src="chart.svg"><img src="https://example.org/pixel"><script>alert(1)</script>', "index.html",
    () => new Promise(resolve => { finish = resolve; }), html => { initial = html; });
  expect(initial).toContain("Read this immediately");
  expect(initial).toContain("default-src 'none'");
  expect(initial).not.toMatch(/<script|src="(?:chart|https:)/);
  finish(new Blob(['<svg xmlns="http://www.w3.org/2000/svg"/>'], { type: "image/svg+xml" }));
  expect(await pending).toContain("data:image/svg+xml;base64,");
});

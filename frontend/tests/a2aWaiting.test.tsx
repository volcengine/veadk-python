import React from "react";
import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { ThinkingPlaceholder } from "../src/ui/Blocks";
import { createAssistantEventProjector } from "../src/blocks";
import { i18n } from "../src/i18n/runtime";

describe("A2A waiting presentation", () => {
  it.each([
    ["connecting", "正在等待 Runtime 响应"],
    ["submitted", "任务排队中"],
    ["working", "任务执行中"],
  ])("renders %s as accessible progress without answer content", async (status, label) => {
    await i18n.changeLanguage("zh-CN");
    const projector = createAssistantEventProjector();
    const projection = projector.project({author: "agent", partial: true,
      customMetadata: {a2aStatus: status}});
    expect(projection.completed).toBe(false);
    expect(projection.turn.blocks).toEqual([]);
    const html = renderToStaticMarkup(<ThinkingPlaceholder a2aStatus={projection.turn.meta?.a2aStatus} />);
    expect(html).toContain(label);
    expect(html).toContain('role="status"');
    expect(html).toContain('aria-live="polite"');
    const final = projector.project({author: "agent", partial: false,
      content: {role: "model", parts: [{text: "done"}]}});
    expect(final.completed).toBe(true);
    expect(final.turn.meta?.a2aStatus).toBeUndefined();
  });
  it("falls back for unknown status and ignores malformed metadata", () => {
    for (const status of [undefined, "unknown"]) {
      const html = renderToStaticMarkup(<ThinkingPlaceholder a2aStatus={status} />);
      expect(html).toContain("block-thinking");
      expect(html).not.toContain("block-progress");
    }
    const projector = createAssistantEventProjector();
    expect(projector.project({customMetadata: {a2aStatus: 123}}).ignored).toBe(true);
    expect(projector.project({partial: true, custom_metadata: {a2aStatus: "working"}}).turn.meta?.a2aStatus).toBe("working");
  });
});

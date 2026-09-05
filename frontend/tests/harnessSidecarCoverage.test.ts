import { describe, expect, it } from "vitest";
import {
  HARNESS_SIDECAR_OPTION_IDS,
  HARNESS_SIDECAR_OPTION_GROUPS,
  HARNESS_SIDECAR_OPTIONS,
  HARNESS_SIDECAR_PROFILES,
  harnessIntentFromOptimizations,
  harnessIntentFromRuntimeEnvs,
  harnessProfileDefaultOptimizations,
  normalizeHarnessSidecarIntent,
  harnessSidecarProviderNotice,
  harnessSidecarProfileLabel,
  harnessSidecarOptionLabel,
  releaseDraftFromDebugVariant,
  selectedHarnessModelProxyOptimizations,
  selectedHarnessProfile,
  selectedHarnessOptimizations,
} from "../src/create/harnessSidecarOptions";
import { emptyDraft } from "../src/create/types";

describe("Studio Harness Sidecar metadata options", () => {
  it("keeps BytePlus ordinary deployment available while rejecting Sidecar selection", () => {
    expect(harnessSidecarProviderNotice("volcengine")).toBeNull();
    expect(harnessSidecarProviderNotice("byteplus")).toContain(
      "not available for BytePlus accounts",
    );
  });

  it("publishes the five capabilities integrated by this Studio release", () => {
    expect(HARNESS_SIDECAR_OPTION_IDS).toEqual([
      "context_engine",
      "compressor",
      "verifier",
      "long_run_control",
      "mcp_resilience",
    ]);
    expect(HARNESS_SIDECAR_OPTIONS.map((item) => item.displayName)).toEqual([
      "Context management",
      "Context and result compression",
      "Response verification and repair",
      "Goal task control",
      "MCP resilience",
    ]);
    expect(HARNESS_SIDECAR_OPTIONS.at(-1)?.description).toContain(
      "read-only SQL protection",
    );
  });

  it("publishes custom first and the concrete ops scenario after it", () => {
    expect(HARNESS_SIDECAR_PROFILES.map((profile) => profile.id)).toEqual([
      "default",
      "ops",
    ]);
    expect(HARNESS_SIDECAR_PROFILES.map((profile) => profile.displayName)).toEqual([
      "Custom",
      "Operations",
    ]);
    expect(HARNESS_SIDECAR_PROFILES.map((profile) => profile.description)).toEqual([
      "Choose components as needed. The Sidecar stays off when none are selected.",
      "For operations diagnostics, databases, logs, and monitoring MCP servers.",
    ]);
    expect(harnessProfileDefaultOptimizations("default")).toEqual([]);
    expect(harnessProfileDefaultOptimizations("ops")).toEqual([
      "context_engine",
      "verifier",
      "long_run_control",
      "mcp_resilience",
    ]);
    expect(HARNESS_SIDECAR_PROFILES.at(-1)?.autoAddedComponents).toEqual([
      "sql_readonly",
    ]);
    expect(
      harnessProfileDefaultOptimizations(
        "unsupported" as Parameters<
          typeof harnessProfileDefaultOptimizations
        >[0],
      ),
    ).toEqual([]);
  });

  it("publishes localized optimization groups", () => {
    expect(HARNESS_SIDECAR_OPTION_GROUPS.map((group) => group.displayName)).toEqual([
      "Improve response quality",
      "Reduce runtime cost",
      "Improve runtime stability",
    ]);
  });

  it("turns a selection into metadata without runtime identity", () => {
    expect(harnessIntentFromOptimizations(["verifier"])).toEqual({
      enabled: true,
      profile: "default",
      componentOverrides: {
        context_engine: false,
        compressor: false,
        verifier: true,
        long_run_control: false,
        mcp_resilience: false,
      },
    });
  });

  it("keeps the empty selection disabled", () => {
    expect(harnessIntentFromOptimizations([])).toMatchObject({
      enabled: false,
    });
  });

  it("restores the ops profile without enabling compression by default", () => {
    const intent = harnessIntentFromRuntimeEnvs([
      { key: "HARNESS_SIDECAR_ENABLED", value: "true" },
      { key: "HARNESS_PROFILE", value: "ops" },
      { key: "HARNESS_MODEL_PROXY_ENABLED", value: "true" },
      { key: "HARNESS_MCP_GATEWAY_ENABLED", value: "true" },
    ]);

    expect(intent).toEqual(
      harnessIntentFromOptimizations(
        harnessProfileDefaultOptimizations("ops"),
        "ops",
      ),
    );
  });

  it("canonicalizes an existing ops Runtime to the fixed ops preset", () => {
    const intent = harnessIntentFromRuntimeEnvs([
      { key: "HARNESS_SIDECAR_ENABLED", value: "true" },
      { key: "HARNESS_PROFILE", value: "ops" },
      {
        key: "HARNESS_SIDECAR_COMPONENT_OVERRIDES",
        value: JSON.stringify({
          context_engine: true,
          compressor: true,
          verifier: true,
          long_run_control: true,
          mcp_resilience: true,
        }),
      },
    ]);

    expect(intent).toEqual(
      harnessIntentFromOptimizations(
        harnessProfileDefaultOptimizations("ops"),
        "ops",
      ),
    );
  });

  it("repairs a partial legacy ops snapshot without enabling compression", () => {
    expect(
      normalizeHarnessSidecarIntent(
        harnessIntentFromOptimizations(["mcp_resilience"], "ops"),
      ),
    ).toEqual(
      harnessIntentFromOptimizations(
        harnessProfileDefaultOptimizations("ops"),
        "ops",
      ),
    );
  });

  it("normalizes custom snapshots from explicit overrides and missing legacy metadata", () => {
    expect(
      normalizeHarnessSidecarIntent({
        ...harnessIntentFromOptimizations(["verifier"]),
        catalogVersion: "catalog-v1",
        planHash: "sha256:test-plan",
      }),
    ).toEqual({
      ...harnessIntentFromOptimizations(["verifier"]),
      catalogVersion: "catalog-v1",
      planHash: "sha256:test-plan",
    });

    expect(
      normalizeHarnessSidecarIntent({
        enabled: true,
        profile: "default",
        componentOverrides: undefined,
      } as unknown as Parameters<typeof normalizeHarnessSidecarIntent>[0]),
    ).toEqual(harnessIntentFromOptimizations([]));
  });

  it("restores custom model and MCP optimizations from explicit Runtime flags", () => {
    expect(
      harnessIntentFromRuntimeEnvs([
        { key: "HARNESS_SIDECAR_ENABLED", value: "yes" },
        { key: "HARNESS_PROFILE", value: "default" },
        { key: "HARNESS_MODEL_PROXY_ENABLED", value: "on" },
        { key: "HARNESS_MCP_GATEWAY_ENABLED", value: "1" },
      ]),
    ).toEqual(
      harnessIntentFromOptimizations([
        "context_engine",
        "compressor",
        "verifier",
        "long_run_control",
        "mcp_resilience",
      ]),
    );
  });

  it("prefers exact custom component overrides over broad Runtime proxy flags", () => {
    const intent = harnessIntentFromRuntimeEnvs([
      { key: "HARNESS_SIDECAR_ENABLED", value: "true" },
      { key: "HARNESS_PROFILE", value: "default" },
      {
        key: "HARNESS_SIDECAR_COMPONENT_OVERRIDES",
        value: JSON.stringify({ verifier: true, mcp_resilience: false }),
      },
      { key: "HARNESS_MODEL_PROXY_ENABLED", value: "true" },
      { key: "HARNESS_MCP_GATEWAY_ENABLED", value: "true" },
    ]);

    expect(intent).toEqual(harnessIntentFromOptimizations(["verifier"]));
  });

  it.each(["not-json", "[]", "null"])(
    "falls back to explicit proxy flags for unusable overrides: %s",
    (overrides) => {
      const intent = harnessIntentFromRuntimeEnvs([
        { key: "HARNESS_SIDECAR_ENABLED", value: "true" },
        { key: "HARNESS_SIDECAR_COMPONENT_OVERRIDES", value: overrides },
        { key: "HARNESS_MODEL_PROXY_ENABLED", value: "false" },
        { key: "HARNESS_MCP_GATEWAY_ENABLED", value: "false" },
      ]);

      expect(intent).toEqual({
        ...harnessIntentFromOptimizations([]),
        enabled: true,
      });
    },
  );

  it("keeps an explicitly disabled Runtime recorded as disabled", () => {
    expect(
      harnessIntentFromRuntimeEnvs([
        { key: "HARNESS_SIDECAR_ENABLED", value: "false" },
        { key: "HARNESS_PROFILE", value: "ops" },
        { key: "HARNESS_MODEL_PROXY_ENABLED", value: "true" },
        { key: "HARNESS_MCP_GATEWAY_ENABLED", value: "true" },
      ]),
    ).toEqual(harnessIntentFromOptimizations([], "ops"));
  });

  it("does not infer Sidecar state without its explicit Runtime marker", () => {
    expect(
      harnessIntentFromRuntimeEnvs([
        { key: "HARNESS_PROFILE", value: "ops" },
        { key: "HARNESS_MODEL_PROXY_ENABLED", value: "true" },
      ]),
    ).toBeNull();
    expect(harnessIntentFromRuntimeEnvs(undefined)).toBeNull();
  });

  it("preserves the selected profile in public intent metadata", () => {
    expect(
      harnessIntentFromOptimizations(
        harnessProfileDefaultOptimizations("ops"),
        "ops",
      ),
    ).toMatchObject({
      enabled: true,
      profile: "ops",
      componentOverrides: { compressor: false, mcp_resilience: true },
    });
  });

  it("materializes ordinary and ops release drafts with model fallback", () => {
    const ordinaryDraft = {
      ...emptyDraft(),
      modelName: "ordinary-model",
      description: "ordinary description",
      instruction: "ordinary instruction",
    };
    const ordinaryRelease = releaseDraftFromDebugVariant(ordinaryDraft, {
      modelName: "",
      description: ordinaryDraft.description,
      instruction: ordinaryDraft.instruction,
    });
    expect(ordinaryRelease.modelName).toBe("ordinary-model");
    expect(ordinaryRelease.harnessSidecar).toBeUndefined();

    const opsDraft = {
      ...ordinaryDraft,
      harnessSidecar: harnessIntentFromOptimizations(
        harnessProfileDefaultOptimizations("ops"),
        "ops",
      ),
    };
    const opsRelease = releaseDraftFromDebugVariant(opsDraft, {
      modelName: "ops-model",
      description: "ops description",
      instruction: "ops instruction",
    });
    expect(opsRelease).toMatchObject({
      modelName: "ops-model",
      description: "ops description",
      instruction: "ops instruction",
      harnessSidecar: {
        enabled: true,
        profile: "ops",
        componentOverrides: { compressor: false, mcp_resilience: true },
      },
    });
  });

  it("derives selected options from Draft metadata", () => {
    expect(selectedHarnessOptimizations(emptyDraft())).toEqual([]);
    expect(selectedHarnessProfile(emptyDraft())).toBe("default");
    expect(
      selectedHarnessOptimizations({
        ...emptyDraft(),
        harnessSidecar: harnessIntentFromOptimizations([
          "compressor",
          "mcp_resilience",
        ]),
      }),
    ).toEqual(["compressor", "mcp_resilience"]);
    expect(
      selectedHarnessProfile({
        ...emptyDraft(),
        harnessSidecar: harnessIntentFromOptimizations(
          harnessProfileDefaultOptimizations("ops"),
          "ops",
        ),
      }),
    ).toBe("ops");
  });

  it("derives the selected Model Proxy optimization dependencies", () => {
    expect(
      selectedHarnessModelProxyOptimizations({
        ...emptyDraft(),
        harnessSidecar: harnessIntentFromOptimizations([
          "context_engine",
          "verifier",
          "mcp_resilience",
        ]),
      }),
    ).toEqual(["context_engine", "verifier"]);
    expect(selectedHarnessModelProxyOptimizations(emptyDraft())).toEqual([]);
  });

  it("maps known labels and preserves unknown runtime-only ids", () => {
    expect(harnessSidecarProfileLabel("default")).toBe("Custom");
    expect(harnessSidecarProfileLabel("ops")).toBe("Operations");
    expect(harnessSidecarProfileLabel("unknown")).toBe("unknown");
    expect(harnessSidecarOptionLabel("long_run_control")).toBe("Goal task control");
    expect(harnessSidecarOptionLabel("sql_readonly")).toBe("sql_readonly");
  });
});

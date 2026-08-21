import assert from "node:assert/strict";
import test from "node:test";

import { build } from "esbuild";

async function loadCandidateArtifactModule() {
  const result = await build({
    entryPoints: [new URL(
      "../src/evaluation/candidateArtifact.ts",
      import.meta.url,
    ).pathname],
    bundle: true,
    format: "esm",
    platform: "node",
    target: "node20",
    write: false,
  });
  const source = result.outputFiles[0]?.text;
  assert.ok(source, "expected candidate artifact helpers to compile");
  return import(`data:text/javascript;base64,${Buffer.from(source).toString("base64")}`);
}

const artifact = {
  codeDigest: "code-1",
  topologyDigest: "topology-1",
  modelRefs: ["model-b", "model-a"],
  promptRefs: ["prompt-1"],
  toolRefs: ["tool-b", "tool-a"],
  skillRefs: ["skill-1"],
  knowledgeRefs: ["knowledge-1"],
  memoryRefs: ["memory-1"],
  environmentRefs: [
    { name: "TOKEN_B", reference: "env://TOKEN_B" },
    { name: "TOKEN_A", reference: "env://TOKEN_A" },
  ],
  runtimeProjectRef: null,
};

test("candidate fingerprint is stable across reference order and runtime storage refs", async () => {
  const { candidateArtifactFingerprint } = await loadCandidateArtifactModule();
  const reordered = {
    ...artifact,
    modelRefs: [...artifact.modelRefs].reverse(),
    toolRefs: [...artifact.toolRefs].reverse(),
    environmentRefs: [...artifact.environmentRefs].reverse(),
    runtimeProjectRef: "tos://stored/runtime-project",
  };

  assert.equal(
    candidateArtifactFingerprint(artifact),
    candidateArtifactFingerprint(reordered),
  );
});

test("matching candidate chooses the newest exact artifact and rejects changed dependencies", async () => {
  const { findMatchingCandidate } = await loadCandidateArtifactModule();
  const candidates = [
    { candidateId: "candidate-old", agentId: "agent-1", version: 1, artifact, createdAt: "2026-08-16T00:00:00Z", createdBy: "owner" },
    { candidateId: "candidate-new", agentId: "agent-1", version: 2, artifact: { ...artifact, runtimeProjectRef: "tos://stored/runtime-project" }, createdAt: "2026-08-17T00:00:00Z", createdBy: "owner" },
    { candidateId: "candidate-other", agentId: "agent-1", version: 3, artifact: { ...artifact, promptRefs: ["prompt-2"] }, createdAt: "2026-08-18T00:00:00Z", createdBy: "owner" },
  ];

  assert.equal(findMatchingCandidate(candidates, artifact)?.candidateId, "candidate-new");
  assert.equal(findMatchingCandidate(candidates, { ...artifact, codeDigest: "changed" }), null);
});

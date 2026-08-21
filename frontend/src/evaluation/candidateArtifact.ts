import type { CandidateArtifact, CandidateVersion } from "./types";

function sorted(values: string[]): string[] {
  return [...values].sort((left, right) => left.localeCompare(right));
}

export function candidateArtifactFingerprint(artifact: CandidateArtifact): string {
  return JSON.stringify({
    codeDigest: artifact.codeDigest,
    topologyDigest: artifact.topologyDigest,
    modelRefs: sorted(artifact.modelRefs),
    promptRefs: sorted(artifact.promptRefs),
    toolRefs: sorted(artifact.toolRefs),
    skillRefs: sorted(artifact.skillRefs),
    knowledgeRefs: sorted(artifact.knowledgeRefs),
    memoryRefs: sorted(artifact.memoryRefs),
    environmentRefs: [...artifact.environmentRefs]
      .map(({ name, reference }) => ({ name, reference }))
      .sort((left, right) => `${left.name}:${left.reference}`.localeCompare(`${right.name}:${right.reference}`)),
  });
}

export function findMatchingCandidate(
  candidates: CandidateVersion[],
  artifact: CandidateArtifact,
): CandidateVersion | null {
  const fingerprint = candidateArtifactFingerprint(artifact);
  return [...candidates]
    .filter((candidate) => candidateArtifactFingerprint(candidate.artifact) === fingerprint)
    .sort((left, right) => {
      const timeDifference = Date.parse(right.createdAt) - Date.parse(left.createdAt);
      return Number.isNaN(timeDifference) || timeDifference === 0
        ? right.version - left.version
        : timeDifference;
    })[0] ?? null;
}

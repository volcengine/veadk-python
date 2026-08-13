export type ComparisonRuntimeBatchResult<TRuntime> =
  | { ok: true; runtimes: Map<string, TRuntime> }
  | { ok: false; failedTargetId: string; error: unknown };

export function debugRuntimeFailureMessage(error: unknown): string {
  if (error instanceof Error && error.message.trim()) return error.message;
  return "调试环境启动失败，请稍后重试。";
}

export async function stageComparisonRuntimes<
  TTarget extends { id: string },
  TRuntime,
>(
  targets: readonly TTarget[],
  createRuntime: (target: TTarget) => Promise<TRuntime>,
  cleanupRuntime: (runtime: TRuntime) => Promise<unknown>,
): Promise<ComparisonRuntimeBatchResult<TRuntime>> {
  const settled = await Promise.allSettled(
    targets.map(async (target) => [target.id, await createRuntime(target)] as const),
  );
  const failedIndex = settled.findIndex((result) => result.status === "rejected");

  if (failedIndex >= 0) {
    const successful = settled.flatMap((result) =>
      result.status === "fulfilled" ? [result.value[1]] : [],
    );
    await Promise.allSettled(
      successful.map((runtime) =>
        Promise.resolve().then(() => cleanupRuntime(runtime)),
      ),
    );
    const failure = settled[failedIndex] as PromiseRejectedResult;
    return {
      ok: false,
      failedTargetId: targets[failedIndex].id,
      error: failure.reason,
    };
  }

  return {
    ok: true,
    runtimes: new Map(
      settled.map(
        (result) =>
          (result as PromiseFulfilledResult<readonly [string, TRuntime]>).value,
      ),
    ),
  };
}

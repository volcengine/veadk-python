export interface DebugStreamHandle {
  token: number;
  signal: AbortSignal;
}

interface DebugStreamEntry {
  token: number;
  controller: AbortController;
}

/** Owns the live stream for each comparison variant and obsoletes replacements. */
export class DebugStreamRegistry {
  private readonly entries = new Map<string, DebugStreamEntry>();
  private nextToken = 1;

  begin(variantId: string): DebugStreamHandle {
    this.abort(variantId);
    const controller = new AbortController();
    const token = this.nextToken++;
    this.entries.set(variantId, { token, controller });
    return { token, signal: controller.signal };
  }

  isCurrent(variantId: string, token: number): boolean {
    const entry = this.entries.get(variantId);
    return entry?.token === token && !entry.controller.signal.aborted;
  }

  finish(variantId: string, token: number): boolean {
    if (!this.isCurrent(variantId, token)) return false;
    this.entries.delete(variantId);
    return true;
  }

  abort(variantId: string): void {
    const entry = this.entries.get(variantId);
    if (!entry) return;
    this.entries.delete(variantId);
    entry.controller.abort();
  }

  abortAll(): void {
    const entries = [...this.entries.values()];
    this.entries.clear();
    entries.forEach(({ controller }) => controller.abort());
  }
}

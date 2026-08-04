interface NativeCompositionEvent {
  isComposing: boolean;
  keyCode: number;
}

/** Browsers report IME composition either explicitly or with legacy key 229. */
export function isImeCompositionEvent(event: NativeCompositionEvent): boolean {
  return event.isComposing || event.keyCode === 229;
}

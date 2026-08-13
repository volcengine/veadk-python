// Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

export const RESPONSE_ANNOTATION_COMMENT_MAX_LENGTH = 2_000;
export const RESPONSE_ANNOTATION_SELECTION_MAX_LENGTH = 700;
export const RESPONSE_ANNOTATION_NOTE_MAX_LENGTH = 1_200;

export interface ResponseAnnotationAnchor {
  left: number;
  top: number;
  height: number;
}

export interface ResponseTextSelection {
  text: string;
  anchor: ResponseAnnotationAnchor;
}

function truncateCodePoints(value: string, maxLength: number): string {
  const codePoints = Array.from(value);
  if (codePoints.length <= maxLength) return value;
  return `${codePoints.slice(0, maxLength - 1).join("").trimEnd()}…`;
}

export function prepareResponseAnnotationSelection(value: string): string {
  return truncateCodePoints(
    value.trim(),
    RESPONSE_ANNOTATION_SELECTION_MAX_LENGTH,
  );
}

export function prepareResponseAnnotationNote(value: string): string {
  return truncateCodePoints(value, RESPONSE_ANNOTATION_NOTE_MAX_LENGTH);
}

export function canSubmitResponseAnnotation(note: string): boolean {
  return note.trim().length > 0;
}

export function formatResponseAnnotationComment(
  selectedText: string,
  note: string,
): string {
  const selection = prepareResponseAnnotationSelection(selectedText);
  const annotation = prepareResponseAnnotationNote(note.trim());
  return truncateCodePoints(
    `选中片段：${selection}\n\n批注：${annotation}`,
    RESPONSE_ANNOTATION_COMMENT_MAX_LENGTH,
  );
}

function elementForNode(node: Node | null): Element | null {
  if (!node) return null;
  return node instanceof Element ? node : node.parentElement;
}

/** Read a browser selection only when both endpoints belong to reply bubbles. */
export function responseSelectionWithin(
  container: HTMLElement,
  selection: Selection | null,
): ResponseTextSelection | null {
  if (!selection || selection.isCollapsed || selection.rangeCount === 0) {
    return null;
  }
  const anchorElement = elementForNode(selection.anchorNode);
  const focusElement = elementForNode(selection.focusNode);
  if (
    !anchorElement ||
    !focusElement ||
    !container.contains(anchorElement) ||
    !container.contains(focusElement) ||
    !anchorElement.closest(".bubble") ||
    !focusElement.closest(".bubble")
  ) {
    return null;
  }
  const text = selection.toString().trim();
  if (!text) return null;
  const rect = selection.getRangeAt(0).getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return null;
  return {
    text,
    anchor: {
      left: rect.left + rect.width / 2,
      top: rect.top,
      height: rect.height,
    },
  };
}

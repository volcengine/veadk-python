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

import { Button } from "@openai/apps-sdk-ui/components/Button";
import { Popover } from "@openai/apps-sdk-ui/components/Popover";
import { Textarea } from "@openai/apps-sdk-ui/components/Textarea";
import { useEffect, useRef, useState } from "react";
import {
  canSubmitResponseAnnotation,
  prepareResponseAnnotationSelection,
  RESPONSE_ANNOTATION_NOTE_MAX_LENGTH,
  type ResponseAnnotationAnchor,
} from "./responseAnnotation";
import "./ResponseAnnotationPopover.css";

interface ResponseAnnotationPopoverProps {
  anchor: ResponseAnnotationAnchor;
  selectedText: string;
  onClose: () => void;
  onSubmit: (note: string) => Promise<void>;
}

export function ResponseAnnotationPopover({
  anchor,
  selectedText,
  onClose,
  onSubmit,
}: ResponseAnnotationPopoverProps) {
  const busyRef = useRef(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [submitted, setSubmitted] = useState(false);
  const excerpt = prepareResponseAnnotationSelection(selectedText);

  busyRef.current = busy;

  useEffect(() => {
    const handleResize = () => {
      if (!busyRef.current) onClose();
    };
    const handleScroll = (event: Event) => {
      const target = event.target;
      if (
        target instanceof Element &&
        target.closest(".response-annotation-popover")
      ) {
        return;
      }
      if (!busyRef.current) onClose();
    };
    window.addEventListener("resize", handleResize);
    window.addEventListener("scroll", handleScroll, true);
    return () => {
      window.removeEventListener("resize", handleResize);
      window.removeEventListener("scroll", handleScroll, true);
    };
  }, [onClose]);

  const submit = async () => {
    if (busy || submitted || !canSubmitResponseAnnotation(note)) return;
    setBusy(true);
    setError("");
    try {
      await onSubmit(note.trim());
      setSubmitted(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Popover
      open
      onOpenChange={(open) => {
        if (!open && !busy) onClose();
      }}
    >
      <Popover.Trigger>
        <span
          className="response-annotation-anchor"
          style={{ left: anchor.left, top: anchor.top, height: anchor.height }}
          aria-hidden="true"
        />
      </Popover.Trigger>
      <Popover.Content
        side="top"
        sideOffset={8}
        align="center"
        minWidth="auto"
        className="response-annotation-popover"
      >
        {submitted ? (
          <div className="response-annotation-success" role="status" aria-live="polite">
            <div>
              <strong>已加入 Bad case 评测集</strong>
              <p>这条批注已关联当前问题和完整模型回复。</p>
            </div>
            <Button
              type="button"
              color="secondary"
              size="sm"
              pill={false}
              onClick={onClose}
            >
              完成
            </Button>
          </div>
        ) : (
          <form
            className="response-annotation-form"
            aria-label="批注选中的模型回复"
            aria-busy={busy || undefined}
            onSubmit={(event) => {
              event.preventDefault();
              void submit();
            }}
          >
            <div className="response-annotation-header">
              <h2>添加批注</h2>
            </div>
            <blockquote title={excerpt}>{excerpt}</blockquote>
            <label className="response-annotation-field">
              <span>批注内容</span>
              <Textarea
                value={note}
                rows={3}
                maxRows={6}
                autoResize
                maxLength={RESPONSE_ANNOTATION_NOTE_MAX_LENGTH}
                disabled={busy}
                invalid={Boolean(error)}
                aria-label="批注内容"
                placeholder="说明问题或期望的修改方式"
                onChange={(event) => {
                  setNote(event.target.value);
                  if (error) setError("");
                }}
              />
            </label>
            {error && (
              <p className="response-annotation-error" role="alert">
                {error}，请重试。
              </p>
            )}
            <div className="response-annotation-actions">
              <Button
                className="response-annotation-action"
                type="button"
                color="secondary"
                variant="ghost"
                size="sm"
                pill={false}
                disabled={busy}
                onClick={onClose}
              >
                取消
              </Button>
              <Button
                className="response-annotation-action"
                type="submit"
                color="primary"
                size="sm"
                pill={false}
                loading={busy}
                disabled={!canSubmitResponseAnnotation(note)}
              >
                加入 Bad Case
              </Button>
            </div>
          </form>
        )}
      </Popover.Content>
    </Popover>
  );
}

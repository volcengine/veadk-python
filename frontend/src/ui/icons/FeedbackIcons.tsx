// Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
// http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import type { SVGProps } from "react";

type FeedbackIconProps = SVGProps<SVGSVGElement> & {
  filled?: boolean;
};

export function FeedbackUpIcon({ filled = false, ...props }: FeedbackIconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <rect x="3.5" y="9.3" width="4.5" height="10.2" rx="1.5" />
      <path d="M8 10.2 11.3 4.8c.5-.8 1.7-.45 1.7.5v3.8h4.2a2.1 2.1 0 0 1 2.04 2.6l-1.4 5.75A2.1 2.1 0 0 1 15.8 19H8" />
    </svg>
  );
}

export function FeedbackDownIcon({ filled = false, ...props }: FeedbackIconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <rect x="3.5" y="4.5" width="4.5" height="10.2" rx="1.5" />
      <path d="M8 13.8 11.3 19.2c.5.8 1.7.45 1.7-.5v-3.8h4.2a2.1 2.1 0 0 0 2.04-2.6l-1.4-5.75A2.1 2.1 0 0 0 15.8 5H8" />
    </svg>
  );
}

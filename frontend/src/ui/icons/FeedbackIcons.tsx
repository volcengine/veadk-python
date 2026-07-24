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

export function FeedbackUpIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="M8.4 10.2 11.8 4.6c.5-.8 1.7-.5 1.7.5v3.8h4.1c1.3 0 2.2 1.2 1.8 2.4l-1.8 6.1c-.2.8-1 1.4-1.8 1.4H8.4" />
      <path d="M4.1 9.9h4.3v9.2H4.1z" />
    </svg>
  );
}

export function FeedbackDownIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      <path d="M8.4 13.8 11.8 19.4c.5.8 1.7.5 1.7-.5v-3.8h4.1c1.3 0 2.2-1.2 1.8-2.4l-1.8-6.1c-.2-.8-1-1.4-1.8-1.4H8.4" />
      <path d="M4.1 4.9h4.3v9.2H4.1z" />
    </svg>
  );
}

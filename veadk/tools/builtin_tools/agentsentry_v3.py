# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""AgentSentry private Moderate V3 transport (Endpoint HMAC credentials).

Only user/before_dispatch and assistant/before_tool_call are supported.
No retries: a timeout is ambiguous and must not silently execute a tool.
"""

import json
import logging
import os
import time
import uuid
from urllib.parse import urlsplit

import requests
from volcengine.auth.SignerV4 import SignerV4
from volcengine.base.Request import Request
from volcengine.Credentials import Credentials

PATH = "/OpenTOP/V3/Lumen/Moderate"
BLOCK = "Your request has been blocked by the security policy."
UNAVAILABLE = "The security service is unavailable. Please try again later."
MISSING_PLAN = "Tool execution requires a visible model plan; none was provided."
UNSUPPORTED_INPUT = (
    "Unsupported input: AgentSentry text moderation requires visible text."
)
MISSING_CALL = "Tool execution could not be correlated with a pending model tool call."
logger = logging.getLogger(__name__)


def enabled_from_env():
    """AGENTSENTRY_ENABLED overrides only private moderation; default is on."""
    raw = os.getenv("AGENTSENTRY_ENABLED", "true").strip().lower()
    if raw not in ("1", "true", "yes", "on", "0", "false", "no", "off"):
        raise ValueError("AGENTSENTRY_ENABLED must be a boolean")
    return raw in ("1", "true", "yes", "on")


class AgentSentryV3:
    def __init__(
        self,
        url,
        *,
        account_id,
        instance_id,
        access_key,
        secret_key,
        region="cn-private",
        timeout=30,
    ):
        parsed = urlsplit(url)
        if (
            parsed.scheme not in ("http", "https")
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.fragment
            or parsed.path.rstrip("/") != PATH
            or parsed.query not in ("", "Version=2025-01-01")
        ):
            raise ValueError("Expected AgentSentry V3 Moderate URL")
        if not all((account_id, instance_id, access_key, secret_key, region)):
            raise ValueError(
                "AgentSentry V3 requires account, instance and Endpoint AK/SK"
            )
        self.url = url.split("?", 1)[0].rstrip("/") + "?Version=2025-01-01"
        self.account_id, self.instance_id = account_id, instance_id
        self.access_key, self.secret_key = access_key, secret_key
        self.region, self.timeout = region, timeout

    @classmethod
    def from_env(cls, url, timeout=30):
        return cls(
            url,
            account_id=os.getenv("AGENTSENTRY_ACCOUNT_ID", ""),
            instance_id=os.getenv("AGENTSENTRY_INSTANCE_ID", ""),
            access_key=os.getenv("AGENTSENTRY_AK", ""),
            secret_key=os.getenv("AGENTSENTRY_SK", ""),
            region=os.getenv("AGENTSENTRY_REGION", "cn-private"),
            timeout=timeout,
        )

    def _headers(self, body):
        parsed = urlsplit(self.url)
        request = Request()
        request.set_schema(parsed.scheme)
        request.set_method("POST")
        request.set_host(parsed.netloc.lower())
        request.set_path(PATH)
        request.set_query({"Version": "2025-01-01"})
        request.set_headers(
            {
                "Content-Type": "application/json",
                "Host": parsed.netloc.lower(),
                "X-Top-Account-Id": self.account_id,
            }
        )
        request.set_body(body.decode("utf-8"))
        SignerV4.sign(
            request,
            Credentials(self.access_key, self.secret_key, "clawsentry", self.region),
        )
        return dict(request.headers)

    def moderate(self, text, *, role, hook_name, session_info=None, tool_calls=None):
        if (role, hook_name) not in (
            ("user", "before_dispatch"),
            ("assistant", "before_tool_call"),
        ):
            raise ValueError("Unsupported AgentSentry V3 role/hook")
        if not isinstance(text, str) or not text.strip():
            return MISSING_PLAN if role == "assistant" else UNSUPPORTED_INPUT
        session = dict(session_info or {})
        for key in ("SessionID", "RunID", "MessageID"):
            session[key] = session.get(key) or str(uuid.uuid4())
        now_ms = time.time_ns() // 1_000_000
        message = {"Role": role, "MultiPart": [{"Content": text, "ContentType": 1}]}
        if tool_calls:
            message["ToolCall"] = tool_calls
        payload = {
            "Base": {"InstanceID": self.instance_id},
            "Message": message,
            "SessionInfo": session,
            "SessionID": session["SessionID"],
            "LocalTimestamp": now_ms // 1000,
            "LocalTimestampMS": now_ms,
            "HookName": hook_name,
            "IsGroup": False,
        }
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        try:
            response = requests.post(
                self.url,
                headers=self._headers(body),
                data=body,
                timeout=self.timeout,
                allow_redirects=False,
            )
            if response.status_code != 200:
                return UNAVAILABLE
            data = response.json()
            result = data.get("Result") or {}
            logger.info(
                "AgentSentry V3 hook=%s request_id=%s decision=%s degraded=%s",
                hook_name,
                (data.get("ResponseMetadata") or {}).get("RequestId"),
                (result.get("Decision") or {}).get("DecisionType"),
                result.get("Degraded"),
            )
            if (data.get("ResponseMetadata") or {}).get("Error"):
                return UNAVAILABLE
            if result.get("Degraded") is not False:
                return UNAVAILABLE
            decision = (result.get("Decision") or {}).get("DecisionType")
            if type(decision) is int and decision == 1:
                return None
            if type(decision) is int and decision == 2:
                return BLOCK
            # REPLACE/unknown decisions are stopped rather than executing unreviewed args.
            return UNAVAILABLE
        except (requests.RequestException, ValueError, TypeError, AttributeError):
            logger.warning("AgentSentry V3 transport or response error")
            return UNAVAILABLE

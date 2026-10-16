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

"""BytePlus OV control-plane signing matching the Johor collection contract."""

import datetime
import hashlib
import hmac
import json
from urllib.parse import urlencode

HOST = "vikingdb.ap-southeast-1.byteplusapi.com"
REGION = "ap-southeast-1"
SERVICE = "vikingdb"
VERSION = "2025-06-09"
ACTIONS = frozenset(
    {"CreateOpenVikingCollection", "GetOpenVikingCollection", "AccessOpenVikingApiKey"}
)


def signed_request(*, action, body, credential):
    """Keep the overseas signing contract independent of domestic callers."""
    import requests

    if action not in ACTIONS:
        raise ValueError("Unsupported OpenViking action")
    path = "/api/openviking/" + action
    query = urlencode({"Action": action, "Version": VERSION})
    payload = json.dumps(body)
    digest = hashlib.sha256(payload.encode()).hexdigest()
    now = datetime.datetime.now(datetime.timezone.utc)
    date = now.strftime("%Y%m%dT%H%M%SZ")
    day = date[:8]
    signed = {
        "content-type": "application/json",
        "host": HOST,
        "x-content-sha256": digest,
        "x-date": date,
    }
    if credential.session_token:
        signed["x-security-token"] = credential.session_token
    header_names = ";".join(sorted(signed))
    canonical_headers = "\n".join(f"{key}:{signed[key]}" for key in sorted(signed))
    canonical_request = "\n".join(
        ["POST", path, query, canonical_headers, "", header_names, digest]
    )
    scope = f"{day}/{REGION}/{SERVICE}/request"
    to_sign = "\n".join(
        [
            "HMAC-SHA256",
            date,
            scope,
            hashlib.sha256(canonical_request.encode()).hexdigest(),
        ]
    )
    signing_key = credential.secret_access_key.encode()
    for part in (day, REGION, SERVICE, "request"):
        signing_key = hmac.new(signing_key, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(signing_key, to_sign.encode(), hashlib.sha256).hexdigest()
    headers = {
        **signed,
        "Accept": "application/json",
        "X-Top-Service": SERVICE,
        "X-Top-Region": REGION,
        "Authorization": f"HMAC-SHA256 Credential={credential.access_key_id}/{scope}, SignedHeaders={header_names}, Signature={signature}",
    }
    response = requests.post(
        f"https://{HOST}{path}?{query}", data=payload, headers=headers, timeout=(10, 30)
    )
    try:
        result = response.json()
    except ValueError:
        response.raise_for_status()
        raise ValueError("Invalid OpenViking response") from None
    # Preserve structured provider errors for classification without exposing messages.
    metadata = result.get("ResponseMetadata") if isinstance(result, dict) else None
    if isinstance(metadata, dict) and isinstance(metadata.get("Error"), dict):
        return result
    response.raise_for_status()
    return result

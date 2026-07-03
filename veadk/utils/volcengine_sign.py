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

import datetime
import hashlib
import hmac
import json
from typing import Literal
from urllib.parse import quote

import requests

# Bounded default (connect, read) timeout in seconds for Volcengine API calls, so a
# hung endpoint cannot block the caller forever. Callers with slow control-plane
# operations (deploys, large uploads) can override via the ``timeout`` parameter.
DEFAULT_REQUEST_TIMEOUT: tuple[float, float] = (10, 60)

Service = ""
Version = ""
Region = ""
Host = ""
ContentType = ""
Scheme = "https"


def norm_query(params):
    query = ""
    for key in sorted(params.keys()):
        if isinstance(params[key], list):
            for k in params[key]:
                query = (
                    query + quote(key, safe="-_.~") + "=" + quote(k, safe="-_.~") + "&"
                )
        else:
            query = (
                query
                + quote(key, safe="-_.~")
                + "="
                + quote(params[key], safe="-_.~")
                + "&"
            )
    query = query[:-1]
    return query.replace("+", "%20")


# 第一步：准备辅助函数。
# sha256 非对称加密
def hmac_sha256(key: bytes, content: str):
    return hmac.new(key, content.encode("utf-8"), hashlib.sha256).digest()


# sha256 hash算法
def hash_sha256(content: str):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _normalize_request_body(request_body):
    if request_body is None:
        return ""
    if isinstance(request_body, (bytes, bytearray)):
        return bytes(request_body)
    if isinstance(request_body, str):
        return request_body
    return json.dumps(request_body)


def _uri_escape(value: str) -> str:
    return quote(str(value), safe="-_.~")


def _normalize_path(path: str) -> str:
    if not path:
        return "/"
    if not path.startswith("/"):
        path = f"/{path}"
    return "/".join(_uri_escape(part) for part in path.split("/")) or "/"


def _normalize_query(query: dict) -> str:
    query_parts = []
    for key in sorted(query.keys()):
        value = query[key]
        values = value if isinstance(value, list) else [value]
        for item in sorted(str(v) for v in values):
            query_parts.append(f"{_uri_escape(key)}={_uri_escape(item)}")
    return "&".join(query_parts)


def volcengine_signed_request(
    request_body,
    ak: str,
    sk: str,
    service: str,
    region: str,
    host: str,
    path: str,
    content_type: str = "application/json",
    header: dict | None = None,
    query: dict | None = None,
    method: Literal["GET", "POST", "PUT", "DELETE"] = "POST",
    scheme: Literal["http", "https"] = "https",
    unsigned_payload: bool = False,
    response_type: Literal["json", "content", "response"] = "json",
    timeout: float | tuple[float, float] | None = DEFAULT_REQUEST_TIMEOUT,
):
    """Send a Volcengine SigV4 request to a concrete path.

    This covers APIs that are not exposed through the Action/Version query style
    used by :func:`ve_request`, such as SkillHub's ``/ListSkills`` and
    ``/DownloadSkill`` endpoints.
    """

    header = dict(header or {})
    query = dict(query or {})
    body = _normalize_request_body(request_body)
    # Some services, including SkillHub, sign the literal UNSIGNED-PAYLOAD while
    # still sending the JSON body in the request.
    body_for_hash = "UNSIGNED-PAYLOAD" if unsigned_payload else body
    if isinstance(body_for_hash, bytes):
        payload_hash = hashlib.sha256(body_for_hash).hexdigest()
    else:
        payload_hash = hash_sha256(body_for_hash)

    now = datetime.datetime.utcnow()
    x_date = now.strftime("%Y%m%dT%H%M%SZ")
    short_x_date = x_date[:8]

    request_host = host
    header.update(
        {
            "Host": request_host,
            "X-Date": x_date,
            "X-Content-Sha256": payload_hash,
            "Content-Type": content_type,
        }
    )

    if header.get("X-Security-Token") == "":
        del header["X-Security-Token"]

    unsignable_headers = {
        "authorization",
        "content-type",
        "content-length",
        "user-agent",
        "presigned-expires",
        "expect",
        "x-content-sha256",
    }
    headers_to_sign = {}
    for key, value in header.items():
        lowered_key = key.lower()
        if lowered_key not in unsignable_headers:
            headers_to_sign[lowered_key] = " ".join(str(value).split())

    signed_header_keys = sorted(headers_to_sign.keys())
    canonical_headers = "\n".join(
        f"{key}:{headers_to_sign[key]}" for key in signed_header_keys
    )
    signed_headers_str = ";".join(signed_header_keys)
    canonical_request_str = "\n".join(
        [
            method.upper(),
            _normalize_path(path),
            _normalize_query(query),
            canonical_headers + "\n",
            signed_headers_str,
            payload_hash,
        ]
    )

    credential_scope = "/".join([short_x_date, region, service, "request"])
    string_to_sign = "\n".join(
        [
            "HMAC-SHA256",
            x_date,
            credential_scope,
            hash_sha256(canonical_request_str),
        ]
    )

    k_date = hmac_sha256(sk.encode("utf-8"), short_x_date)
    k_region = hmac_sha256(k_date, region)
    k_service = hmac_sha256(k_region, service)
    k_signing = hmac_sha256(k_service, "request")
    signature = hmac_sha256(k_signing, string_to_sign).hex()
    header["Authorization"] = (
        "HMAC-SHA256 Credential={}, SignedHeaders={}, Signature={}".format(
            ak + "/" + credential_scope,
            signed_headers_str,
            signature,
        )
    )

    response = requests.request(
        method=method,
        url=f"{scheme}://{request_host}{_normalize_path(path)}",
        headers=header,
        params=query,
        data=body,
        timeout=timeout,
    )
    response.raise_for_status()
    if response_type == "content":
        return response.content
    if response_type == "response":
        return response
    try:
        return response.json()
    except Exception:
        raise ValueError(f"Error occurred. Bad response: {response}")


# 第二步：签名请求函数
def request(
    method,
    date,
    query,
    header,
    ak,
    sk,
    action,
    body,
    scheme: Literal["http", "https"] = "https",
    timeout: float | tuple[float, float] | None = DEFAULT_REQUEST_TIMEOUT,
):
    # 第三步：创建身份证明。其中的 Service 和 Region 字段是固定的。ak 和 sk 分别代表
    # AccessKeyID 和 SecretAccessKey。同时需要初始化签名结构体。一些签名计算时需要的属性也在这里处理。
    # 初始化身份证明结构体
    credential = {
        "access_key_id": ak,
        "secret_access_key": sk,
        "service": Service,
        "region": Region,
    }
    # 初始化签名结构体
    request_param = {
        "body": body,
        "host": Host,
        "path": "/",
        "method": method,
        "content_type": ContentType,
        "date": date,
        "query": {"Action": action, "Version": Version, **query},
    }
    if body is None:
        request_param["body"] = ""
    # 第四步：接下来开始计算签名。在计算签名前，先准备好用于接收签算结果的 signResult 变量，并设置一些参数。
    # 初始化签名结果的结构体
    x_date = request_param["date"].strftime("%Y%m%dT%H%M%SZ")
    short_x_date = x_date[:8]
    x_content_sha256 = hash_sha256(request_param["body"])
    sign_result = {
        "Host": request_param["host"],
        "X-Content-Sha256": x_content_sha256,
        "X-Date": x_date,
        "Content-Type": request_param["content_type"],
    }
    # 第五步：计算 Signature 签名。
    signed_headers_str = ";".join(
        ["content-type", "host", "x-content-sha256", "x-date"]
    )
    # signed_headers_str = signed_headers_str + ";x-security-token"
    canonical_request_str = "\n".join(
        [
            request_param["method"].upper(),
            request_param["path"],
            norm_query(request_param["query"]),
            "\n".join(
                [
                    "content-type:" + request_param["content_type"],
                    "host:" + request_param["host"],
                    "x-content-sha256:" + x_content_sha256,
                    "x-date:" + x_date,
                ]
            ),
            "",
            signed_headers_str,
            x_content_sha256,
        ]
    )

    # 打印正规化的请求用于调试比对
    # print(canonical_request_str)
    hashed_canonical_request = hash_sha256(canonical_request_str)

    # 打印hash值用于调试比对
    # print(hashed_canonical_request)
    credential_scope = "/".join(
        [short_x_date, credential["region"], credential["service"], "request"]
    )
    string_to_sign = "\n".join(
        ["HMAC-SHA256", x_date, credential_scope, hashed_canonical_request]
    )

    # 打印最终计算的签名字符串用于调试比对
    # print(string_to_sign)
    k_date = hmac_sha256(credential["secret_access_key"].encode("utf-8"), short_x_date)
    k_region = hmac_sha256(k_date, credential["region"])
    k_service = hmac_sha256(k_region, credential["service"])
    k_signing = hmac_sha256(k_service, "request")
    signature = hmac_sha256(k_signing, string_to_sign).hex()

    sign_result["Authorization"] = (
        "HMAC-SHA256 Credential={}, SignedHeaders={}, Signature={}".format(
            credential["access_key_id"] + "/" + credential_scope,
            signed_headers_str,
            signature,
        )
    )
    header = {**header, **sign_result}
    if "X-Security-Token" in header and header["X-Security-Token"] == "":
        del header["X-Security-Token"]
    # header = {**header, **{"X-Security-Token": SessionToken}}
    # 第六步：将 Signature 签名写入 HTTP Header 中，并发送 HTTP 请求。
    r = requests.request(
        method=method,
        url=f"{scheme}://{request_param['host']}{request_param['path']}",
        headers=header,
        params=request_param["query"],
        data=request_param["body"],
        timeout=timeout,
    )
    try:
        return r.json()
    except Exception:
        raise ValueError(f"Error occurred. Bad response: {r}")


def ve_request(
    request_body: dict,
    action: str,
    ak: str,
    sk: str,
    service: str,
    version: str,
    region: str,
    host: str,
    content_type: str = "application/json",
    header: dict = {},
    query: dict = {},
    method: Literal["GET", "POST", "PUT", "DELETE"] = "POST",
    scheme: Literal["http", "https"] = "https",
):
    global Service
    Service = service
    global Version
    Version = version
    global Region
    Region = region
    global Host
    Host = host
    global ContentType
    ContentType = content_type
    global Scheme
    Scheme = scheme
    AK = ak
    SK = sk
    now = datetime.datetime.utcnow()
    # Body的格式需要配合Content-Type，API使用的类型请阅读具体的官方文档，如:json格式需要json.dumps(obj)
    # response_body = request("GET", now, {"Limit": "2"}, {}, AK, SK, "ListUsers", None)
    import json

    try:
        response_body = request(
            method,
            now,
            query,
            header,
            AK,
            SK,
            action,
            json.dumps(request_body),
            Scheme,
        )
        return response_body
    except Exception as e:
        raise e

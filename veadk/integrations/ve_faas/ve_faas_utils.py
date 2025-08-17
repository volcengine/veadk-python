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

# This file is partly adapted from https://github.com/volcengine/mcp-server/blob/main/server/mcp_server_vefaas_function/src/mcp_server_vefaas_function/vefaas_server.py

import base64
import datetime
import hashlib
import hmac
import json
import os
import shutil
import subprocess
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Tuple
from urllib.parse import quote

import requests
from volcenginesdkcore.rest import ApiException

Service = "apig"
Version = "2021-03-03"
Region = "cn-beijing"
Host = "iam.volcengineapi.com"
ContentType = "application/x-www-form-urlencoded"


def ensure_executable_permissions(folder_path: str):
    for root, _, files in os.walk(folder_path):
        for fname in files:
            full_path = os.path.join(root, fname)
            if fname.endswith(".sh") or fname in ("run.sh",):
                os.chmod(full_path, 0o755)


def python_zip_implementation(folder_path: str) -> bytes:
    """Pure Python zip implementation with permissions support"""
    buffer = BytesIO()

    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(folder_path):
            for file in files:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, folder_path)

                # Skip excluded paths and binary/cache files
                if any(
                    excl in arcname for excl in [".git", ".venv", "__pycache__", ".pyc"]
                ):
                    continue

                try:
                    st = os.stat(file_path)
                    dt = datetime.datetime.fromtimestamp(st.st_mtime)
                    date_time = (
                        dt.year,
                        dt.month,
                        dt.day,
                        dt.hour,
                        dt.minute,
                        dt.second,
                    )

                    info = zipfile.ZipInfo(arcname)
                    info.external_attr = 0o755 << 16  # rwxr-xr-x
                    info.date_time = date_time

                    with open(file_path, "rb") as f:
                        zipf.writestr(info, f.read())
                except Exception as e:
                    print(f"Warning: Skipping file {arcname} due to error: {str(e)}")

    print(f"Your .zip project size: {buffer.tell() / 1024 / 1024:.2f} MB")
    return buffer.getvalue()


def zip_and_encode_folder(folder_path: str) -> Tuple[bytes, int, Exception]:
    """
    Zips a folder with system zip command (if available) or falls back to Python implementation.
    Returns (zip_data, size_in_bytes, error) tuple.
    """
    # Check for system zip first
    if not shutil.which("zip"):
        print("System zip command not found, using Python implementation")
        try:
            data = python_zip_implementation(folder_path)
            return data, len(data), None
        except Exception as e:
            return None, 0, e

    # print(f"Zipping folder: {folder_path}")
    try:
        ensure_executable_permissions(folder_path)
        # Create zip process with explicit arguments
        proc = subprocess.Popen(
            [
                "zip",
                "-r",
                "-q",
                "-",
                ".",
                "-x",
                "*.git*",
                "-x",
                "*.venv*",
                "-x",
                "*__pycache__*",
                "-x",
                "*.pyc",
            ],
            cwd=folder_path,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=1024 * 8,  # 8KB buffer
        )

        # Collect output with proper error handling
        try:
            stdout, stderr = proc.communicate(timeout=30)
            if proc.returncode != 0:
                print(f"Zip error: {stderr.decode()}")
                data = python_zip_implementation(folder_path)
                return data, len(data), None

            if stdout:
                size = len(stdout)
                # print(f"Zip finished, size: {size / 1024 / 1024:.2f} MB")
                return stdout, size, None
            else:
                print("No data from zip command, falling back to Python implementation")
                data = python_zip_implementation(folder_path)
                return data, len(data), None

        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)  # Give it 5 seconds to cleanup
            print("Zip process timed out, falling back to Python implementation")
            try:
                data = python_zip_implementation(folder_path)
                return data, len(data), None
            except Exception as e:
                return None, 0, e

    except Exception as e:
        print(f"System zip error: {str(e)}")
        try:
            data = python_zip_implementation(folder_path)
            return data, len(data), None
        except Exception as e2:
            return None, 0, e2


def get_project_path() -> str:
    """Pack the whole project into a zip file."""
    proj_dir = Path(__file__).parent.parent.parent
    return proj_dir


def encoding():
    with open("/root/test_data/test_zip.zip", "rb") as zip_file:
        zip_binary = zip_file.read()
        zip_base64 = base64.b64encode(zip_binary).decode("utf-8")
    return zip_base64


def hmac_sha256(key: bytes, content: str):
    return hmac.new(key, content.encode("utf-8"), hashlib.sha256).digest()


def hash_sha256(content: str):
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


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


def request(method, date, query, header, ak, sk, token, action, body):
    credential = {
        "access_key_id": ak,
        "secret_access_key": sk,
        "service": Service,
        "region": Region,
    }

    if token is not None:
        credential["session_token"] = token

    if action in [
        "CodeUploadCallback",
        "CreateDependencyInstallTask",
        "GetReleaseStatus",
        "GetDependencyInstallTaskStatus",
    ]:
        credential["service"] = "vefaas"

    content_type = ContentType
    version = Version
    if method == "POST":
        content_type = "application/json"

    if action == "CreateRoute" or action == "ListRoutes":
        version = "2022-11-12"

    request_param = {
        "body": body,
        "host": Host,
        "path": "/",
        "method": method,
        "content_type": content_type,
        "date": date,
        "query": {"Action": action, "Version": version, **query},
    }
    if body is None:
        request_param["body"] = ""

    x_date = request_param["date"].strftime("%Y%m%dT%H%M%SZ")
    short_x_date = x_date[:8]
    x_content_sha256 = hash_sha256(request_param["body"])
    sign_result = {
        "Host": request_param["host"],
        "X-Content-Sha256": x_content_sha256,
        "X-Date": x_date,
        "Content-Type": request_param["content_type"],
    }

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

    hashed_canonical_request = hash_sha256(canonical_request_str)

    credential_scope = "/".join(
        [short_x_date, credential["region"], credential["service"], "request"]
    )
    string_to_sign = "\n".join(
        ["HMAC-SHA256", x_date, credential_scope, hashed_canonical_request]
    )

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
    header = {**header, **{"X-Security-Token": token}}
    r = requests.request(
        method=method,
        url="https://{}{}".format(request_param["host"], request_param["path"]),
        headers=header,
        params=request_param["query"],
        data=request_param["body"],
    )
    return r.json()


def signed_request(ak: str, sk: str, target: str, body: dict):
    now = datetime.datetime.utcnow()

    try:
        response_body = request(
            "POST",
            now,
            {},
            {},
            ak,
            sk,
            "",
            target,
            json.dumps(body),
        )
        return response_body
    except Exception as e:
        error_message = f"Error creating upstream: {str(e)}"
        raise ValueError(error_message)
    except ApiException as e:
        print("Exception when calling API: %s\n" % e)


def create_api_gateway_trigger(
    ak, sk, function_id: str, api_gateway_id: str, service_id: str, region: str = None
):
    token = ""

    now = datetime.datetime.utcnow()

    body = {
        "Name": f"{function_id}-trigger",
        "GatewayId": api_gateway_id,
        "SourceType": "VeFaas",
        "UpstreamSpec": {"VeFaas": {"FunctionId": function_id}},
    }

    try:
        response_body = request(
            "POST", now, {}, {}, ak, sk, token, "CreateUpstream", json.dumps(body)
        )
        # Print the full response for debugging
        # print(f"Response: {json.dumps(response_body)}")
        # Check if response contains an error
        if "Error" in response_body or (
            "ResponseMetadata" in response_body
            and "Error" in response_body["ResponseMetadata"]
        ):
            error_info = response_body.get("Error") or response_body[
                "ResponseMetadata"
            ].get("Error")
            error_message = f"API Error: {error_info.get('Message', 'Unknown error')}"
            raise ValueError(error_message)

        # Check if Result exists in the response
        if "Result" not in response_body:
            raise ValueError(f"API call did not return a Result field: {response_body}")

        upstream_id = response_body["Result"]["Id"]
    except Exception as e:
        error_message = f"Error creating upstream: {str(e)}"
        raise ValueError(error_message)

    body = {
        "Name": "router1",
        "UpstreamList": [{"Type": "VeFaas", "UpstreamId": upstream_id, "Weight": 100}],
        "ServiceId": service_id,
        "MatchRule": {
            "Method": ["POST", "GET", "PUT", "DELETE", "HEAD", "OPTIONS"],
            "Path": {"MatchType": "Prefix", "MatchContent": "/"},
        },
        "AdvancedSetting": {
            "TimeoutSetting": {"Enable": False, "Timeout": 30},
            "CorsPolicySetting": {"Enable": False},
        },
    }
    try:
        response_body = request(
            "POST", now, {}, {}, ak, sk, token, "CreateRoute", json.dumps(body)
        )
    except Exception as e:
        error_message = f"Error creating route: {str(e)}"
        raise ValueError(error_message)
    return response_body


def list_routes(ak, sk, upstream_id: str):
    now = datetime.datetime.utcnow()
    token = ""

    body = {"UpstreamId": upstream_id}

    response_body = request(
        "POST", now, {}, {}, ak, sk, token, "ListRoutes", json.dumps(body)
    )
    return response_body

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

# This file is adapted from https://github.com/volcengine/mcp-server/blob/main/server/mcp_server_veapig/src/mcp_server_veapig/veapig_server.py

import datetime
import hashlib
import hmac
import json
from urllib.parse import quote

import requests

Service = "apig"
Version = "2021-03-03"
Region = "cn-beijing"
Host = "iam.volcengineapi.com"
ContentType = "application/json"


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


def request(method, date, query, header, region, ak, sk, token, action, body):
    # 第三步：创建身份证明。其中的 Service 和 Region 字段是固定的。ak 和 sk 分别代表
    # AccessKeyID 和 SecretAccessKey。同时需要初始化签名结构体。一些签名计算时需要的属性也在这里处理。
    # 初始化身份证明结构体

    credential = {
        "access_key_id": ak,
        "secret_access_key": sk,
        "service": Service,
        "region": region,
    }

    if token is not None:
        credential["session_token"] = token

    content_type = ContentType
    version = Version
    if action == "CreateRoute" or action == "ListRoutes" or action == "GetRoute":
        version = "2022-11-12"

    # 初始化签名结构体
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
    hashed_canonical_request = hash_sha256(canonical_request_str)

    # 打印hash值用于调试比对
    credential_scope = "/".join(
        [short_x_date, credential["region"], credential["service"], "request"]
    )
    string_to_sign = "\n".join(
        ["HMAC-SHA256", x_date, credential_scope, hashed_canonical_request]
    )

    # 打印最终计算的签名字符串用于调试比对
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
    header = {"Region": region, **header, **sign_result}
    header = {**header, **{"X-Security-Token": token}}
    # 第六步：将 Signature 签名写入 HTTP Header 中，并发送 HTTP 请求。
    r = requests.request(
        method=method,
        url="https://{}{}".format(request_param["host"], request_param["path"]),
        headers=header,
        params=request_param["query"],
        data=request_param["body"],
    )
    return r.json()


def validate_and_set_region(region: str = "cn-beijing") -> str:
    """
    Validates the provided region and returns the default if none is provided.

    Args:
        region: The region to validate

    Returns:
        A valid region string

    Raises:
        ValueError: If the provided region is invalid
    """
    valid_regions = ["ap-southeast-1", "cn-beijing", "cn-shanghai", "cn-guangzhou"]
    if region:
        if region not in valid_regions:
            raise ValueError(
                f"Invalid region. Must be one of: {', '.join(valid_regions)}"
            )
    else:
        region = "cn-beijing"
    return region


# Uniformly process requests and send requests
def handle_request(ak, sk, region, action, body) -> str:
    """
    Uniformly process and send requests.

    Args:
        region(str): The region of the request.
        action (str): The name of the operation to be performed by the request.
        body (dict): The main content of the request, stored in a dictionary.

    Returns:
        str: The response body of the request.
    """
    date = datetime.datetime.utcnow()

    token = ""

    response_body = request(
        "POST", date, {}, {}, region, ak, sk, token, action, json.dumps(body)
    )
    return response_body


def create_serverless_gateway(
    ak, sk, name: str = "", region: str = "cn-beijing"
) -> str:
    """
    Creates a new VeApig serverless gateway.

    Args:
        name (str): The name of the serverless gateway. If not provided, a random name will be generated.
        region (str): The region where the serverless gateway will be created. Default is cn-beijing.

    Returns:
        str: The response body of the request.
    """
    gateway_name = name
    region = validate_and_set_region(region)
    body = {
        "Name": gateway_name,
        "Region": region,
        "Type": "serverless",
        "ResourceSpec": {
            "Replicas": 2,
            "InstanceSpecCode": "1c2g",
            "CLBSpecCode": "small_1",
            "PublicNetworkBillingType": "traffic",
            "NetworkType": {"EnablePublicNetwork": True, "EnablePrivateNetwork": False},
        },
    }
    try:
        response = handle_request(ak, sk, region, "CreateGateway", body)
        return response
    except Exception as e:
        return f"Failed to create VeApig serverless gateway with name {gateway_name}: {str(e)}"


def create_gateway_service(
    ak, sk, gateway_id: str, name: str = "", region: str = "cn-beijing"
) -> str:
    """
    Creates a new VeApig serverless gateway service.

    Args:
        gateway_id (str): The id of the serverless gateway where the service will be created.
        name (str): The name of the serverless gateway service. If not provided, a random name will be generated.
        region (str): The region where the serverless gateway service will be created. Default is cn-beijing.

    Returns:
        str: The response body of the request.
    """

    service_name = name
    region = validate_and_set_region(region)
    body = {
        "ServiceName": service_name,
        "GatewayId": gateway_id,
        "Protocol": ["HTTP", "HTTPS"],
        "AuthSpec": {"Enable": False},
    }

    try:
        response = handle_request(ak, sk, region, "CreateGatewayService", body)
        return response
    except Exception as e:
        return f"Failed to create VeApig serverless gateway service with name {service_name}: {str(e)}"


def list_gateways(ak, sk, region: str = "cn-beijing") -> str:
    # Validate region parameter
    region = validate_and_set_region(region)

    # Construct the request parameter body of the tool in JSON format
    body = {"PageNumber": 1, "PageSize": 100}

    # Set the action for the request
    action = "ListGateways"

    # Send the request and return the response body
    response_body = handle_request(ak, sk, region, action, body)
    return response_body


def list_gateway_services(
    ak, sk, gateway_id: str = "", region: str = "cn-beijing"
) -> str:
    # Validate region parameter
    region = validate_and_set_region(region)

    # Construct the request parameter body of the tool in JSON format
    body = {
        "PageNumber": 1,
        "PageSize": 100,
        "GatewayId": gateway_id,
    }

    # Set the action for the request
    action = "ListGatewayServices"

    # Send the request and return the response body
    response_body = handle_request(ak, sk, region, action, body)
    return response_body


def get_gateway_route(ak, sk, route_id: str, region: str = "cn-beijing") -> str:
    """
    Gets detailed informantion about a specific VeApig route.

    Args:
        route_id (str): The id of the route.
        region (str): The region where the route is located.

    Returns:
        str: The response body of the request.
    """
    region = validate_and_set_region(region)
    body = {
        "Id": route_id,
    }
    try:
        response = handle_request(ak, sk, region, "GetRoute", body)
        return response
    except Exception as e:
        return f"Failed to get VeApig route with id {route_id}: {str(e)}"

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

"""Policies required by Studio's VeFaaS ``ServerlessApplicationRole``."""

SYSTEM_POLICIES: tuple[str, ...] = (
    "CloudMonitorReadOnlyAccess",
    "VPCFullAccess",
    "TLSFullAccess",
    "APIGFullAccess",
    "ECSFullAccess",
    "VeFaaSFullAccess",
    "STSAssumeRoleAccess",
)

TRUST_POLICY: dict = {
    "Statement": [
        {
            "Effect": "Allow",
            "Action": ["sts:AssumeRole"],
            "Principal": {"Service": ["vefaas_dev", "vefaas"]},
        }
    ]
}

CUSTOM_POLICY: dict = {
    "Statement": [
        {
            "Effect": "Allow",
            "Action": ["vefaas:*", "vefaas_dev:*"],
            "Resource": ["*"],
        },
        {
            "Effect": "Allow",
            "Action": [
                "apig:GetGateway",
                "apig:ListGateways",
                "apig:ListGatewayServices",
                "apig:GetGatewayService",
                "apig:DeleteGatewayService",
                "apig:CreateUpstream",
                "apig:CheckUpstreamSpecExist",
                "apig:GetUpstream",
                "apig:DeleteUpstream",
                "apig:CreateRoute",
                "apig:UpdateRoute",
                "apig:ListRoutes",
                "apig:DeleteRoute",
            ],
            "Resource": ["*"],
        },
        {
            "Effect": "Allow",
            "Action": [
                "vpc:DescribeVpcs",
                "vpc:DescribeVpcAttributes",
                "vpc:DescribeSubnets",
                "vpc:DescribeSubnetAttributes",
                "vpc:DescribeSecurityGroups",
                "vpc:DescribeSecurityGroupAttributes",
            ],
            "Resource": ["*"],
        },
        {
            "Effect": "Allow",
            "Action": [
                "tls:DescribeProject",
                "tls:DescribeProjects",
                "tls:DescribeTopic",
                "tls:DescribeTopics",
                "tls:DescribeIndex",
                "tls:DescribeIndexConfig",
                "tls:DescribeHistogram",
                "tls:DescribeHistogramV1",
                "tls:DescribeSavedSearches",
                "tls:SearchLogs",
                "tls:Statistics",
            ],
            "Resource": ["*"],
        },
        {
            "Effect": "Allow",
            "Action": [
                "cr:ListRegistries",
                "cr:ListRepositories",
                "cr:ListNamespaces",
                "cr:ListTags",
            ],
            "Resource": ["*"],
        },
        {
            "Effect": "Allow",
            "Action": [
                "kafka:DescribeKafkaInstances",
                "kafka:DescribeInstanceDetail",
                "kafka:DescribeTopics",
                "kafka:DescribeUsers",
            ],
            "Resource": ["*"],
        },
        {
            "Effect": "Allow",
            "Action": [
                "rocketmq:ListInstances",
                "rocketmq:ListTopics",
                "rocketmq:ListGroups",
                "rocketmq:GetInstance",
            ],
            "Resource": ["*"],
        },
        {
            "Effect": "Allow",
            "Action": [
                "tos:PutBucketNotification",
                "tos:GetBucketNotification",
                "tos:ListBuckets",
                "tos:ListBucket",
                "tos:HeadBucket",
                "tos:GetObject",
            ],
            "Resource": ["*"],
        },
        {
            "Effect": "Allow",
            "Action": ["apmplus_server:GetMetricsData", "apmplus_server:Draw"],
            "Resource": ["*"],
        },
        {
            "Effect": "Allow",
            "Action": ["bill_volcano_engine:ListResourcePackage"],
            "Resource": ["*"],
        },
        {
            "Effect": "Allow",
            "Action": ["iam:ListRoles"],
            "Resource": ["*"],
        },
        {
            "Effect": "Allow",
            "Action": [
                "filenas:DescribeFileSystems",
                "filenas:DescribeMountPoints",
                "filenas:DescribeMountedClients",
            ],
            "Resource": ["*"],
        },
    ]
}

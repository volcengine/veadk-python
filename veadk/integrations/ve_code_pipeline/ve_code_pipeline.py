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

import json
from string import Template

import requests
from veadk.config import getenv
from veadk.utils.logger import get_logger
from veadk.utils.misc import formatted_timestamp
from veadk.utils.volcengine_sign import ve_request

logger = get_logger(__name__)

SPEC = Template("""version: 1.0.0
agentPool: public/prod-v2-public
sources:
    - name: ${code_connection_name}
      type: Github
      url: ${github_url}
      branch: ${github_branch}                            
      branchingModel: false
      credential:
        type: serviceConnection
        serviceConnectionId: ${code_connection_id}
      cloneDepth: 1                                     
stages:
    - stage: stage-1
      displayName: 函数构建
      tasks:
        - task: task-1
          displayName: 函数构建
          timeout: 2h
          steps:
            - step: step-c1
              displayName: 镜像构建推送到镜像仓库服务
              component: build@2.0.0/buildkit-cr@3.0.0
              inputs:
                buildParams: ""
                compression: gzip
                contextPath: .
                crDomain: ${cr_domain}
                crNamespace: ${cr_namespace_name}
                crRegion: ${cr_region}
                crRegistryInstance: ${cr_instance_name}
                crRepo: ${cr_repo}
                crTag: $(DATETIME)
                disableSSLVerify: false
                dockerfiles:
                    default:
                        content: |-
                            ${docker_file}
                loginCredential: []
                useCache: false
          outputs:
            - imageOutput_step-c1
          workspace:
            resources:
                - ref: ${code_connection_name}
                  directory: $(CP_WORKSPACE)
          resourcesPolicy: all
          resources:
            limits:
                cpu: 1C
                memory: 2Gi
    - stage: stage-2
      displayName: 函数部署
      tasks:
        - task: task-2
          displayName: 函数部署
          component: deploy@1.0.0/faas-deploy
          inputs:
            artifact:
                mode: output
                type: image
                value: $(stages.stage-1.tasks.task-1.outputs.imageOutput_step-c1)
            deployPolicy:
                type: full
            functionId: ${function_id}
            functionVersion: 0
            region: cn-beijing
          outputs:
            - releaseId
            - releaseStatus
          workspace: {}
""")


def get_dockerfile(tag: str = "latest") -> str:
    dockerfile = f"""FROM veadk-cn-beijing.cr.volces.com/veadk/veadk-python:{tag}
                                WORKDIR /app
                                COPY . .
                                RUN pip3 install --no-cache-dir -r requirements.txt
                                ENTRYPOINT ["bash", "./run.sh"]"""
    return dockerfile


class VeCodePipeline:
    def __init__(
        self,
        volcengine_access_key: str = getenv("VOLCENGINE_ACCESS_KEY"),
        volcengine_secret_key: str = getenv("VOLCENGINE_SECRET_KEY"),
        region: str = "cn-beijing",
    ) -> None:
        self.volcengine_access_key = volcengine_access_key
        self.volcengine_secret_key = volcengine_secret_key
        self.region = region

        self.service = "CP"
        self.version = "2023-05-01"
        self.host = "open.volcengineapi.com"
        self.content_type = "application/json"

    def _create_code_connection(
        self, github_token: str, github_url: str
    ) -> tuple[str, str]:
        logger.info("Creating code connection...")

        conn_name = f"veadk-conn-{formatted_timestamp()}"
        res = ve_request(
            request_body={
                "Id": f"VEADK_CONN_{formatted_timestamp()}",
                "Name": conn_name,
                "Description": "Created by Volcengine Agent Development Kit (VeADK)",
                "Type": "Github",
                "Credential": {"Token": github_token},
                "IsAllWsShared": True,
                "URL": github_url,
            },
            action="CreateServiceConnection",
            ak=self.volcengine_access_key,
            sk=self.volcengine_secret_key,
            service=self.service,
            version=self.version,
            region=self.region,
            host=self.host,
            content_type=self.content_type,
        )

        try:
            logger.info(
                f"Code connection created successfully, code connection id {res['Result']['Id']}",
            )
            return res["Result"]["Id"], conn_name
        except KeyError:
            raise Exception(f"Create code connection failed: {res}")

    def _get_default_workspace(self) -> str:
        logger.info("Getting default workspace...")

        res = ve_request(
            request_body={},
            action="GetDefaultWorkspaceInner",
            ak=self.volcengine_access_key,
            sk=self.volcengine_secret_key,
            service=self.service,
            version=self.version,
            region=self.region,
            host=self.host,
            content_type=self.content_type,
        )

        try:
            logger.info(
                f"Default workspace retrieved successfully, workspace id {res['Result']['Id']}",
            )
            return res["Result"]["Id"]
        except KeyError:
            raise Exception(f"Get default workspace failed: {res}")

    def _create_pipeline(
        self,
        workspace_id: str,
        code_connection_id: str,
        code_connection_name: str,
        github_url: str,
        github_branch: str,
        cr_domain: str,
        cr_namespace_name: str,
        cr_region: str,
        cr_instance_name: str,
        cr_repo: str,
        docker_file: str,
        function_id: str,
    ) -> str:
        logger.info("Creating pipeline...")

        spec = SPEC.safe_substitute(
            github_url=github_url,
            github_branch=github_branch,
            workspace_id=workspace_id,
            code_connection_id=code_connection_id,
            code_connection_name=code_connection_name,
            cr_domain=cr_domain,
            cr_namespace_name=cr_namespace_name,
            cr_region=cr_region,
            cr_instance_name=cr_instance_name,
            cr_repo=cr_repo,
            docker_file=docker_file,
            function_id=function_id,
        )

        print(spec)

        res = ve_request(
            request_body={
                "WorkspaceId": workspace_id,
                "Name": f"veadk-pipeline-{formatted_timestamp()}",
                "spec": spec,
            },
            action="CreatePipeline",
            ak=self.volcengine_access_key,
            sk=self.volcengine_secret_key,
            service="CP",
            version="2023-05-01",
            region="cn-beijing",
            host="open.volcengineapi.com",
            content_type="application/json",
        )

        try:
            logger.info(
                f"Pipeline created successfully, pipeline id {res['Result']['Id']}",
            )
            return res["Result"]["Id"]
        except KeyError:
            raise Exception(f"Create pipeline failed: {res}")

    def _create_webhook_trigger(self, workspace_id: str, pipeline_id: str) -> str:
        logger.info("Creating webhook trigger...")

        res = ve_request(
            request_body={
                "WorkspaceId": workspace_id,
                "PipelineId": pipeline_id,
                "Type": "GitWebhook",
            },
            action="CreatePipelineWebhookURL",
            ak=self.volcengine_access_key,
            sk=self.volcengine_secret_key,
            service=self.service,
            version=self.version,
            region=self.region,
            host=self.host,
            content_type=self.content_type,
        )

        webhook_url = ""
        try:
            logger.info(
                f"Webhook trigger created successfully, webhook trigger url {res['Result']['WebhookURL']}",
            )
            webhook_url = res["Result"]["WebhookURL"]
        except KeyError:
            raise Exception(f"Create webhook trigger failed: {res}")

        # create a trigger with webhook url and pipeline id

        return webhook_url

    def _set_github_webhook(
        self, webhook_url: str, github_url: str, github_token: str
    ) -> None:
        logger.info("Setting GitHub webhook...")

        github_url = github_url.replace("https://", "").replace("http://", "")
        github_url_parts = [part for part in github_url.split("/") if part]
        owner = github_url_parts[-2]
        repo = github_url_parts[-1]

        logger.debug(f"Parsed GitHub URL, owner: {owner}, repo: {repo}")

        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {github_token}",
            "X-GitHub-Api-Version": "2022-11-28",
            "Content-Type": "application/json",
        }

        webhook_config = {
            "name": "web",
            "active": True,
            "events": ["push"],
            "config": {"url": webhook_url, "content_type": "json", "insecure_ssl": "1"},
        }

        try:
            response = requests.post(
                url=f"https://api.github.com/repos/{owner}/{repo}/hooks",
                headers=headers,
                data=json.dumps(webhook_config),
            )

            if response.status_code == 201:
                logger.info("Create github Webhook successfully.")
                result = response.json()
                logger.info(
                    f"Webhook ID: {result['id']}, Webhook URL: {result['url']}, Listening events: {', '.join(result['events'])}"
                )
                return result
            else:
                logger.error(f"Create Webhook failed: HTTP {response.status_code}")
                logger.error(f"Error message: {response.text}")
                return None

        except requests.exceptions.RequestException as e:
            logger.error(f"Request exception: {e}")
            return None

    def _create_trigger(
        self,
        workspace_id: str,
        pipeline_id: str,
        webhook_url: str,
        code_connection_name: str,
        github_branch: str,
    ) -> None:
        """Create and bind a trigger to pipeline instance with webhook url."""
        logger.info("Creating trigger and bind it to pipeline instance...")

        res = ve_request(
            request_body={
                "WorkspaceId": workspace_id,
                "PipelineId": pipeline_id,
                "Name": f"veadk-event-trigger-{formatted_timestamp()}",
                "Type": "GitWebhook",
                "Configuration": {
                    "Webhook": {
                        "URL": webhook_url,
                        "Git": {
                            "SourceName": code_connection_name,
                            "Filters": [
                                {
                                    "EventType": "Push",
                                    "Config": {"References": [github_branch]},
                                },
                                {
                                    "EventType": "CreateTag",
                                    "Config": {"References": []},
                                },
                            ],
                            "TriggerExecutionType": "AllEvents",
                        },
                    }
                },
                "Sources": [
                    {
                        "SourceName": code_connection_name,
                        "Reference": "main",
                    }
                ],
            },
            action="CreateTrigger",
            ak=self.volcengine_access_key,
            sk=self.volcengine_secret_key,
            service=self.service,
            version=self.version,
            region=self.region,
            host=self.host,
            content_type=self.content_type,
        )

        try:
            logger.info(
                f"Trigger created and bind successfully, result Id is {res['Result']['Id']}",
            )
        except KeyError:
            raise Exception(f"Create webhook trigger failed: {res}")

    def deploy(
        self,
        base_image_tag: str,
        github_url: str,
        github_branch: str,
        github_token: str,
        cr_domain: str,
        cr_namespace_name: str,
        cr_region: str,
        cr_instance_name: str,
        cr_repo: str,
        function_id: str,
    ) -> str:
        workspace_id = self._get_default_workspace()

        code_connection_id, code_connection_name = self._create_code_connection(
            github_token=github_token, github_url=github_url
        )

        pipeline_id = self._create_pipeline(
            workspace_id=workspace_id,
            code_connection_id=code_connection_id,
            code_connection_name=code_connection_name,
            github_url=github_url,
            github_branch=github_branch,
            cr_domain=cr_domain,
            cr_namespace_name=cr_namespace_name,
            cr_region=cr_region,
            cr_instance_name=cr_instance_name,
            cr_repo=cr_repo,
            docker_file=get_dockerfile(tag=base_image_tag),
            function_id=function_id,
        )

        webhook_url = self._create_webhook_trigger(
            workspace_id=workspace_id, pipeline_id=pipeline_id
        )

        self._set_github_webhook(
            webhook_url=webhook_url, github_url=github_url, github_token=github_token
        )

        self._create_trigger(
            workspace_id=workspace_id,
            pipeline_id=pipeline_id,
            webhook_url=webhook_url,
            code_connection_name=code_connection_name,
            github_branch=github_branch,
        )

        return pipeline_id

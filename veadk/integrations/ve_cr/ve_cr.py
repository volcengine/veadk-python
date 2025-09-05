from veadk.utils.volcengine_sign import ve_request
from veadk.utils.logger import get_logger
from veadk.consts import (
    DEFAULT_CR_INSTANCE_NAME,
    DEFAULT_CR_NAMESPACE_NAME,
    DEFAULT_CR_REPO_NAME,
)
import time

logger = get_logger(__name__)


class VeCR:
    def __init__(self, access_key: str, secret_key: str, region: str = "cn-beijing"):
        self.ak = access_key
        self.sk = secret_key
        self.region = region
        assert region in ["cn-beijing", "cn-guangzhou", "cn-shanghai"]
        self.version = "2022-05-12"

    def _create_instance(self, instance_name: str = DEFAULT_CR_INSTANCE_NAME):
        response = ve_request(
            request_body={
                "Name": instance_name,
                "ResourceTags": [
                    {"Key": "provider", "Value": "veadk"},
                ],
            },
            action="CreateRegistry",
            ak=self.ak,
            sk=self.sk,
            service="cr",
            version=self.version,
            region=self.region,
            host=f"cr.{self.region}.volcengineapi.com",
        )
        logger.info(f"create cr instance {instance_name}: {response}")
        return response

    def _check_instance(self, instance_name: str = DEFAULT_CR_INSTANCE_NAME):
        response = ve_request(
            request_body={
                "Filter": {
                    "Names": [instance_name],
                }
            },
            action="ListRegistries",
            ak=self.ak,
            sk=self.sk,
            service="vecr",
            version=self.version,
            region=self.region,
            host=f"cr.{self.region}.volcengineapi.com",
        )

        try:
            return response["Result"]["Items"][0]["Status"]
        except Exception as e:
            raise ValueError(f"cr instance {instance_name} not found: {e}")

    def _create_namespace(self, namespace_name: str = DEFAULT_CR_NAMESPACE_NAME):
        pass

    def _create_repo(self, repo_name: str = DEFAULT_CR_REPO_NAME):
        pass


if __name__ == "__main__":
    cr = VeCR("", "")
    cr._create_instance()

    while True:
        status = cr._check_instance()
        if status["Phase"] == "Running":
            print("cr instance running")
            break
        else:
            print("cr instance not running")
            time.sleep(30)

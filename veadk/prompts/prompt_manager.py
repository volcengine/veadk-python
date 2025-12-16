from abc import ABC, abstractmethod
from typing import override

from google.adk.agents.readonly_context import ReadonlyContext

from veadk.prompts.agent_default_prompt import DEFAULT_INSTRUCTION
from veadk.utils.logger import get_logger

logger = get_logger(__name__)


class BasePromptManager(ABC):
    def __init__(self) -> None: ...

    @abstractmethod
    def get_prompt(self, context: ReadonlyContext, **kwargs) -> str: ...


class CozeloopPromptManager(BasePromptManager):
    def __init__(
        self,
        cozeloop_workspace_id: str,
        cozeloop_token: str,
        prompt_key: str,
        version: str = "",
        label: str = "",
    ) -> None:
        import cozeloop

        self.cozeloop_workspace_id = cozeloop_workspace_id
        self.cozeloop_token = cozeloop_token

        self.prompt_key = prompt_key
        self.version = version
        self.label = label

        self.client = cozeloop.new_client(
            workspace_id=self.cozeloop_workspace_id,
            api_token=self.cozeloop_token,
        )

        super().__init__()

    @override
    def get_prompt(self, context: ReadonlyContext, **kwargs) -> str:
        logger.info(f"Get prompt for agent {context.agent_name} from CozeLoop.")

        prompt = self.client.get_prompt(
            prompt_key=self.prompt_key,
            version=self.version,
            label=self.label,
        )
        if (
            prompt
            and prompt.prompt_template
            and prompt.prompt_template.messages
            and prompt.prompt_template.messages[0].content
        ):
            return prompt.prompt_template.messages[0].content

        logger.warning(
            f"Prompt {self.prompt_key} version {self.version} label {self.label} not found, get prompt result is {prompt}"
            f"return default instruction"
        )
        return DEFAULT_INSTRUCTION

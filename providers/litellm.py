import os

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_litellm import ChatLiteLLM

from .models import LiteLLMModel

load_dotenv()


class LiteLLM:
    def __init__(
        self,
        model: LiteLLMModel = LiteLLMModel.CLAUDE_SONNET_4_6,
        temperature: float = 0.6,
    ):
        api_key = os.environ.get("LITELLM_API_KEY")
        api_base = os.environ.get("LITELLM_API_BASE")
        if not api_key:
            raise ValueError("LITELLM_API_KEY environment variable is not set")
        if not api_base:
            raise ValueError("LITELLM_API_BASE environment variable is not set")

        self._llm = ChatLiteLLM(
            api_key=api_key,
            api_base=api_base,
            temperature=temperature,
            model=model,
        )

    def chat(self, message: str, system_message: str | None = None):
        return self._llm.invoke(self._build_message(message, system_message))

    def chat_stream(self, message: str, system_message: str | None = None):
        for chunk in self._llm.stream(self._build_message(message, system_message)):
            print(chunk.text, end="", flush=True)

    def _build_message(
        self, human_msg: str, system_msg: str | None
    ) -> list[HumanMessage | SystemMessage]:
        human_message = HumanMessage(content=human_msg)

        if system_msg:
            system_message = SystemMessage(content=system_msg)
            return [system_message, human_message]

        return [human_message]

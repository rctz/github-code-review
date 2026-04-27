import logging

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openrouter import ChatOpenRouter
from pydantic import SecretStr
from tenacity import before_sleep_log, retry, stop_after_attempt, wait_exponential

from config.settings import settings
from providers.base import LLMProvider

logger = logging.getLogger(__name__)


class OpenRouterProvider(LLMProvider):
    def __init__(self, model: str = "minimax/minimax-m2.5", temperature: float = 0.6):
        if not settings.openrouter_api_key:
            raise ValueError("OPENROUTER_API_KEY is not configured")
        self._llm = ChatOpenRouter(
            api_key=SecretStr(settings.openrouter_api_key),
            temperature=temperature,
            model=model,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def chat(self, message: str, system_message: str | None = None) -> str:
        msgs = _build_messages(message, system_message)
        response = self._llm.invoke(msgs)
        return str(response.content)

    def chat_stream(self, message: str, system_message: str | None = None) -> None:
        msgs = _build_messages(message, system_message)
        for chunk in self._llm.stream(msgs):
            print(chunk.text, end="", flush=True)


def _build_messages(human_msg: str, system_msg: str | None) -> list[HumanMessage | SystemMessage]:
    msgs: list[HumanMessage | SystemMessage] = []
    if system_msg:
        msgs.append(SystemMessage(content=system_msg))
    msgs.append(HumanMessage(content=human_msg))
    return msgs

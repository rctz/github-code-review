import logging
import threading
import time

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_litellm import ChatLiteLLM
from tenacity import before_sleep_log, retry, stop_after_attempt, wait_exponential

from config.settings import settings
from providers.base import LLMProvider
from providers.models import LiteLLMModel

logger = logging.getLogger(__name__)


class _RateLimiter:
    """Sliding-window rate limiter — allows N requests per period."""

    def __init__(self, max_requests: int, period_seconds: int) -> None:
        self._max = max_requests
        self._period = period_seconds
        self._timestamps: list[float] = []
        self._lock = threading.Lock()

    def acquire(self) -> None:
        while True:
            with self._lock:
                now = time.monotonic()
                self._timestamps = [t for t in self._timestamps if now - t < self._period]
                if len(self._timestamps) < self._max:
                    self._timestamps.append(now)
                    return
                sleep_time = self._period - (now - self._timestamps[0]) + 0.1
            # Sleep *outside* the lock so other threads aren't blocked
            logger.debug("Rate limit reached — sleeping %.1fs", sleep_time)
            time.sleep(sleep_time)


# Shared limiter across all provider instances
_rate_limiter = _RateLimiter(settings.llm_rate_limit, settings.llm_rate_period_seconds)
_semaphore = threading.Semaphore(settings.max_concurrent_llm_calls)


class LiteLLMProvider(LLMProvider):
    def __init__(self, model: LiteLLMModel = LiteLLMModel.CLAUDE_SONNET_4_6, temperature: float = 0.6):
        if not settings.litellm_api_key:
            raise ValueError("LITELLM_API_KEY is not configured")
        if not settings.litellm_api_base:
            raise ValueError("LITELLM_API_BASE is not configured")

        self._llm = ChatLiteLLM(
            api_key=settings.litellm_api_key,
            api_base=settings.litellm_api_base,
            temperature=temperature,
            model=model,
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(min=1, max=10),
        before_sleep=before_sleep_log(logger, logging.WARNING),
    )
    def chat(self, message: str, system_message: str | None = None) -> str:
        _rate_limiter.acquire()
        with _semaphore:
            msgs = self._build_messages(message, system_message)
            response = self._llm.invoke(msgs)
            return str(response.content)

    def chat_stream(self, message: str, system_message: str | None = None) -> None:
        _rate_limiter.acquire()
        msgs = self._build_messages(message, system_message)
        for chunk in self._llm.stream(msgs):
            print(chunk.text, end="", flush=True)

    @staticmethod
    def _build_messages(human_msg: str, system_msg: str | None) -> list[HumanMessage | SystemMessage]:
        human_message = HumanMessage(content=human_msg)
        if system_msg:
            return [SystemMessage(content=system_msg), human_message]
        return [human_message]

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """Abstract base class for all LLM providers."""

    @abstractmethod
    def chat(self, message: str, system_message: str | None = None) -> str:
        """Send a chat message and return the response content as a string."""

    @abstractmethod
    def chat_stream(self, message: str, system_message: str | None = None) -> None:
        """Stream a chat response to stdout."""

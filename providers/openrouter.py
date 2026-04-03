import os

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openrouter import ChatOpenRouter
from pydantic import SecretStr

load_dotenv()


class OpenRouter:
    def __init__(self, model: str = "minimax/minimax-m2.5", temperature: float = 0.6):
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise ValueError("OPENROUTER_API_KEY environment variable is not set")
        self._llm = ChatOpenRouter(
            api_key=SecretStr(api_key),
            temperature=temperature,
            model=model,
        )

    def chat(self, message: list[HumanMessage | SystemMessage]):
        return self._llm.invoke(message)

    def chat_stream(self, message: list[HumanMessage | SystemMessage]):
        for chunk in self._llm.stream(message):
            print(chunk.text, end="", flush=True)

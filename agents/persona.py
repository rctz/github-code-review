from dotenv import load_dotenv

from providers.litellm import LiteLLM
from providers.models import LiteLLMModel

load_dotenv()


def _get_llm() -> LiteLLM:
    return LiteLLM(model=LiteLLMModel.GPT_5_4, temperature=1.0)


def run_persona(repo_name: str) -> str:
    """Generate a reviewer system prompt based on the repository name.

    Returns:
        A concise system prompt string for the code reviewer.
    """
    llm = _get_llm()

    prompt = f"""You are an expert software architect.
Given the repository name "{repo_name}", generate a concise system prompt
that will guide a code reviewer. The prompt should specify:
1. The likely tech stack and conventions for this repo
2. What to focus on during review (security, performance, style, etc.)
3. The expected output format for each file review

Keep the system prompt under 200 words. Write in English."""

    response = llm.chat(prompt)
    return str(response.content)

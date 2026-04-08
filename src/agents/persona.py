import logging

from prompts.persona import PERSONA_SYSTEM_PROMPT
from providers.factory import LLMFactory
from providers.models import LiteLLMModel

logger = logging.getLogger(__name__)


def run_persona(repo_name: str) -> str:
    """Generate a reviewer system prompt based on the repository name.

    Args:
        repo_name: The repository name (e.g., "owner/repo").

    Returns:
        A concise system prompt string for the code reviewer.
    """
    llm = LLMFactory.create(model=LiteLLMModel.GPT_5_4, temperature=1.0)
    prompt = PERSONA_SYSTEM_PROMPT.format(repo_name=repo_name)
    logger.info("Generating persona for repo: %s", repo_name)
    return llm.chat(prompt)

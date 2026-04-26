import logging

from prompts.persona import PERSONA_SYSTEM_PROMPT
from providers.factory import LLMFactory
from providers.models import LiteLLMModel
from services.github import GitHubService

logger = logging.getLogger(__name__)

_CONTEXT_FILES = ["README.md", "CLAUDE.md"]


def _fetch_project_context(owner: str, repo_name: str, github_token: str) -> str:
    github = GitHubService(token=github_token)
    full_repo = f"{owner}/{repo_name}"
    parts = []
    for filename in _CONTEXT_FILES:
        content = github.fetch_file_content(full_repo, filename)
        if not content.startswith("[Error"):
            parts.append(f"### {filename}\n{content}")
    return "\n\n".join(parts)


def run_persona(repo_name: str, owner: str, github_token: str) -> str:
    """Generate a reviewer system prompt from the project's README and CLAUDE.md.

    Args:
        repo_name: The repository name (without owner).
        owner: The repository owner.
        github_token: GitHub token for fetching project files.

    Returns:
        A domain-specific system prompt string for the code reviewer.
    """
    project_context = _fetch_project_context(owner, repo_name, github_token)
    if not project_context:
        logger.warning("No project context found for %s/%s", owner, repo_name)
        project_context = "(No README.md or CLAUDE.md found — use repo name for context.)"

    llm = LLMFactory.create(model=LiteLLMModel.CLAUDE_SONNET_4_6, temperature=1.0)
    prompt = PERSONA_SYSTEM_PROMPT.format(repo_name=repo_name, project_context=project_context)
    logger.info("Generating persona for repo: %s/%s", owner, repo_name)
    return llm.chat(prompt)

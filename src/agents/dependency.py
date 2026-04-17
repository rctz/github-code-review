import logging

from prompts.dependency import DEPENDENCY_CONTEXT_TEMPLATE, NO_DEPENDENCIES_MESSAGE
from services.dependency_resolver import get_resolver
from services.github import GitHubService

logger = logging.getLogger(__name__)

LIMIT_IMPORT_CHECK = 7
_CONTENT_TRUNCATE = 500


def run_dependency(
    filename: str,
    diff: str,
    repo_name: str,
    head_sha: str,
    github_service: GitHubService,
) -> str:
    """Resolve and fetch dependency context for a single file.

    Args:
        filename: The file being reviewed (e.g. "src/nodes/review_node.cpp").
        diff: The unified diff string.
        repo_name: Full repo name (e.g. "owner/repo").
        head_sha: Commit SHA to fetch files at.
        github_service: GitHubService instance for API calls.

    Returns:
        A dependency context string for the review prompt.
    """
    resolver = get_resolver(filename)
    if not resolver:
        return NO_DEPENDENCIES_MESSAGE

    candidates = resolver.guess_paths(filename, diff, repo_name)
    if not candidates:
        return NO_DEPENDENCIES_MESSAGE

    parts: list[str] = []
    for path in candidates[:LIMIT_IMPORT_CHECK]:
        content = github_service.fetch_file_content(repo_name, path, ref=head_sha)
        if content.startswith("[Error"):
            logger.debug("Dependency not found: %s", path)
            continue
        parts.append(DEPENDENCY_CONTEXT_TEMPLATE.format(path=path, content=content[:_CONTENT_TRUNCATE]))

    if not parts:
        return NO_DEPENDENCIES_MESSAGE

    return "\n\n".join(parts)

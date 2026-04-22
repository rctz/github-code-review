import logging
from pathlib import PurePosixPath

from prompts.dependency import DEPENDENCY_CONTEXT_TEMPLATE, NO_DEPENDENCIES_MESSAGE
from services.dependency import DependencyResolver, create_python_resolver, get_resolver
from services.dependency.registry import RepoContext
from services.github import GitHubService

logger = logging.getLogger(__name__)

LIMIT_IMPORT_CHECK = 10
_CONTENT_TRUNCATE = 500


def _build_resolver(
    filename: str,
    repo_name: str,
    head_sha: str,
    github_service: GitHubService,
) -> DependencyResolver | None:
    resolver = get_resolver(filename)
    if resolver is None:
        return None

    if PurePosixPath(filename).suffix != ".py":
        return resolver

    # Detect ROS 2 workspace by checking for package.xml in the repo root.
    pkg_xml = github_service.fetch_file_content(repo_name, "package.xml", ref=head_sha)
    is_ros2 = not pkg_xml.startswith("[Error")
    context = RepoContext(repo_path=PurePosixPath(repo_name), is_ros2=is_ros2)
    return create_python_resolver(context)


def run_dependency(
    filename: str,
    diff: str,
    repo_name: str,
    head_sha: str,
    github_service: GitHubService,
) -> str:
    resolver = _build_resolver(filename, repo_name, head_sha, github_service)
    if not resolver:
        return NO_DEPENDENCIES_MESSAGE

    candidates = resolver.guess_paths(filename, diff, repo_name)

    if not candidates:
        return NO_DEPENDENCIES_MESSAGE

    parts: list[str] = []
    found = 0
    for path in candidates:
        if found >= LIMIT_IMPORT_CHECK:
            break
        content = github_service.fetch_file_content(repo_name, path, ref=head_sha)

        if content.startswith("[Error"):
            logger.debug("Dependency not found: %s", path)
            continue
        found += 1
        parts.append(DEPENDENCY_CONTEXT_TEMPLATE.format(path=path, content=content[:_CONTENT_TRUNCATE]))

    if not parts:
        return NO_DEPENDENCIES_MESSAGE

    return "\n\n".join(parts)

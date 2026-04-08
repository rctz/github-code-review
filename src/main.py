import json
import logging
import sys
from pathlib import Path

from config.settings import settings
from graph.builder import build_compiled_graph
from services.github import GitHubService
from state.models import PRReviewState

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

# Default mock input path relative to project root
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_MOCK_PATH = str(_PROJECT_ROOT / "tests" / "mock_input.json")


def run_review_from_file(mock_path: str) -> PRReviewState:
    """Run PR review from a mock JSON file.

    Args:
        mock_path: Path to a JSON file matching the GitHub webhook PR payload schema.

    Returns:
        The final PRReviewState after graph execution.
    """
    github_service = GitHubService()

    with open(mock_path, encoding="utf-8") as f:
        mock = json.load(f)

    pr = mock["pull_request"]
    repo = mock["repository"]
    raw_diff = github_service.fetch_diff(repo["name"], repo["owner"]["login"], pr["number"])

    initial_state = PRReviewState(
        pr_id=str(pr["number"]),
        repo_name=f"{repo['owner']['login']}/{repo['name']}",
        pr_files=raw_diff,
    )

    graph = build_compiled_graph()
    result = graph.invoke(initial_state.model_dump())
    return PRReviewState.model_validate(result)


def main() -> None:
    """CLI entry point for the PR review bot."""
    mock_path = sys.argv[1] if len(sys.argv) > 1 else _DEFAULT_MOCK_PATH

    logger.info("Running PR Review from %s", mock_path)
    result = run_review_from_file(mock_path)

    print("=" * 60)
    print(result.final_comment)

    output_path = _PROJECT_ROOT / "tests" / "review_output.md"
    output_path.write_text(result.final_comment, encoding="utf-8")
    logger.info("Review saved to %s", output_path.resolve())


if __name__ == "__main__":
    main()

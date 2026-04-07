import json
from pathlib import Path
from typing import cast

from graph import app
from state import PRReviewState
from tools import github


def _save_review_markdown(result: PRReviewState) -> None:
    """Save the final_comment (already GitHub-ready markdown) to a file."""
    output_path = Path("tests/review_output.md")
    output_path.write_text(result["final_comment"], encoding="utf-8")
    print(f"\nReview saved to {output_path.resolve()}")


with open(
    "/Users/rctz/rctz/langgraph-test/tests/mock_input.json", "r", encoding="utf-8"
) as file:
    # Parse the JSON file into a Python dictionary or list
    mock = json.load(file)
pr = mock["pull_request"]
repo = mock["repository"]
raw_diff = github.fetch_diff(repo["name"], repo["owner"]["login"], pr["number"])


if __name__ == "__main__":
    # Simulate a webhook payload: a PR with two changed files
    initial_state = PRReviewState(
        pr_id="42",
        repo_name="my-org/my-repo",
        pr_files=raw_diff,
        system_prompt="",
        file_reviews=[],
        final_comment="",
    )

    print("Running PR Review Graph...\n")
    result = cast(PRReviewState, app.invoke(initial_state))

    print("=" * 60)
    print(result["final_comment"])

    # Save review results as markdown
    _save_review_markdown(result)

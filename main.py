import json

from graph import app
from state import PRReviewState
from tools import  github

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
    result = app.invoke(initial_state)

    print("=" * 60)
    print(result["final_comment"])

from graph import app
from state import PRReviewState

if __name__ == "__main__":
    # Simulate a webhook payload: a PR with two changed files
    initial_state = PRReviewState(
        pr_id="42",
        repo_name="my-org/my-repo",
        pr_files=[
            {
                "filename": "src/auth.py",
                "diff": (
                    "+def login(username, password):\n"
                    "+    query = f\"SELECT * FROM users WHERE name='{username}'\"\n"
                    "+    return db.execute(query)"
                ),
            },
            {
                "filename": "src/utils.py",
                "diff": ("+def format_date(ts):\n+    return str(ts)\n"),
            },
        ],
        system_prompt="",
        file_reviews=[],
        final_comment="",
    )

    print("Running PR Review Graph...\n")
    result = app.invoke(initial_state)

    print("=" * 60)
    print(result["final_comment"])

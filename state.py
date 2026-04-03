import operator
from typing import Annotated, TypedDict


class PRReviewState(TypedDict):
    """Main state for the entire PR review process."""

    pr_id: str
    repo_name: str
    pr_files: list[dict]  # [{"filename": "...", "diff": "..."}]
    system_prompt: str
    # Reducer: appends individual file reviews (fan-in result)
    file_reviews: Annotated[list[str], operator.add]
    final_comment: str


class SingleFileState(TypedDict):
    """Sub-state passed to each parallel file review node."""

    pr_id: str
    repo_name: str
    filename: str
    diff: str
    system_prompt: str
    dependency_context: str
    file_reviews: Annotated[list[str], operator.add]


class SingleFileOutput(TypedDict):
    """Only these keys are written back to the parent PRReviewState."""

    file_reviews: Annotated[list[str], operator.add]

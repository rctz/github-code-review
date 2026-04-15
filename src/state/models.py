import operator
from typing import Annotated

from pydantic import BaseModel, ConfigDict


class PRReviewState(BaseModel):
    """Main state for the entire PR review process."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    pr_id: str
    repo_name: str
    pr_files: list[dict]
    system_prompt: str = ""
    file_reviews: Annotated[list[str], operator.add] = []
    final_comment: str = ""
    error: str = ""


class SingleFileState(BaseModel):
    """Sub-state passed to each parallel file review node."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    pr_id: str
    repo_name: str
    filename: str
    diff: str = ""
    system_prompt: str = ""
    dependency_context: str = ""
    file_reviews: Annotated[list[str], operator.add] = []


class SingleFileOutput(BaseModel):
    """Keys written back to the parent PRReviewState after fan-in."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    file_reviews: Annotated[list[str], operator.add] = []

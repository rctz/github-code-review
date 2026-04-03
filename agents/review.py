import json
import logging
from typing import Literal

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError, field_validator

from providers.litellm import LiteLLM
from providers.models import LiteLLMModel

load_dotenv()

logger = logging.getLogger(__name__)


class ReviewItem(BaseModel):
    title: str
    detail: str
    suggestion_for_change: str
    critical_rate: Literal["High", "Mid", "Low"]

    @field_validator("title")
    @classmethod
    def title_max_15_words(cls, v: str) -> str:
        if len(v.split()) > 15:
            raise ValueError("title must not exceed 15 words")
        return v


class FileReviewOutput(BaseModel):
    filename: str
    reviews: list[ReviewItem]


def _get_llm() -> LiteLLM:
    return LiteLLM(model=LiteLLMModel.GPT_5_4, temperature=1.0)


def _parse_response(content: str, filename: str) -> FileReviewOutput:
    """Parse and validate the LLM JSON response into FileReviewOutput."""
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

    data = json.loads(text)
    if "filename" not in data:
        data["filename"] = filename
    return FileReviewOutput.model_validate(data)


def run_review(
    filename: str,
    diff: str,
    system_prompt: str,
    dependency_context: str,
) -> FileReviewOutput:
    """Review a single file diff and return structured review items.

    Args:
        filename: Path of the file being reviewed.
        diff: The unified diff string for the file.
        system_prompt: Reviewer persona/instructions from the persona agent.
        dependency_context: Relevant dependency content from the dependency agent.

    Returns:
        A validated FileReviewOutput with one ReviewItem per issue found.
    """
    llm = _get_llm()

    user_prompt = f"""Review the following code diff for `{filename}`.

## Dependency Context
{dependency_context}

## Diff
```diff
{diff}
```

Analyze the diff and return a JSON object with this exact structure:
{{
  "filename": "{filename}",
  "reviews": [
    {{
      "title": "<concise issue title, max 15 words>",
      "detail": "<detailed explanation of the issue>",
      "suggestion_for_change": "<concrete suggestion to fix or improve the code>",
      "critical_rate": "<High | Mid | Low>"
    }}
  ]
}}

Rules:
- Each review item must cover one specific issue (bugs, security, performance, or style).
- Write everything in English.
- Output only the JSON object — no markdown fences, no extra text."""

    response = llm.chat(message=user_prompt, system_message=system_prompt)

    try:
        return _parse_response(str(response.content), filename)
    except (json.JSONDecodeError, ValidationError, KeyError) as exc:
        logger.warning("Failed to parse review response for %s: %s", filename, exc)
        return FileReviewOutput(
            filename=filename,
            reviews=[
                ReviewItem(
                    title="Review output parse error",
                    detail=f"The model returned an unexpected format. Raw output: {response.content[:500]}",
                    suggestion_for_change="Re-run the review or inspect the model output manually.",
                    critical_rate="Low",
                )
            ],
        )

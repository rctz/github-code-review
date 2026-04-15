import json
import logging
from typing import Literal

from pydantic import BaseModel, ValidationError, field_validator

from prompts.review import REVIEW_PROMPT_TEMPLATE
from providers.factory import LLMFactory
from providers.models import LiteLLMModel

logger = logging.getLogger(__name__)


class ReviewItem(BaseModel):
    title: str
    detail: str
    existing_code_to_replace: str
    suggestion_for_change: str
    exact_code_replacement: str
    critical_rate: Literal["Critical", "High", "Mid"]

    @field_validator("title")
    @classmethod
    def title_max_15_words(cls, v: str) -> str:
        if len(v.split()) > 15:
            raise ValueError("title must not exceed 15 words")
        return v


_SEVERITY_EMOJI = {"Critical": "🔴", "High": "🟠", "Mid": "🟡"}


class FileReviewOutput(BaseModel):
    filename: str
    reviews: list[ReviewItem]

    def to_markdown(self) -> str:
        """Render as GitHub-ready markdown with suggestion blocks."""
        lines: list[str] = [f"### 📄 `{self.filename}`", ""]
        for item in self.reviews:
            emoji = _SEVERITY_EMOJI.get(item.critical_rate, "⚪")
            lines.append(f"#### {emoji} {item.critical_rate} — {item.title}")
            lines.append("")
            lines.append(item.detail)
            lines.append("")
            lines.append(f"**Suggestion:** {item.suggestion_for_change}")
            lines.append("")
            lines.append("```suggestion")
            lines.append(item.exact_code_replacement)
            lines.append("```")
            lines.append("")
            lines.append("---")
            lines.append("")
        return "\n".join(lines)


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
    """Review a single file diff and return structured review items."""
    llm = LLMFactory.create(model=LiteLLMModel.GPT_5_4, temperature=1.0)

    user_prompt = REVIEW_PROMPT_TEMPLATE.format(
        filename=filename,
        dependency_context=dependency_context,
        diff=diff,
    )

    response = llm.chat(message=user_prompt, system_message=system_prompt)

    try:
        return _parse_response(response, filename)
    except (json.JSONDecodeError, ValidationError, KeyError) as exc:
        logger.warning("Failed to parse review response for %s: %s", filename, exc)
        return FileReviewOutput(
            filename=filename,
            reviews=[
                ReviewItem(
                    title="Review output parse error",
                    detail=f"The model returned an unexpected format. Raw: {response[:500]}",
                    existing_code_to_replace="",
                    suggestion_for_change="Re-run the review or inspect the model output manually.",
                    exact_code_replacement="",
                    critical_rate="Mid",
                )
            ],
        )

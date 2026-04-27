import json
import logging

from pydantic import BaseModel

from prompts.synthesis import SYNTHESIS_PROMPT_TEMPLATE
from providers.factory import LLMFactory
from providers.models import LiteLLMModel

logger = logging.getLogger(__name__)

_MAX_DIFF_CHARS = 12_000
_MAX_REVIEWS_CHARS = 6_000


class SynthesisIssue(BaseModel):
    title: str
    detail: str
    files_involved: list[str]
    critical_rate: str


class SynthesisOutput(BaseModel):
    issues: list[SynthesisIssue]

    def to_markdown(self) -> str:
        if not self.issues:
            return ""
        _emoji = {"Critical": "🔴", "High": "🟠"}
        lines = ["### 🔍 Cross-File Issues", ""]
        for issue in self.issues:
            emoji = _emoji.get(issue.critical_rate, "🟠")
            files = ", ".join(f"`{f}`" for f in issue.files_involved)
            lines.append(f"#### {emoji} {issue.critical_rate} — {issue.title}")
            lines.append(f"*Files: {files}*")
            lines.append("")
            lines.append(issue.detail)
            lines.append("")
            lines.append("---")
            lines.append("")
        return "\n".join(lines)


def _build_all_diffs(pr_files: list[dict]) -> str:
    parts = []
    total = 0
    for f in pr_files:
        diff = f.get("diff") or ""
        if not diff:
            continue
        header = f"### {f['filename']}\n```diff\n{diff}\n```\n"
        if total + len(header) > _MAX_DIFF_CHARS:
            parts.append(f"### {f['filename']}\n[diff truncated — too large]\n")
        else:
            parts.append(header)
            total += len(header)
    return "\n".join(parts)


def run_synthesis(
    pr_files: list[dict],
    file_reviews: list[str],
    pr_title: str,
    pr_body: str,
    system_prompt: str,
) -> SynthesisOutput:
    """Cross-file review: find issues invisible to per-file reviewers."""
    all_diffs = _build_all_diffs(pr_files)
    reviews_text = "\n\n".join(file_reviews)[:_MAX_REVIEWS_CHARS]

    prompt = SYNTHESIS_PROMPT_TEMPLATE.format(
        pr_title=pr_title or "(no title)",
        pr_body=pr_body or "(no description)",
        system_prompt=system_prompt or "",
        all_diffs=all_diffs,
        file_reviews=reviews_text or "(none)",
    )

    llm = LLMFactory.create(model=LiteLLMModel.CLAUDE_SONNET_4_6, temperature=1.0)
    response = llm.chat(prompt)

    try:
        text = response.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
        data = json.loads(text)
        return SynthesisOutput.model_validate(data)
    except Exception as exc:
        logger.warning("Failed to parse synthesis response: %s", exc)
        return SynthesisOutput(issues=[])

import logging
import re

from agents.review import FileReviewOutput, ReviewItem
from services.github import GitHubService, find_line_in_file
from state.models import PRReviewState

logger = logging.getLogger(__name__)

_SEVERITY_EMOJI = {"Critical": "🔴", "High": "🟠", "Mid": "🟡"}

_HUNK_HEADER_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def _parse_diff_line_ranges(diff: str) -> list[tuple[int, int]]:
    """Return list of (start, end) line ranges (1-based, inclusive) for the RIGHT side of a diff.

    These are the only lines GitHub's Reviews API accepts as inline comment targets.
    """
    ranges: list[tuple[int, int]] = []
    for line in diff.splitlines():
        m = _HUNK_HEADER_RE.match(line)
        if m:
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            if count > 0:
                ranges.append((start, start + count - 1))
    return ranges


def _line_in_diff(line: int, ranges: list[tuple[int, int]]) -> bool:
    """Return True if ``line`` falls within any hunk range."""
    return any(start <= line <= end for start, end in ranges)


def _strip_diff_markers(snippet: str) -> str:
    """Remove leading +/- diff markers from each line of a snippet."""
    cleaned = []
    for line in snippet.splitlines():
        if line.startswith(("+", "-")):
            cleaned.append(line[1:])
        else:
            cleaned.append(line)
    return "\n".join(cleaned)


def _build_review_body(item: ReviewItem) -> str:
    """Build the markdown body for a single inline review comment."""
    emoji = _SEVERITY_EMOJI.get(item.critical_rate, "⚪")

    parts = [
        f"**{emoji} {item.critical_rate} — {item.title}**",
        "",
        item.detail,
        "",
        f"**Suggestion:** {item.suggestion_for_change}",
        "",
        "```suggestion",
        item.exact_code_replacement,
        "```",
    ]
    return "\n".join(parts)


def post_review_node(state: PRReviewState) -> dict:
    """LangGraph node: post inline review comments as a single batched review.

    For each review item:
    1. Fetch the file content at the PR HEAD commit
    2. Find the exact line number by matching ``existing_code_to_replace``
    3. Collect into a batch

    Then posts all inline comments via a single Reviews API call to avoid
    GitHub's secondary rate limit. Falls back to a general PR comment for
    items where line resolution fails.
    """
    try:
        github_service = GitHubService(token=state.github_token or None)
        full_repo = f"{state.owner}/{state.repo_name}"
        pr_number = int(state.pr_id)
        head_sha = state.head_sha

        if not head_sha:
            logger.warning("No head_sha available — posting as general comments")
            for raw in state.file_reviews:
                try:
                    review = FileReviewOutput.model_validate_json(raw)
                    github_service.post_pr_comment(full_repo, pr_number, review.to_markdown())
                except Exception:
                    github_service.post_pr_comment(full_repo, pr_number, raw)
            return {}

        # -- Phase 1: collect all comments and fallbacks --------------------
        inline_comments: list[dict] = []
        fallback_bodies: list[str] = []
        file_content_cache: dict[str, str] = {}

        # Build a map of filename → valid diff line ranges for hunk validation
        diff_ranges_cache: dict[str, list[tuple[int, int]]] = {}
        for pr_file in state.pr_files:
            fname = pr_file.get("filename", "")
            raw_diff = pr_file.get("diff") or ""
            if fname and raw_diff:
                diff_ranges_cache[fname] = _parse_diff_line_ranges(raw_diff)

        for raw in state.file_reviews:
            try:
                review = FileReviewOutput.model_validate_json(raw)
            except Exception:
                fallback_bodies.append(raw)
                continue

            # Fetch file content once per file
            if review.filename not in file_content_cache:
                content = github_service.fetch_file_content(full_repo, review.filename, ref=head_sha)
                file_content_cache[review.filename] = content
            file_content = file_content_cache[review.filename]

            # Guard: treat error sentinel strings from fetch_file_content as missing
            file_content_valid = bool(file_content) and not file_content.startswith("[Error")

            if not file_content_valid:
                logger.warning(
                    "[inline] %s — file content unavailable (%s), all items → fallback",
                    review.filename,
                    file_content[:60] if file_content else "empty",
                )

            diff_ranges = diff_ranges_cache.get(review.filename, [])
            if not diff_ranges:
                logger.warning(
                    "[inline] %s — no diff hunk ranges found in pr_files, hunk check skipped",
                    review.filename,
                )

            for item in review.reviews:
                body = _build_review_body(item)

                if file_content_valid and item.existing_code_to_replace.strip():
                    # Strip +/- diff markers the LLM may have included
                    clean_snippet = _strip_diff_markers(item.existing_code_to_replace)
                    line_range = find_line_in_file(file_content, clean_snippet)

                    if line_range:
                        start_line, end_line = line_range
                        # GitHub only accepts lines present in the diff hunk
                        if diff_ranges and not _line_in_diff(end_line, diff_ranges):
                            logger.warning(
                                "[inline] %s — resolved line %d not in diff hunks %s → fallback | snippet: %r",
                                review.filename,
                                end_line,
                                diff_ranges,
                                clean_snippet[:120],
                            )
                        else:
                            comment: dict = {
                                "path": review.filename,
                                "line": end_line,
                                "side": "RIGHT",
                                "body": body,
                            }
                            if start_line != end_line:
                                comment["start_line"] = start_line
                                comment["start_side"] = "RIGHT"
                            inline_comments.append(comment)
                            logger.info(
                                "[inline] %s:%d-%d queued as inline comment ✓",
                                review.filename,
                                start_line,
                                end_line,
                            )
                            continue
                    else:
                        logger.warning(
                            "[inline] %s — find_line_in_file returned None → fallback | snippet: %r",
                            review.filename,
                            clean_snippet[:120],
                        )
                elif not item.existing_code_to_replace.strip():
                    logger.warning(
                        "[inline] %s — existing_code_to_replace is empty → fallback | title: %s",
                        review.filename,
                        item.title,
                    )

                # Could not resolve line or not in diff — queue as fallback
                fallback_bodies.append(f"### 📄 `{review.filename}`\n\n{body}")

        # -- Phase 2: batch-post inline comments as one review ---------------
        inline_posted = 0
        if inline_comments:
            summary = f"## PR Review — `{state.repo_name}` #{state.pr_id}\n\n"
            summary += f"Found {len(inline_comments)} issue(s) across reviewed files.\n\n"
            summary += "---\n*Generated by LangGraph PR Review Bot*"

            success = github_service.create_review_with_comments(
                repo_name=full_repo,
                pr_number=pr_number,
                commit_id=head_sha,
                comments=inline_comments,
                body=summary,
                event="COMMENT",
            )
            if success:
                inline_posted = len(inline_comments)
            else:
                # Review API failed — dump everything as general comments
                logger.warning(
                    "Batch review failed for %s#%d — falling back to individual comments",
                    full_repo,
                    pr_number,
                )
                for c in inline_comments:
                    fallback_bodies.append(f"### 📄 `{c['path']}`\n\n{c['body']}")

        # -- Phase 3: post fallback comments ---------------------------------
        fallback_posted = 0
        for fb_body in fallback_bodies:
            success = github_service.post_pr_comment(full_repo, pr_number, fb_body)
            if success:
                fallback_posted += 1

        logger.info(
            "Posted %d inline + %d fallback comments for %s#%s",
            inline_posted,
            fallback_posted,
            full_repo,
            state.pr_id,
        )
        return {}
    except Exception as exc:
        logger.error(
            "Review post failed for %s/%s#%s: %s",
            state.owner,
            state.repo_name,
            state.pr_id,
            exc,
        )
        return {"error": str(exc)}

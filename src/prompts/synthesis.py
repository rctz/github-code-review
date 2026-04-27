SYNTHESIS_PROMPT_TEMPLATE = """You are a senior engineer performing a holistic cross-file review of a pull request.

## PR Context
Title: {pr_title}
Description:
{pr_body}

## System Context
{system_prompt}

## All Changed Files and Their Diffs
{all_diffs}

## Per-File Review Findings (already completed)
{file_reviews}

Your task is to find issues that NO single-file reviewer could see — problems that only emerge from looking at ALL the changes together. Focus on:

1. **Interface / implementation mismatch**: A type, field, or contract changed in one file but not consistently updated across all callers or implementors in this diff.
2. **Missing data migration**: A rename of a persisted filename, database key, or wire-format field with no migration for existing data.
3. **Partial rename**: A rename applied to some files in this PR but not others, leaving the codebase in an inconsistent state.
4. **Cascade omissions**: A change that obviously requires a paired change in another file (e.g., adding a field to a struct but not updating serialization, adding a service method but not registering it).

Rules:
- Return a maximum of 3 issues.
- ONLY report issues that require seeing multiple files simultaneously — do NOT repeat issues already in the per-file findings above.
- If there are no cross-file issues, return an empty list.
- Each issue must name the specific files involved.
- Write everything in English.

Return a JSON object with this exact structure:
{{
  "issues": [
    {{
      "title": "<max 8 words>",
      "detail": "<2-3 sentences: what is wrong, which files, why it matters>",
      "files_involved": ["file1", "file2"],
      "critical_rate": "<Critical | High>"
    }}
  ]
}}

Output strictly the JSON object — no markdown fences, no extra text."""

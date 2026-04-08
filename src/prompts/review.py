REVIEW_PROMPT_TEMPLATE = """Review the following code diff for `{filename}`.

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
- Each review item must cover a DISTINCT issue -- no two items should address the same root cause.
- If multiple observations relate to the same problem, merge them into a single, comprehensive item.
- Before adding an item, ensure its topic does not overlap with any other item already listed.
- Write everything in English.
- Output only the JSON object -- no markdown fences, no extra text."""

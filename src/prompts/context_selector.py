CONTEXT_SELECTOR_PROMPT = """You are helping review a code diff by identifying which existing files in the repository would provide the most useful context for a thorough, accurate review.

File under review: {filename}

Diff:
{diff}

Repository files (same language, same package):
{file_list}

Select up to {max_files} files that are most relevant. Prioritise:
1. Files directly imported or referenced by name in the diff
2. Base classes, interfaces, or abstract types the changed code inherits or implements
3. Sibling modules in the same package that define types, methods, or constants called in the diff
4. Configuration or schema files referenced by the changed code

Return ONLY a JSON array of file paths. No explanation, no markdown, no extra text.
Example: ["src/foo/bar.py", "src/foo/baz.py"]
If no files are relevant, return an empty array: []"""

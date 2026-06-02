# LangGraph PR Review Bot

AI-powered GitHub PR reviewer using LangGraph Map-Reduce (fan-out/fan-in). Receives webhook payloads, reviews files in parallel, posts inline diff comments directly on the PR.

## Tech Stack
- **Python 3.12/3.13**, LangGraph, LangChain (`langchain-litellm`, `langchain-core`)
- **LLM:** LiteLLM proxy via `LLMFactory` (provider-agnostic)
- **State/Config:** Pydantic v2, `pydantic-settings` (loads `.env`)
- **Resilience:** `tenacity` (3 attempts, exponential backoff)
- **Package manager:** `uv` | **Linting:** Ruff

## Architecture Layers

| Layer | Path | Role |
|---|---|---|
| Config | `src/config/` | `pydantic-settings` — never call `os.getenv()` directly |
| Prompts | `src/prompts/` | All prompt templates — edit without touching code |
| State | `src/state/models.py` | `PRReviewState`, `SingleFileState`, `SingleFileOutput` |
| Providers | `src/providers/` | `LLMFactory.create(model, temperature)` → `LLMProvider` |
| Agents | `src/agents/` | Pure LLM logic — plain args in/out, no LangGraph |
| Nodes | `src/nodes/` | LangGraph state ↔ agent bridge — return `dict` |
| Graph | `src/graph/builder.py` | Orchestration, `Send` fan-out, all edges |
| Services | `src/services/` | `GitHubService`, `GitHubAppService`, dependency resolvers |
| Entrypoint | `entrypoints/webhook.py` | FastAPI webhook server, HMAC verification, dedup, backlog |

## Graph Workflow (in order)

```
START
  → persona_node          # run_persona(repo_name, owner, token) → system_prompt
  → fetch_sha_node        # fetch_pr_metadata() → head_sha, pr_title, pr_body
  → fetch_tree_node       # GitHub Trees API → repo_tree (fetched once, shared to all branches)
  → [_map_files_to_review]  # fan-out: Send per file (skips .md/.rst/.txt + trivial diffs)
      → review_single_file [subgraph per file, parallel]:
          → context_node  # Layer 1: resolve_imports() + Layer 2: run_context_selector() → dependency_context
          → review_node   # run_review() → appends JSON to file_reviews
  → synthesis_node        # cross-file analysis using all file_reviews → synthesis_reviews
  → aggregate_node        # joins file_reviews + synthesis_reviews → final_comment
  → post_review_node      # resolves line numbers, batch-posts inline comments to GitHub
END
```

### State Models (`src/state/models.py`)
```python
class PRReviewState:
    pr_id, owner, repo_name, pr_files, github_token, head_sha
    pr_title, pr_body           # fetched by fetch_sha_node, passed into synthesis
    system_prompt, repo_tree    # fetched once; repo_tree shared to all SingleFileStates
    file_reviews: Annotated[list[str], operator.add]  # reducer: parallel branches append
    synthesis_reviews: list[str]
    final_comment, error

class SingleFileState:
    pr_id, owner, repo_name, head_sha, github_token
    pr_title, pr_body, filename, diff, system_prompt
    repo_tree                   # passed from PRReviewState
    dependency_context          # filled by context_node
    file_reviews: Annotated[list[str], operator.add]
```

## Two-Layer Context Selection (`src/nodes/context_node.py`)

`context_node` builds `dependency_context` using a two-layer strategy with a combined budget of **12 files**:

**Layer 1 — Deterministic import resolution (`src/agents/import_resolver.py`):**
Parses `+` lines in the diff and resolves import/include statements to actual repo paths with no LLM call. Supports 8 language families via an extension-keyed dispatch table:

| Extension(s) | Resolver |
|---|---|
| `.py` | `_PythonExtractor` — relative/absolute imports, ROS2 interfaces |
| `.ts .tsx .js .jsx .mjs .cjs` | `_JSExtractor` — ESM, CJS `require()`, dynamic `import()`, `@/` alias |
| `.go` | `_GoExtractor` — single + block import syntax |
| `.java .kt .kts` | `_JavaExtractor` — package imports, wildcard imports |
| `.rs` | `_RustExtractor` — `use` paths, `mod` declarations |
| `.cpp .cc .cxx .c .hpp .h` | `_CppExtractor` — `#include "..."` (skips `<system>`) |
| `.php` | `_PHPExtractor` — `use` namespaces, `require`/`include` |
| `.rb` | `_RubyExtractor` — `require_relative`, `require` |

**Layer 2 — LLM semantic selection (`src/agents/context_selector.py`):**
Uses `claude-sonnet-4-6` (temperature=0) to pick up to `remaining_budget = 12 - len(layer1_paths)` additional semantically relevant files from the repo tree, excluding Layer 1 results. Tree candidates are pre-filtered to the same parent directory and file extension (up to 300 entries).

Content is truncated by file type before being formatted as `dependency_context`:
- Schema files (`.yaml`, `.json`, `.toml`, `.xml`): 2000 chars
- Source files (`.py`, `.ts`, `.go`, etc.): 4000 chars
- Interface files (`.msg`, `.srv`, `.proto`, etc.): unlimited
- Other: 1500 chars

## Synthesis Node

After all per-file reviews fan-in, `synthesis_node` calls `run_synthesis()` to find cross-file issues invisible to per-file reviewers (e.g., interface mismatches, state mutation patterns across modules). Outputs `SynthesisOutput` with `SynthesisIssue[]`.

## Inline Comment Flow (`src/nodes/post_review_node.py`)

Three-phase posting strategy for each `FileReviewOutput`:

**Phase 1 — Line resolution (per review item):**
1. Fetch real file content at `head_sha` via `fetch_file_content()` (cached per file).
2. Strip unified diff markers from `existing_code_to_replace`:
   - `+` added lines, `-` removed lines, ` ` (space) context lines — all get their prefix stripped.
3. Call `find_line_in_file()` with three-pass matching:
   - Pass 1: exact match (rstrip per line, indentation preserved)
   - Pass 2: indent-stripped match (removes common leading whitespace from both sides)
   - Pass 3: first-line anchor (uses first distinctive line ≥10 chars to locate position)
4. Validate resolved line falls within a diff hunk range (parsed from `@@ -a,b +c,d @@` headers). Lines outside hunks are rejected — GitHub's Reviews API only accepts lines present in the diff.
5. Comments that pass all checks are queued as inline; failures route to fallback.

**Phase 2 — Batch post:**
All inline comments posted as a single `POST /pulls/{pr}/reviews` call (`create_review_with_comments`) to avoid GitHub's secondary rate limit.

**Phase 3 — Fallbacks:**
Items that failed line resolution are posted as general PR comments via `post_pr_comment`.

### `find_line_in_file` (module-level in `src/services/github.py`)
```python
find_line_in_file(file_content: str, code_snippet: str) -> tuple[int, int] | None
```
Returns 1-based `(start_line, end_line)` or `None`. Never parse diff line numbers directly — always use this function against real file content fetched at `head_sha`.

## GitHub Services (`src/services/`)

| Service | File | Auth |
|---|---|---|
| `GitHubService` | `github.py` | PAT token or App installation token |
| `GitHubAppService` | `github_app.py` | GitHub App JWT (RS256) → installation access token |

**`GitHubService` methods:**

| Method | Returns | Notes |
|---|---|---|
| `fetch_diff(repo_name, owner, pr_id)` | `list[dict]` | Each dict: `filename`, `diff`, `raw` |
| `fetch_file_content(repo_name, file_path, ref)` | `str` | Returns `"[Error ...]"` string on failure — check before use |
| `fetch_pr_metadata(repo_name, owner, pr_id)` | `tuple[str,str,str]` | `(head_sha, title, body)` in one call |
| `fetch_pr_head_sha(repo_name, owner, pr_id)` | `str` | SHA only |
| `fetch_repo_tree(repo_name, tree_sha)` | `list[str]` | Flat list of blob paths via Trees API |
| `create_review_with_comments(repo_name, pr_number, commit_id, comments, body, event)` | `bool` | Primary inline posting — batch, avoids rate limit |
| `create_inline_comment(repo_name, pr_number, commit_id, path, line, body, side, ...)` | `bool` | Single comment — use only when batch is not applicable |
| `post_pr_comment(repo_name, pr_number, body)` | `bool` | General (non-diff) PR comment — fallback only |

All methods decorated with `@retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))`.

**`GitHubAppService`:**
`get_installation_access_token(installation_id: int) -> str` — exchanges GitHub App JWT for an installation token. Module-level `get_installation_access_token()` is a convenience wrapper.

## Webhook Server (`entrypoints/webhook.py`)

FastAPI app. Key behaviour:
- Triggers on `opened` and `reopened` PR actions only.
- Verifies `X-Hub-Signature-256` HMAC-SHA256 signature (configurable secret).
- Skips fork PRs unless `settings.review_forks = True`.
- Deduplicates: ignores a PR already being reviewed (keyed by `owner/repo#number`).
- Backlog cap: returns HTTP 429 if `>= settings.max_webhook_backlog` (default 8) reviews are queued.
- Executes reviews in a `ThreadPoolExecutor(max_workers=4)` — fire-and-forget from the request handler.
- `GET /health` → `{"status": "ok"}`.

## Review Output Format (`FileReviewOutput`)
```json
{
  "filename": "src/auth.py",
  "reviews": [{
    "title": "Max 7 words",
    "detail": "Clear explanation, max 3 sentences",
    "existing_code_to_replace": "exact 1-3 lines copied verbatim from the file (no +/- prefix)",
    "suggestion_for_change": "Brief actionable instruction",
    "exact_code_replacement": "replacement code for GitHub Suggestion API",
    "critical_rate": "Critical | High"
  }]
}
```

`existing_code_to_replace` must be a verbatim substring of the reviewed file — the backend uses it for line-number resolution via string matching. Never quote from dependency context files.

## Dependency Resolver System (`src/services/dependency/`)

Plugin-based strategy pattern — context-aware for different repo types. Used internally; `context_node` now uses `import_resolver` instead for the primary resolution path.

```
dependency/
  base.py          # DependencyResolver ABC, _STDLIB_MODULES
  registry.py      # RESOLVER_REGISTRY, RepoContext, analyze_repository(),
                   # create_python_resolver(), get_context_aware_registry(), get_resolver()
  resolvers/
    cpp.py         # CppResolver — parses #include lines
    python.py      # PythonResolver(plugins, attr_plugins) — extensible via plugins
  plugins/
    ros2.py        # Ros2InterfacePlugin, Ros2AmentWorkspacePlugin, Ros2AttrPlugin
```

## Key Implementation Rules

- **Agents:** plain args in, plain values/Pydantic out — never accept state objects
- **Nodes:** accept Pydantic state, return `dict` — never call LLM directly
- **Fan-out:** use `Send` API via conditional edge — never loop files inside a node
- **State reducers:** `Annotated[list[str], operator.add]` for keys aggregated across parallel branches
- **Providers:** `LLMFactory.create(model, temperature)` only — never instantiate providers directly
- **Config:** `from config.settings import settings` — never `os.getenv()` or `load_dotenv()` directly
- **GitHub API:** `GitHubService` / `GitHubAppService` only — never call PyGithub/requests outside `services/`
- **Retries:** `tenacity` in providers/services only — no graph-level retries
- **Inline comments:** always use `find_line_in_file` against real file content — never parse diff line numbers
- **Batch posting:** always use `create_review_with_comments` for inline comments — never post one-by-one in a loop
- **Snippet source:** `existing_code_to_replace` must come from the reviewed file's diff — never from dependency context

## Adding Components

**Agent/Node pair:** `src/agents/<name>.py` (plain fn) → `src/prompts/<name>.py` → `src/nodes/<name>_node.py` → wire in `src/graph/builder.py`

**LLM Provider:** implement `LLMProvider` in `src/providers/<name>.py` → add routing in `factory.py` + enum in `models.py`

**Import Resolver language:** implement `LanguageExtractor` in `src/agents/import_resolver.py` → add extension entries to `_EXTRACTORS`

**Dependency Resolver (legacy):** implement `DependencyResolver` → register in `RESOLVER_REGISTRY`

**Python Resolver Plugin:** implement `PythonImportPlugin` or `PythonAttrPlugin` → pass to `create_python_resolver()` or `PythonResolver(plugins=...)`

## Local Testing

`run_review_from_file` in `src/main.py` reads `installation.id` from the mock JSON payload and exchanges it for a GitHub App installation token automatically — the same auth flow as the live webhook. No PAT required for private repos.

```bash
uv sync                          # install deps
uv run python -m main            # run with default tests/mock_input.json
uv run python -m main <file>     # run with custom payload (must include installation.id)
uv run pytest                    # all tests
uv run ruff check src/ tests/    # lint
uv run ruff format src/ tests/   # format
```

Mock payload schema: standard GitHub `pull_request` webhook JSON. Must include `pull_request.number`, `repository.name`, `repository.owner.login`, and `installation.id` for App auth.

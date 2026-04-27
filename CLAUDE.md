# LangGraph PR Review Bot

AI-powered GitHub PR reviewer using LangGraph Map-Reduce (fan-out/fan-in). Receives webhook payloads, reviews files in parallel, posts inline diff comments.

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

## Graph Workflow (in order)

```
START
  → persona_node          # run_persona(repo_name) → system_prompt
  → fetch_sha_node        # fetch PR HEAD SHA → head_sha
  → fetch_tree_node       # GitHub Trees API → repo_tree (fetched once, shared to all parallel branches)
  → [_map_files_to_review]  # fan-out: Send per file (skips doc files + trivial diffs)
      → review_single_file [subgraph per file, parallel]:
          → context_node  # LLM picks relevant files from repo_tree, fetches content → dependency_context
          → review_node   # run_review() → appends JSON to file_reviews
  → synthesis_node        # cross-file analysis using all file_reviews → synthesis_reviews
  → aggregate_node        # joins file_reviews + synthesis_reviews → final_comment
  → post_review_node      # posts inline diff comments to GitHub
END
```

### State Models (`src/state/models.py`)
```python
class PRReviewState:
    pr_id, owner, repo_name, pr_files, github_token, head_sha
    pr_title, pr_body           # passed into synthesis
    system_prompt, repo_tree    # fetched once; repo_tree shared to all SingleFileStates
    file_reviews: Annotated[list[str], operator.add]  # reducer: parallel branches append
    synthesis_reviews: list[str]
    final_comment, error

class SingleFileState:
    pr_id, owner, repo_name, head_sha, github_token
    pr_title, pr_body, filename, diff, system_prompt
    repo_tree                   # subset passed from PRReviewState
    dependency_context          # filled by context_node
    file_reviews: Annotated[list[str], operator.add]
```

## Context Selection (replaces old dependency resolver)

`fetch_tree_node` fetches the full repo file tree once via GitHub Trees API. Each `context_node` runs `run_context_selector()` — a lightweight LLM call that picks up to 8 relevant files from the tree for that specific diff. Content is fetched and formatted as `dependency_context`.

## Synthesis Node

After all per-file reviews fan-in, `synthesis_node` calls `run_synthesis()` to find cross-file issues invisible to per-file reviewers (e.g., interface mismatches, state mutation patterns across modules). Outputs `SynthesisOutput` with `SynthesisIssue[]`.

## Dependency Resolver System (`src/services/dependency/`)

Plugin-based strategy pattern — context-aware for different repo types.

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

**Context-aware usage:** `get_context_aware_registry(repo_root)` inspects the repo (e.g., detects `package.xml` for ROS2) and builds the appropriate resolver with correct plugins. Use this when repo root is available. Use static `RESOLVER_REGISTRY` / `get_resolver(filename)` as fallback.

**Adding a new resolver:** implement `DependencyResolver.guess_paths()` → register in `RESOLVER_REGISTRY` (no other changes needed).
**Adding a Python plugin:** implement `PythonImportPlugin` or `PythonAttrPlugin` → pass to `PythonResolver(plugins=[...])`.

## GitHub Services (`src/services/`)

| Service | File | Auth |
|---|---|---|
| `GitHubService` | `github.py` | PAT token |
| `GitHubAppService` | `github_app.py` | GitHub App JWT + installation token |

Key `GitHubService` methods: `fetch_diff`, `fetch_file_content`, `fetch_repo_tree`, `fetch_pr_head_sha`, `create_inline_comment`, `create_pr_review`, `post_pr_comment`

`find_line_in_file(file_content, code_snippet) → (start, end) | None` — matches snippets to 1-based line numbers in real file content (never parse diff for line numbers).

## Inline Comment Flow

`post_review_node` for each `ReviewItem`: fetch file at `head_sha` → `find_line_in_file()` → `create_inline_comment(side=RIGHT, line=...)` → fallback to `post_pr_comment` if line not found.

## Review Output Format (`FileReviewOutput`)
```json
{
  "filename": "src/auth.py",
  "reviews": [{
    "title": "...", "detail": "...",
    "existing_code_to_replace": "exact 1-3 lines from diff",
    "suggestion_for_change": "...",
    "exact_code_replacement": "...",
    "critical_rate": "High"
  }]
}
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
- **Inline comments:** `find_line_in_file` + `create_inline_comment` — never parse diff for line numbers

## Adding Components

**Agent/Node pair:** `src/agents/<name>.py` (plain fn) → `src/prompts/<name>.py` → `src/nodes/<name>_node.py` → wire in `src/graph/builder.py`

**LLM Provider:** implement `LLMProvider` in `src/providers/<name>.py` → add routing in `factory.py` + enum in `models.py`

**Dependency Resolver:** implement `DependencyResolver` → register in `RESOLVER_REGISTRY`

**Python Resolver Plugin:** implement `PythonImportPlugin` or `PythonAttrPlugin` → pass to `create_python_resolver()` or `PythonResolver(plugins=...)`

## Commands
```bash
uv sync                          # install deps
uv run python -m main            # run with default tests/mock_input.json
uv run python -m main <file>     # run with custom payload
uv run pytest                    # all tests
uv run ruff check src/ tests/    # lint
uv run ruff format src/ tests/   # format
```

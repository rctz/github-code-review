# Project Overview: LangGraph PR Review Bot

## 1. Description
This project is an AI-powered GitHub Pull Request Review Bot built with **LangGraph** and **Python**. It receives GitHub Webhooks containing PR diffs, processes multiple files in parallel using a Map-Reduce (Fan-out/Fan-in) architecture, and posts **inline review comments** pointing to exact lines in the PR diff back to GitHub.

Designed as an **organizational template** — teams can compose their own graphs by wiring together agents and nodes from the shared library.

## 2. Tech Stack & Environment
- **Core Framework:** LangGraph, LangChain (`langchain-litellm`, `langchain-core`)
- **LLM Provider:** LiteLLM proxy (via `LLMFactory` — provider-agnostic)
- **State Validation:** Pydantic v2 (Pydantic state models for LangGraph)
- **Configuration:** `pydantic-settings` (loads `.env` centrally)
- **Retry/Resilience:** `tenacity` (exponential backoff, 3 attempts)
- **Package Manager:** `uv`
- **Python Version:** **Strictly 3.12 or 3.13**
- **Linting:** Ruff

## 3. Architecture: Modular Layered Design

The codebase enforces strict separation between concerns:

| Layer | Directory | Responsibility |
|---|---|---|
| **Config** | `src/config/` | Centralized settings via `pydantic-settings` (`.env` loader) |
| **Prompts** | `src/prompts/` | Prompt templates decoupled from agent logic |
| **State** | `src/state/` | Pydantic state models for LangGraph |
| **Providers** | `src/providers/` | Abstract `LLMProvider` + factory + implementations |
| **Agents** | `src/agents/` | Pure LLM logic — no LangGraph awareness |
| **Nodes** | `src/nodes/` | Thin wrappers: LangGraph state ↔ agent calls |
| **Graph** | `src/graph/` | Orchestration only — subgraphs, edges, fan-out/fan-in |
| **Services** | `src/services/` | External API integrations (GitHub) |
| **Entry** | `src/main.py` | CLI entry point (webhook-ready via `entrypoints/`) |

### Key Design Principles
- **Agents are testable in isolation** — pass plain args, no need to mock LangGraph state.
- **Nodes are swappable** — change graph structure without touching agent logic.
- **A node can call multiple agents** — sequential or parallel (`asyncio.gather`).
- **Providers are pluggable** — swap LLM via `LLMFactory.create(model=...)` without code changes.
- **Prompts are editable without touching code** — all templates in `src/prompts/`.
- **Error handling is built-in** — nodes catch exceptions, `error_node` available for graceful degradation.

## 4. Directory Structure
```text
├── pyproject.toml              # uv/hatchling config, deps, ruff, pytest
├── .env                        # Secrets (never committed)
├── CLAUDE.md                   # This file
│
├── src/                        # Source code (installed via hatchling sources map)
│   ├── __init__.py
│   ├── main.py                 # CLI entry point
│   │
│   ├── config/
│   │   ├── __init__.py
│   │   └── settings.py         # pydantic-settings: loads .env, validates keys
│   │
│   ├── prompts/
│   │   ├── __init__.py
│   │   ├── persona.py          # PERSONA_SYSTEM_PROMPT template
│   │   ├── dependency.py       # DEPENDENCY_CONTEXT_TEMPLATE, NO_DEPENDENCIES_MESSAGE
│   │   └── review.py           # REVIEW_PROMPT_TEMPLATE
│   │
│   ├── state/
│   │   ├── __init__.py
│   │   └── models.py           # Pydantic: PRReviewState, SingleFileState, SingleFileOutput
│   │
│   ├── providers/
│   │   ├── __init__.py
│   │   ├── base.py             # ABC: LLMProvider (chat, chat_stream)
│   │   ├── factory.py          # LLMFactory.create(model, temperature) -> LLMProvider
│   │   ├── models.py           # LiteLLMModel enum
│   │   ├── litellm.py          # LiteLLMProvider (tenacity retry)
│   │   ├── openrouter.py       # OpenRouterProvider (tenacity retry)
│   │   └── azure.py            # AzureProvider (tenacity retry)
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── persona.py          # run_persona(repo_name) -> str
│   │   ├── dependency.py       # run_dependency(filename, diff, repo_name, head_sha, github_service) -> str
│   │   └── review.py           # run_review(...) -> FileReviewOutput
│   │                           #   Also: ReviewItem, FileReviewOutput (Pydantic)
│   │
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── persona_node.py     # persona_node(state) -> dict
│   │   ├── dependency_node.py  # dependency_node(state) -> dict
│   │   ├── review_node.py      # review_node(state) -> dict
│   │   ├── aggregate_node.py   # aggregate_node(state) -> dict
│   │   ├── fetch_sha_node.py   # fetch_sha_node(state) -> dict (fetches PR HEAD SHA)
│   │   ├── post_review_node.py # post_review_node(state) -> dict (posts inline comments)
│   │   └── error_node.py       # error_node(state) -> dict (graceful failure)
│   │
│   ├── graph/
│   │   ├── __init__.py
│   │   └── builder.py          # build_graph(), build_compiled_graph()
│   │
│   └── services/
│       ├── __init__.py
│       ├── dependency_resolver.py  # Strategy pattern: DependencyResolver ABC + CppResolver + PythonResolver + registry
│       └── github.py           # GitHubService + find_line_in_file utility
│
├── entrypoints/                # Future: FastAPI webhook handler
│   └── __init__.py
│
└── tests/
    ├── __init__.py
    ├── conftest.py              # Shared fixtures (mock LLM, mock github)
    ├── mock_input.json          # Sample GitHub webhook payload
    ├── unit/
    │   ├── __init__.py
    │   ├── test_agents.py       # Agent unit tests
    │   ├── test_dependency_resolver.py  # Resolver strategy tests
    │   ├── test_nodes.py        # Node unit tests
    │   ├── test_providers.py    # Provider factory + abstract tests
    │   └── test_services_github.py  # GitHub service tests
    └── integration/
        ├── __init__.py
        └── test_graph.py        # Full graph integration test
```

## 5. LangGraph Architecture (Map-Reduce / Parallel Execution)

### 5.1 State Definitions (`src/state/models.py`)
Pydantic models with LangGraph reducer annotations:
```python
class PRReviewState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    pr_id: str
    owner: str
    repo_name: str
    pr_files: list[dict]
    github_token: str = ""
    head_sha: str = ""
    system_prompt: str = ""
    file_reviews: Annotated[list[str], operator.add] = []
    final_comment: str = ""
    error: str = ""

class SingleFileState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    pr_id: str
    owner: str = ""
    repo_name: str
    head_sha: str = ""
    github_token: str = ""
    filename: str
    diff: str = ""
    system_prompt: str = ""
    dependency_context: str = ""
    file_reviews: Annotated[list[str], operator.add] = []
```
`owner`, `head_sha`, and `github_token` are passed from `PRReviewState` through the `Send` fan-out so the dependency node can call `GitHubService`.

### 5.2 Workflow Steps
1. **`persona_node`** — calls `run_persona(repo_name)` → writes `system_prompt` to state.
2. **`fetch_sha_node`** — fetches the PR's HEAD commit SHA → writes `head_sha` to state.
3. **`_map_files_to_review`** (conditional edge) — fans out one `Send("review_single_file", ...)` per file (deduplicates by filename). Passes `owner`, `head_sha`, `github_token` into each `SingleFileState`.
4. **`review_single_file`** (subgraph, runs in parallel per file):
   - `dependency_node` → resolves dependency file paths via `RESOLVER_REGISTRY`, fetches actual content via `GitHubService`, formats into `dependency_context` (see §7)
   - `review_node` → calls `run_review(...)` → appends JSON to `file_reviews`
5. **`aggregate_node`** — joins all `file_reviews` into `final_comment`.
6. **`post_review_node`** — posts **inline diff comments** pointing to exact lines (see §6).

### 5.3 Review Output Format
Each file review is a JSON string matching `FileReviewOutput`:
```json
{
  "filename": "src/auth.py",
  "reviews": [
    {
      "title": "SQL injection via string interpolation",
      "detail": "The query uses f-string interpolation with user input...",
      "existing_code_to_replace": "the exact 1-3 lines of code from the diff",
      "suggestion_for_change": "Use parameterized queries",
      "exact_code_replacement": "db.execute('SELECT * FROM users WHERE name=?', [username])",
      "critical_rate": "High"
    }
  ]
}
```

## 6. Inline Review Comment System

### 6.1 How It Works
Instead of posting general issue comments, the bot posts **inline diff comments** that point to specific lines in the PR — exactly like a human reviewer clicking on a line in the GitHub diff view.

For each `ReviewItem`, `post_review_node`:
1. **Fetches the file content** from GitHub at the PR HEAD commit (`fetch_file_content`)
2. **Finds the exact line number** by matching `existing_code_to_replace` against the real file content via `find_line_in_file()` — returns 1-based `(start_line, end_line)`
3. **Posts an inline comment** via `create_inline_comment()` using the GitHub `POST /repos/{owner}/{repo}/pulls/{pull_number}/comments` API with `line`, `side=RIGHT`, `commit_id`, and `path`
4. **Falls back** to a general PR comment if line resolution fails

### 6.2 Why File-Content Matching (Not Diff Parsing)
The line resolver uses **real file content** instead of parsing the unified diff. This avoids a class of bugs:
- **Diff parsing is fragile** — tracking new-side line numbers across `+`/`-`/` ` lines is error-prone; interleaved deletions cause line counter drift
- **Off-by-one errors** — the `@@ -a +b @@` header starts at line `b`, but context/deletion lines shift counters differently
- **Whitespace mismatch** — diff lines have `+`/`-`/` ` prefixes that must be stripped; context lines carry a leading space
- **Same commit guarantee** — `fetch_file_content(ref=head_sha)` uses the same SHA passed as `commit_id` to the comment API, so file state and line numbers are always consistent

### 6.3 GitHubService Methods (`src/services/github.py`)

| Method | API Endpoint | Purpose |
|---|---|---|
| `fetch_diff` | PyGithub | Fetch PR file diffs |
| `fetch_file_content` | `GET /repos/{owner}/{repo}/contents/{path}` | Fetch real file at a given ref |
| `fetch_pr_head_sha` | PyGithub | Get PR HEAD commit SHA |
| `create_inline_comment` | `POST /repos/{owner}/{repo}/pulls/{pr}/comments` | Post inline review comment on diff line |
| `create_pr_review` | `POST /repos/{owner}/{repo}/pulls/{pr}/reviews` | Create a PR review (APPROVE/COMMENT/REQUEST_CHANGES) |
| `post_pr_comment` | `POST /repos/{owner}/{repo}/issues/{pr}/comments` | Post general issue comment (fallback) |

### 6.4 Module-level utility: `find_line_in_file`
```python
def find_line_in_file(file_content: str, code_snippet: str) -> tuple[int, int] | None
```
Searches the real file content for an exact stripped match of `code_snippet`. Returns `(start_line, end_line)` (1-based) or `None`. File contents are cached per file in `post_review_node` so each file is fetched only once.

## 7. Dependency Resolution System

### 7.1 Strategy Pattern (Registry)
Dependency resolution uses the Strategy Pattern via a file-extension registry (`src/services/dependency_resolver.py`). Each resolver guesses candidate file paths from the diff content, then the node fetches actual content via `GitHubService`.

```python
class DependencyResolver(ABC):
    def guess_paths(self, filename: str, content: str, repo_name: str) -> list[str]: ...

RESOLVER_REGISTRY: dict[str, DependencyResolver] = {
    ".cpp": CppResolver(), ".cc": CppResolver(), ".cxx": CppResolver(), ".c": CppResolver(),
    ".hpp": CppResolver(), ".h": CppResolver(),
    ".py": PythonResolver(),
}

def get_resolver(filename: str) -> DependencyResolver | None: ...
```

### 7.2 Resolver Implementations

| Resolver | Extensions | Heuristic |
|---|---|---|
| `CppResolver` | `.cpp`, `.cc`, `.cxx`, `.c`, `.hpp`, `.h` | Parses `+#include` lines. For `"..."` includes: same-dir header + `include/` dir. For `<...>` includes: `include/` dir + ROS2 `include/<pkg>/` pattern. `pkg_name` extracted from `repo_name`. |
| `PythonResolver` | `.py` | Parses `+from X import Y` and `+import X.Y` lines. Converts dotted imports to file paths (`a.b.c` → `a/b/c.py`, `a/b/c/__init__.py`). Filters out stdlib modules (`os`, `sys`, `json`, etc.). |

### 7.3 Data Flow
1. **`dependency_node`** — looks up resolver by file extension, constructs `GitHubService(token=state.github_token)`, calls `run_dependency()`.
2. **`run_dependency`** (agent) — calls `resolver.guess_paths()` to get candidates, fetches up to `LIMIT_IMPORT_CHECK=7` files via `GitHubService.fetch_file_content()`, skips errors, formats with `DEPENDENCY_CONTEXT_TEMPLATE`.
3. **Output** — formatted dependency context string (or `NO_DEPENDENCIES_MESSAGE` if nothing found), written to `state.dependency_context`.

### 7.4 Adding a New Resolver
1. Create a class implementing `DependencyResolver` in `src/services/dependency_resolver.py`.
2. Register it in `RESOLVER_REGISTRY` with the target file extension(s).
3. No changes to agents, nodes, or graph needed — the registry handles routing automatically.

## 8. Key Implementation Rules

- **Agent signature:** Agents accept plain Python args and return plain values or Pydantic models — never state objects.
- **Node signature:** Nodes accept a Pydantic state model and return `dict` — never call LLM directly.
- **Parallel processing:** Never loop through files inside a node. Always use the `Send` API via a conditional edge to fan-out.
- **State reducers:** Use `Annotated[list[str], operator.add]` for keys that aggregate across parallel branches.
- **Provider access:** Use `LLMFactory.create(model, temperature)` — never instantiate providers directly in agents.
- **Prompt access:** Import from `prompts/` module — never inline prompt strings in agents.
- **Configuration:** Use `from config.settings import settings` — never call `os.getenv()` or `load_dotenv()` directly.
- **GitHub API:** Use `GitHubService` class — never call PyGithub or requests directly outside of `services/`.
- **Dependency resolution:** Use `get_resolver(filename)` from `RESOLVER_REGISTRY` — never build if-else chains for file-type logic.
- **Inline comments:** Use `create_inline_comment` with `side=RIGHT` and line numbers from `find_line_in_file` — never parse the diff for line numbers.
- **Error handling:** Nodes catch exceptions and return fallback values. Wire `error_node` for catastrophic failures.
- **Retry logic:** Handled by `tenacity` in providers and services (max 3 attempts, exponential backoff). Do not add retries at the graph level.

## 9. Adding New Components

### New Agent/Node Pair
1. Create `src/agents/<name>.py` with `run_<name>(plain_args...) -> OutputType`.
2. Create `src/prompts/<name>.py` with prompt templates.
3. Create `src/nodes/<name>_node.py` with `<name>_node(state) -> dict`.
4. Register in `src/graph/builder.py` and wire edges.

### New LLM Provider
1. Create `src/providers/<name>.py` implementing `LLMProvider`.
2. Add routing logic in `src/providers/factory.py`.
3. Add model enum values in `src/providers/models.py` if needed.

### New Dependency Resolver
1. Create a class implementing `DependencyResolver` in `src/services/dependency_resolver.py`.
2. Register it in `RESOLVER_REGISTRY` with the target file extension(s).
3. No changes to agents, nodes, or graph needed — the registry handles routing automatically.

### New Entry Point (e.g., FastAPI Webhook)
1. Create `entrypoints/webhook.py` with FastAPI app.
2. Import `build_compiled_graph()` and `PRReviewState` from `src/`.

## 10. Running the Project

```bash
# Install dependencies
uv sync

# Run CLI with default mock input
uv run python -m main
# or with custom input
uv run python -m main path/to/payload.json

# Run tests
uv run pytest

# Lint
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

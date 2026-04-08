# Project Overview: LangGraph PR Review Bot

## 1. Description
This project is an AI-powered GitHub Pull Request Review Bot built with **LangGraph** and **Python**. It receives GitHub Webhooks containing PR diffs, processes multiple files in parallel using a Map-Reduce (Fan-out/Fan-in) architecture, and posts a consolidated review comment back to GitHub.

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
│   │   ├── dependency.py       # run_dependency(diff) -> str
│   │   └── review.py           # run_review(...) -> FileReviewOutput
│   │                           #   Also: ReviewItem, FileReviewOutput (Pydantic)
│   │
│   ├── nodes/
│   │   ├── __init__.py
│   │   ├── persona_node.py     # persona_node(state) -> dict
│   │   ├── dependency_node.py  # dependency_node(state) -> dict
│   │   ├── review_node.py      # review_node(state) -> dict
│   │   ├── aggregate_node.py   # aggregate_node(state) -> dict
│   │   └── error_node.py       # error_node(state) -> dict (graceful failure)
│   │
│   ├── graph/
│   │   ├── __init__.py
│   │   └── builder.py          # build_graph(), build_compiled_graph()
│   │
│   └── services/
│       ├── __init__.py
│       └── github.py           # GitHubService (fetch_diff, fetch_file_content, post_pr_comment)
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
from pydantic import BaseModel, ConfigDict
import operator
from typing import Annotated

class PRReviewState(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    pr_id: str
    repo_name: str
    pr_files: list[dict]
    system_prompt: str = ""
    file_reviews: Annotated[list[str], operator.add] = []
    final_comment: str = ""
    error: str = ""
```

### 5.2 Workflow Steps
1. **`persona_node`** — calls `run_persona(repo_name)` → writes `system_prompt` to state.
2. **`_map_files_to_review`** (conditional edge) — fans out one `Send("review_single_file", ...)` per file (deduplicates by filename).
3. **`review_single_file`** (subgraph, runs in parallel per file):
   - `dependency_node` → calls `run_dependency(diff)` → writes `dependency_context`
   - `review_node` → calls `run_review(...)` → appends markdown to `file_reviews`
4. **`aggregate_node`** — joins all `file_reviews` into `final_comment`.

### 5.3 Review Output Format
Each file review is a JSON string matching `FileReviewOutput`:
```json
{
  "filename": "src/auth.py",
  "reviews": [
    {
      "title": "SQL injection via string interpolation",
      "detail": "The query uses f-string interpolation with user input...",
      "suggestion_for_change": "Use parameterized queries: db.execute('SELECT * FROM users WHERE name=?', [username])",
      "critical_rate": "High"
    }
  ]
}
```

## 6. Key Implementation Rules

- **Agent signature:** Agents accept plain Python args and return plain values or Pydantic models — never state objects.
- **Node signature:** Nodes accept a Pydantic state model and return `dict` — never call LLM directly.
- **Parallel processing:** Never loop through files inside a node. Always use the `Send` API via a conditional edge to fan-out.
- **State reducers:** Use `Annotated[list[str], operator.add]` for keys that aggregate across parallel branches.
- **Provider access:** Use `LLMFactory.create(model, temperature)` — never instantiate providers directly in agents.
- **Prompt access:** Import from `prompts/` module — never inline prompt strings in agents.
- **Configuration:** Use `from config.settings import settings` — never call `os.getenv()` or `load_dotenv()` directly.
- **GitHub API:** Use `GitHubService` class — never call PyGithub or requests directly outside of `services/`.
- **Error handling:** Nodes catch exceptions and return fallback values. Wire `error_node` for catastrophic failures.
- **Retry logic:** Handled by `tenacity` in providers and services (max 3 attempts, exponential backoff). Do not add retries at the graph level.

## 7. Adding New Components

### New Agent/Node Pair
1. Create `src/agents/<name>.py` with `run_<name>(plain_args...) -> OutputType`.
2. Create `src/prompts/<name>.py` with prompt templates.
3. Create `src/nodes/<name>_node.py` with `<name>_node(state) -> dict`.
4. Register in `src/graph/builder.py` and wire edges.

### New LLM Provider
1. Create `src/providers/<name>.py` implementing `LLMProvider`.
2. Add routing logic in `src/providers/factory.py`.
3. Add model enum values in `src/providers/models.py` if needed.

### New Entry Point (e.g., FastAPI Webhook)
1. Create `entrypoints/webhook.py` with FastAPI app.
2. Import `build_compiled_graph()` and `PRReviewState` from `src/`.

## 8. Running the Project

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

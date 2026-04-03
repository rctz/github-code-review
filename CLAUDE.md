# Project Overview: LangGraph PR Review Bot

## 1. Description
This project is an AI-powered GitHub Pull Request Review Bot built with **LangGraph** and **Python**. It receives GitHub Webhooks containing PR diffs, processes multiple files in parallel using a Map-Reduce (Fan-out/Fan-in) architecture, and posts a consolidated review comment back to GitHub.

Designed as an **organizational template** — teams can compose their own graphs by wiring together agents and nodes from the shared library.

## 2. Tech Stack & Environment
- **Core Framework:** LangGraph, LangChain (`langchain-litellm`, `langchain-core`)
- **LLM Provider:** LiteLLM proxy (`LITELLM_API_BASE` + `LITELLM_API_KEY` env vars)
- **Package Manager:** `uv`
- **Python Version:** **Strictly 3.12 or 3.13** (Avoid Python 3.14+ due to Pydantic V1 compatibility issues with `langchain_core`).

## 3. Architecture: Two-Layer Design

The codebase enforces a strict separation between **business logic** and **orchestration**:

| Layer | Directory | Responsibility |
|---|---|---|
| **Agents** | `agents/` | Pure LLM logic — no LangGraph awareness |
| **Nodes** | `nodes/` | Thin wrappers that translate LangGraph state ↔ agent calls |
| **Graph** | `graph.py` | Orchestration only — subgraphs, edges, fan-out/fan-in |
| **State** | `state.py` | TypedDict definitions |
| **Tools** | `tools/` | External API integrations (GitHub, etc.) |
| **Providers** | `providers/` | LLM client wrappers |

### Why two layers?
- **Agents are testable in isolation** — pass plain args, no need to mock LangGraph state.
- **Nodes are swappable** — change graph structure without touching agent logic.
- **A node can call multiple agents** — sequential or parallel (`asyncio.gather`).
- **Agents are reusable** — callable from any node or outside the graph entirely.

## 4. Directory Structure
```text
├── pyproject.toml              # uv dependency management
├── main.py                     # Entry point / test runner
├── graph.py                    # LangGraph workflow (StateGraph, subgraphs, edges)
├── state.py                    # TypedDict state definitions
│
├── agents/                     # Pure business logic — no LangGraph state
│   ├── __init__.py
│   ├── persona.py              # run_persona(repo_name) -> str
│   ├── dependency.py           # run_dependency(diff) -> str
│   └── review.py               # run_review(...) -> FileReviewOutput
│                               # Also contains: ReviewItem, FileReviewOutput (Pydantic)
│
├── nodes/                      # LangGraph wrappers — thin, state-aware
│   ├── __init__.py
│   ├── persona_node.py         # persona_node(state: PRReviewState) -> dict
│   ├── dependency_node.py      # dependency_node(state: SingleFileState) -> dict
│   ├── review_node.py          # review_node(state: SingleFileState) -> dict
│   └── aggregate_node.py       # aggregate_node(state: PRReviewState) -> dict
│
├── tools/                      # External integrations
│   ├── __init__.py
│   └── github.py               # fetch_file_content(), post_pr_comment()
│
└── providers/                  # LLM provider wrappers
    ├── __init__.py
    ├── litellm.py              # LiteLLM (primary)
    ├── models.py               # LiteLLMModel enum
    ├── azure.py
    └── openrouter.py
```

## 5. LangGraph Architecture (Map-Reduce / Parallel Execution)

### 5.1 State Definitions (`state.py`)
```python
import operator
from typing import Annotated, TypedDict

class PRReviewState(TypedDict):
    pr_id: str
    repo_name: str
    pr_files: list[dict]  # [{"filename": "...", "diff": "..."}]
    system_prompt: str
    file_reviews: Annotated[list[str], operator.add]  # reducer: appends
    final_comment: str

class SingleFileState(TypedDict):
    pr_id: str
    repo_name: str
    filename: str
    diff: str
    system_prompt: str
    dependency_context: str
    file_reviews: Annotated[list[str], operator.add]

class SingleFileOutput(TypedDict):
    file_reviews: Annotated[list[str], operator.add]
```

### 5.2 Workflow Steps
1. **`persona_node`** — calls `run_persona(repo_name)` → writes `system_prompt` to state.
2. **`_map_files_to_review`** (conditional edge) — fans out one `Send("review_single_file", ...)` per file.
3. **`review_single_file`** (subgraph, runs in parallel per file):
   - `dependency_node` → calls `run_dependency(diff)` → writes `dependency_context`
   - `review_node` → calls `run_review(...)` → appends JSON to `file_reviews`
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

- **Agent signature:** Agents accept plain Python args and return plain values or Pydantic models — never TypedDict or LangGraph state.
- **Node signature:** Nodes accept a TypedDict state and return `dict` — never call LLM directly.
- **Parallel processing:** Never loop through files inside a node. Always use the `Send` API via a conditional edge to fan-out.
- **State reducers:** Use `Annotated[list[str], operator.add]` for keys that aggregate across parallel branches (e.g. `file_reviews`).
- **Message handling:** Always wrap messages in a list when calling `llm.invoke([...])`.
- **LLM provider:** Use `LiteLLM` from `providers/litellm.py`. Configure via `LITELLM_API_BASE` and `LITELLM_API_KEY` env vars.

## 7. Extending the Template

To add a new agent/node pair:
1. Create `agents/<name>.py` with a `run_<name>(plain_args...) -> OutputType` function.
2. Create `nodes/<name>_node.py` with a `<name>_node(state: SomeState) -> dict` wrapper.
3. Register the node in `graph.py` and wire edges.

A node can call multiple agents — sequentially or in parallel with `asyncio.gather`.

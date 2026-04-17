# LangGraph PR Review Bot

AI-powered GitHub Pull Request Review Bot built with **LangGraph** and **Python**. Processes multiple files in parallel using a Map-Reduce (Fan-out/Fan-in) architecture and posts consolidated review comments back to GitHub.

## Requirements

- Python 3.12 or 3.13
- [uv](https://docs.astral.sh/uv/) package manager
- LiteLLM proxy server (or compatible OpenAI-compatible API)
- GitHub Personal Access Token

## Quick Start

### 1. Install dependencies

```bash
uv sync
```

For development (includes pytest, ruff):

```bash
uv sync --extra dev
```

### 2. Configure environment

Copy `.env.example` and fill in your credentials:

```bash
cp .env.example .env
```

Required variables in `.env`:

```env
LITELLM_API_KEY=your-litellm-api-key
LITELLM_API_BASE=http://your-litellm-proxy:4000/
GITHUB_TOKEN=ghp_your_github_token
```

Optional:

```env
OPENROUTER_API_KEY=your-openrouter-key
AZURE_API_KEY=your-azure-key
LOG_LEVEL=INFO
```

### 3. Run

With default mock input:

```bash
uv run python src/main.py
```

With a custom payload:

```bash
uv run python src/main.py path/to/payload.json
```

Or via the installed entry point:

```bash
uv run pr-review
```

## Architecture

```
src/
├── config/          pydantic-settings (.env loader)
├── prompts/         Prompt templates (decoupled from logic)
├── state/           Pydantic state models for LangGraph
├── providers/       Abstract LLMProvider + factory + implementations
├── agents/          Pure LLM logic (no LangGraph awareness)
├── nodes/           Thin wrappers: LangGraph state ↔ agent calls
├── graph/           Orchestration (subgraphs, edges, fan-out/fan-in)
├── services/        External APIs (GitHub) + dependency resolver
└── main.py          CLI entry point
```

**Workflow:**

1. `persona_node` — generates a reviewer system prompt from the repo name
2. `fetch_sha_node` — fetches the PR HEAD commit SHA
3. Fan-out — one parallel subgraph per file (deduplicates by filename), passes `owner`, `head_sha`, `github_token` to each
4. Each subgraph: `dependency_node` → `review_node`
   - `dependency_node` resolves dependency file paths via a Strategy Pattern registry, fetches actual content from GitHub, and formats dependency context
5. `aggregate_node` — merges all file reviews into a single markdown comment
6. `post_review_node` — posts inline review comments pointing to exact diff lines

## Dependency Resolution

The bot uses a **Strategy Pattern registry** (`src/services/dependency_resolver.py`) to guess and fetch code dependencies before review:

| Resolver | Extensions | Strategy |
|---|---|---|
| `CppResolver` | `.cpp`, `.cc`, `.cxx`, `.c`, `.hpp`, `.h` | Parses `#include` lines. Guesses same-dir headers, `include/` paths, and ROS2 `include/<pkg>/` patterns. |
| `PythonResolver` | `.py` | Parses `from X import Y` / `import X.Y`. Converts dotted imports to file paths, filters stdlib modules. |

The registry is extensible — add new resolvers without modifying agents, nodes, or graph structure.

## Testing

### Run all tests

```bash
uv run pytest
```

### Run with verbose output

```bash
uv run pytest -v
```

### Run specific test suites

```bash
# Unit tests only
uv run pytest tests/unit/

# Integration tests only
uv run pytest tests/integration/

# Single test file
uv run pytest tests/unit/test_agents.py

# Single test case
uv run pytest tests/unit/test_agents.py::TestReviewAgent::test_parse_valid_json
```

### Run with coverage

```bash
uv run pytest --tb=short -q
```

**Test structure:**

| Suite | File | What it covers |
|---|---|---|
| Agents | `tests/unit/test_agents.py` | Persona, dependency (with resolver + mock GitHub), review logic |
| Resolver | `tests/unit/test_dependency_resolver.py` | CppResolver, PythonResolver, registry lookup |
| Nodes | `tests/unit/test_nodes.py` | LangGraph node wrappers + error handling |
| Providers | `tests/unit/test_providers.py` | Factory pattern, model enum, ABC |
| Services | `tests/unit/test_services_github.py` | GitHub API (fetch diff, post comment) |
| Graph | `tests/integration/test_graph.py` | Full graph execution, fan-out, error recovery |

## Linting & Formatting

```bash
# Check lint
uv run ruff check src/ tests/

# Auto-fix lint issues
uv run ruff check --fix src/ tests/

# Check formatting
uv run ruff format --check src/ tests/

# Auto-format
uv run ruff format src/ tests/
```

## Adding New Components

### New Agent/Node Pair

1. `src/agents/<name>.py` — `run_<name>(plain_args...) -> OutputType`
2. `src/prompts/<name>.py` — prompt templates
3. `src/nodes/<name>_node.py` — `<name>_node(state) -> dict`
4. Register in `src/graph/builder.py` and wire edges

### New LLM Provider

1. `src/providers/<name>.py` — implement `LLMProvider` ABC
2. Add routing in `src/providers/factory.py`
3. Add model enum in `src/providers/models.py`

### New Dependency Resolver

1. `src/services/dependency_resolver.py` — implement `DependencyResolver` ABC
2. Register in `RESOLVER_REGISTRY` with target file extension(s)
3. No changes needed to agents, nodes, or graph — the registry handles routing automatically

### FastAPI Webhook (Future)

1. Create `entrypoints/webhook.py`
2. Import `build_compiled_graph()` and `PRReviewState`

## Configuration Reference

| Variable | Required | Description |
|---|---|---|
| `LITELLM_API_KEY` | Yes | API key for LiteLLM proxy |
| `LITELLM_API_BASE` | Yes | LiteLLM proxy base URL |
| `GITHUB_TOKEN` | Yes | GitHub PAT with repo access |
| `OPENROUTER_API_KEY` | No | OpenRouter API key |
| `AZURE_API_KEY` | No | Azure AI API key |
| `LOG_LEVEL` | No | Python log level (default: `INFO`) |

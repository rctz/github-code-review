# LangGraph PR Review Bot

AI-powered GitHub Pull Request reviewer built with **LangGraph** and **Python**. Reviews PR files in parallel using Map-Reduce (fan-out/fan-in), selects relevant context files via LLM, runs cross-file synthesis, and posts inline diff comments to GitHub.

## How It Works

```
persona → fetch_sha → fetch_tree → [parallel per file: context → review] → synthesis → aggregate → post
```

- **`persona`** — generates a repo-specific reviewer persona
- **`fetch_tree`** — fetches the full repo file tree once (GitHub Trees API)
- **`context`** — LLM picks up to 8 relevant files from the tree per file diff
- **`review`** — reviews each file with dependency context
- **`synthesis`** — finds cross-file issues invisible to per-file reviewers
- **`post`** — posts inline comments on exact diff lines

---

## Requirements

- Python 3.12 or 3.13
- [`uv`](https://docs.astral.sh/uv/) package manager
- LiteLLM proxy (or compatible OpenAI API)
- GitHub Personal Access Token or GitHub App credentials

---

## Setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Configure environment

```bash
cp .env.example .env   # then fill in your values
```

**Required:**

```env
LITELLM_API_KEY=your-litellm-api-key
LITELLM_API_BASE=http://your-litellm-proxy:4000/
GITHUB_TOKEN=ghp_your_github_token
```

**Optional:**

```env
# GitHub App (alternative to PAT)
GITHUB_APP_ID=123456
GITHUB_APP_PRIVATE_KEY=/path/to/private-key.pem   # or raw PEM content

# Webhook server
GITHUB_WEBHOOK_SECRET=your-webhook-secret
WEBHOOK_HOST=0.0.0.0
WEBHOOK_PORT=8000

# LLM providers (if using OpenRouter or Azure instead of LiteLLM)
OPENROUTER_API_KEY=your-key
AZURE_API_KEY=your-key

# Application
LOG_LEVEL=INFO
MAX_CONCURRENT_LLM_CALLS=5
LLM_RATE_LIMIT=20
LLM_RATE_PERIOD_SECONDS=60
```

---

## Running

### CLI — mock payload (for development/testing)

Runs against `tests/mock_input.json` and writes output to `tests/review_output.md`:

```bash
uv run python src/main.py
```

With a custom payload file (GitHub webhook PR payload format):

```bash
uv run python src/main.py path/to/payload.json
```

### CLI — real PR

```python
# Use run_review_from_payload() directly in a script
from main import run_review_from_payload

result = run_review_from_payload(
    repo_name="my-repo",
    owner="my-org",
    pr_number=42,
    github_token="ghp_...",   # optional, falls back to GITHUB_TOKEN env var
)
print(result.final_comment)
```

### Webhook server (FastAPI)

Receives GitHub PR webhook events and triggers reviews automatically:

```bash
uv run uvicorn entrypoints.webhook:app --host 0.0.0.0 --port 8000
```

Configure your GitHub repo webhook:
- **Payload URL:** `http://your-server:8000/webhook`
- **Content type:** `application/json`
- **Events:** Pull requests (`opened`, `reopened`)
- **Secret:** must match `GITHUB_WEBHOOK_SECRET` in `.env`

---

## Testing

### Run all tests

```bash
uv run pytest
```

### Run with verbose output

```bash
uv run pytest -v
```

### Run a specific suite

```bash
uv run pytest tests/unit/
uv run pytest tests/integration/
```

### Run a single file or test

```bash
uv run pytest tests/unit/test_agents.py
uv run pytest tests/unit/test_agents.py::TestReviewAgent::test_parse_valid_json
```

### Run with coverage

```bash
uv run pytest --cov=src --cov-report=term-missing
```

**Test suites:**

| Suite | File | Covers |
|---|---|---|
| Agents | `test_agents.py` | persona, dependency, review agent logic |
| Resolvers | `test_dependency_resolver.py` | CppResolver, PythonResolver, plugins, registry |
| Nodes | `test_nodes.py` | node wrappers + error handling |
| Providers | `test_providers.py` | factory, model enum, LLMProvider ABC |
| GitHub | `test_services_github.py` | fetch diff, post comment, inline comments |
| Webhook | `test_webhook.py` | FastAPI handler, signature verification |
| Graph | `tests/integration/test_graph.py` | full graph execution, fan-out, fan-in |

---

## Linting & Formatting

```bash
uv run ruff check src/ tests/          # lint
uv run ruff check --fix src/ tests/    # auto-fix
uv run ruff format src/ tests/         # format
uv run ruff format --check src/ tests/ # check only
```

---

## Development

### Adding a new agent/node pair

1. `src/agents/<name>.py` — `run_<name>(plain_args) -> OutputType` (no LangGraph)
2. `src/prompts/<name>.py` — prompt templates
3. `src/nodes/<name>_node.py` — `<name>_node(state) -> dict`
4. Register in `src/graph/builder.py` and wire edges

### Adding a dependency resolver

1. Implement `DependencyResolver.guess_paths()` in `src/services/dependency/resolvers/`
2. Register in `RESOLVER_REGISTRY` in `src/services/dependency/registry.py`

### Adding a Python resolver plugin

Implement `PythonImportPlugin` or `PythonAttrPlugin` in `src/services/dependency/plugins/`, then pass to `create_python_resolver()` or `PythonResolver(plugins=[...])`.

### Adding an LLM provider

1. Implement `LLMProvider` in `src/providers/<name>.py`
2. Add routing in `src/providers/factory.py`
3. Add model constants in `src/providers/models.py`

### Mock input format

`tests/mock_input.json` is a standard GitHub Pull Request webhook payload. Replace it with any real PR webhook payload to test against a different repo.

---

## Project Structure

```
src/
├── config/settings.py       pydantic-settings (.env loader)
├── prompts/                 All prompt templates
├── state/models.py          PRReviewState, SingleFileState
├── providers/               LLMProvider ABC + factory + LiteLLM/OpenRouter/Azure
├── agents/                  Pure LLM logic (persona, context_selector, review, synthesis)
├── nodes/                   LangGraph wrappers (fetch_sha, fetch_tree, context, review, synthesis, aggregate, post)
├── graph/builder.py         Full graph wiring
├── services/
│   ├── github.py            GitHubService (PAT auth)
│   ├── github_app.py        GitHub App JWT auth
│   └── dependency/          Plugin-based resolver registry (Python + C/C++ + ROS2)
└── main.py                  CLI entry point + run_review_from_payload()

entrypoints/
└── webhook.py               FastAPI webhook handler

tests/
├── mock_input.json          Sample GitHub webhook payload
├── review_output.md         Output from last CLI run
├── unit/                    Unit tests per module
└── integration/             Full graph integration test
```

import asyncio
import hashlib
import hmac
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from functools import partial

from fastapi import FastAPI, Header, HTTPException, Request

from config.settings import settings
from main import run_review_from_payload
from services.github_app import get_installation_access_token

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

app = FastAPI(title="PR Review Bot Webhook")

REVIEW_TRIGGER_ACTIONS = {"opened", "reopened"}
_executor = ThreadPoolExecutor(max_workers=4)
_max_backlog: int = settings.max_webhook_backlog
_in_flight_lock = threading.Lock()
_in_flight: set[str] = set()


def _verify_signature(payload_body: bytes, signature_header: str) -> bool:
    """Verify the GitHub webhook HMAC-SHA256 signature."""
    if not settings.github_webhook_secret:
        raise HTTPException(status_code=500, detail="GITHUB_WEBHOOK_SECRET not configured")

    expected = (
        "sha256="
        + hmac.new(
            settings.github_webhook_secret.encode("utf-8"),
            payload_body,
            hashlib.sha256,
        ).hexdigest()
    )
    return hmac.compare_digest(expected, signature_header)


def _process_review(repo_name: str, owner: str, pr_number: int, installation_id: int | None) -> None:
    """Synchronous review execution for thread executor.

    The graph's post_review_node handles posting the review to GitHub,
    so we only need to invoke the graph here.
    """
    token = get_installation_access_token(installation_id) if installation_id else None

    run_review_from_payload(
        repo_name=repo_name,
        owner=owner,
        pr_number=pr_number,
        github_token=token,
    )

    logger.info("Finished review process.")


def _run_review_wrapped(
    key: str,
    repo_name: str,
    owner: str,
    pr_number: int,
    installation_id: int | None,
) -> None:
    """Run review and always release the in-flight slot."""
    try:
        _process_review(repo_name, owner, pr_number, installation_id)
    finally:
        with _in_flight_lock:
            _in_flight.discard(key)


@app.post("/webhook")
async def handle_webhook(
    request: Request,
    x_hub_signature_256: str = Header(default=""),
    x_github_event: str = Header(default=""),
) -> dict:
    """Handle incoming GitHub webhook events."""
    body = await request.body()

    logger.info(
        "Webhook request: event=%s signature=%s content_length=%d",
        x_github_event,
        "present" if x_hub_signature_256 else "missing",
        len(body),
    )

    # Verify webhook signature
    if settings.github_webhook_secret and not _verify_signature(body, x_hub_signature_256):
        logger.warning("Signature verification failed for event=%s", x_github_event)
        raise HTTPException(status_code=401, detail="Invalid signature")

    # Only handle pull_request events
    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"event '{x_github_event}' not handled"}

    payload = await request.json()
    action = payload.get("action", "")

    if action not in REVIEW_TRIGGER_ACTIONS:
        return {"status": "ignored", "reason": f"action '{action}' not handled"}

    pr = payload["pull_request"]
    repo = payload["repository"]
    installation_id = payload.get("installation", {}).get("id")

    repo_name = repo["name"]
    owner = repo["owner"]["login"]
    pr_number = pr["number"]

    # Reject fork PRs unless explicitly allowed
    base_repo = pr.get("base", {}).get("repo", {}).get("full_name")
    head_repo = pr.get("head", {}).get("repo", {}).get("full_name") if pr.get("head", {}).get("repo") else base_repo
    if base_repo and head_repo and head_repo != base_repo and not settings.review_forks:
        logger.info("Ignoring fork PR: %s → %s", head_repo, base_repo)
        return {"status": "ignored", "reason": "fork PR not reviewed"}

    logger.info("Webhook received: %s/%s#%d action=%s", owner, repo_name, pr_number, action)

    key = f"{owner}/{repo_name}#{pr_number}"

    with _in_flight_lock:
        if key in _in_flight:
            logger.info("Deduplicating review for %s", key)
            return {"status": "ignored", "reason": "review already in progress"}
        if len(_in_flight) >= _max_backlog:
            logger.warning(
                "Backlog full (%d/%d), rejecting %s",
                len(_in_flight),
                _max_backlog,
                key,
            )
            raise HTTPException(status_code=429, detail="Server busy, try again later")
        _in_flight.add(key)

    # Run review in background thread to avoid blocking the event loop
    loop = asyncio.get_running_loop()
    loop.run_in_executor(
        _executor,
        partial(_run_review_wrapped, key, repo_name, owner, pr_number, installation_id),
    )

    return {"status": "accepted", "repo": f"{owner}/{repo_name}", "pr": pr_number}


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}


def run_server() -> None:
    """Run the webhook server (callable from CLI)."""
    import uvicorn

    uvicorn.run(
        "entrypoints.webhook:app",
        host=settings.webhook_host,
        port=settings.webhook_port,
        reload=True,
    )


if __name__ == "__main__":
    run_server()

import hashlib
import hmac
import logging
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

_REVIEW_TRIGGER_ACTIONS = {"opened", "synchronize", "reopened"}
_executor = ThreadPoolExecutor(max_workers=4)


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

    if action not in _REVIEW_TRIGGER_ACTIONS:
        return {"status": "ignored", "reason": f"action '{action}' not handled"}

    pr = payload["pull_request"]
    repo = payload["repository"]
    installation_id = payload.get("installation", {}).get("id")

    repo_name = repo["name"]
    owner = repo["owner"]["login"]
    pr_number = pr["number"]

    logger.info("Webhook received: %s/%s#%d action=%s", owner, repo_name, pr_number, action)

    # Run review in background thread to avoid blocking the event loop
    loop = __import__("asyncio").get_event_loop()
    loop.run_in_executor(
        _executor,
        partial(_process_review, repo_name, owner, pr_number, installation_id),
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

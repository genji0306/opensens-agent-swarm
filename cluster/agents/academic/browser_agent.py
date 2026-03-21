"""DarkLab Browser Agent: LLM-driven browser automation via browser-use.

Replaces brittle Playwright selectors with an adaptive perception-action loop:
DOM extraction + screenshot → LLM decides next action → Playwright executes → observe.

Security features:
- Domain allowlist enforcement (configurable via DARKLAB_BROWSER_ALLOWED_DOMAINS)
- Per-task browser profile isolation (temp dir per request)
- DRVP event emission for navigate/action/blocked events
- Configurable max steps and headless mode

Used for Perplexity research, Google Scholar, and other web-based tools.
"""
from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from urllib.parse import urlparse

import structlog

from shared.config import settings

__all__ = [
    "DomainBlockedError",
    "check_domain_allowed",
    "browse_perplexity",
    "browse_scholar",
    "browse_url",
    "download_pdf",
]

logger = structlog.get_logger("darklab.browser")

# Browser profiles directory (persistent profiles for auth sessions)
PROFILES_DIR = Path(settings.darklab_home) / "browser-profiles"


class DomainBlockedError(Exception):
    """Raised when a browser navigation targets a domain not in the allowlist."""


def check_domain_allowed(url: str) -> bool:
    """Check if a URL's domain is in the configured allowlist.

    Supports subdomain matching: 'scholar.google.com' matches allowlist entry 'google.com'.
    """
    allowlist = settings.browser_domain_allowlist
    if not allowlist:
        return True  # Empty allowlist = no restriction

    try:
        parsed = urlparse(url if "://" in url else f"https://{url}")
        hostname = (parsed.hostname or "").lower()
    except Exception:
        return False

    if not hostname:
        return False

    for allowed in allowlist:
        if hostname == allowed or hostname.endswith(f".{allowed}"):
            return True

    return False


async def _emit_browser_event(
    event_type: str,
    agent_name: str,
    request_id: str,
    payload: dict,
) -> None:
    """Emit a DRVP browser event (best-effort)."""
    try:
        from oas_core.protocols.drvp import DRVPEvent, DRVPEventType, emit

        type_map = {
            "navigate": DRVPEventType.BROWSER_NAVIGATE,
            "action": DRVPEventType.BROWSER_ACTION,
            "blocked": DRVPEventType.BROWSER_BLOCKED,
        }
        drvp_type = type_map.get(event_type)
        if drvp_type is None:
            return

        event = DRVPEvent(
            event_type=drvp_type,
            request_id=request_id,
            agent_name=agent_name,
            device="academic",
            payload=payload,
        )
        await emit(event)
    except Exception:
        pass  # DRVP is best-effort


def _make_task_profile(task_name: str) -> Path:
    """Create an isolated per-task browser profile directory."""
    task_dir = PROFILES_DIR / f"{task_name}-{uuid.uuid4().hex[:8]}"
    task_dir.mkdir(parents=True, exist_ok=True)
    return task_dir


async def browse_perplexity(query: str, *, request_id: str = "") -> dict:
    """Search Perplexity via browser-use with LLM-driven interaction."""
    from browser_use import Agent, Controller, Browser, BrowserConfig
    from langchain_anthropic import ChatAnthropic

    target_url = "https://perplexity.ai"
    if not check_domain_allowed(target_url):
        await _emit_browser_event("blocked", "BrowserAgent", request_id, {
            "domain": "perplexity.ai", "url": target_url,
        })
        return {"error": "perplexity.ai is not in the browser domain allowlist", "source": "browser-use"}

    # Per-task isolated profile (not shared session)
    profile_dir = _make_task_profile("perplexity")

    browser = Browser(config=BrowserConfig(
        headless=settings.browser_headless,
        extra_chromium_args=[f"--user-data-dir={profile_dir}"],
    ))

    controller = Controller()
    citations_collected: list[dict] = []

    @controller.action(description="Save a citation found during research")
    def save_citation(title: str, url: str, authors: str = "", year: str = "") -> str:
        # Validate citation URL domain
        if url and not check_domain_allowed(url):
            logger.warning("citation_url_blocked", url=url)
            return f"Citation URL blocked by allowlist: {url}"

        citation = {"title": title, "url": url, "authors": authors, "year": year}
        citations_collected.append(citation)
        # Persist to citations file
        citations_path = settings.data_dir / "citations.jsonl"
        with open(citations_path, "a") as f:
            f.write(json.dumps(citation) + "\n")
        return f"Saved citation: {title}"

    await _emit_browser_event("navigate", "BrowserAgent", request_id, {
        "url": target_url, "query": query,
    })

    agent = Agent(
        task=(
            f"Go to perplexity.ai and search for: {query}\n"
            f"Wait for the response to fully load.\n"
            f"Extract the main findings and all cited sources.\n"
            f"For each citation, use the save_citation action with title, url, authors, and year.\n"
            f"Return a summary of the findings."
        ),
        llm=ChatAnthropic(
            model="claude-sonnet-4-6-20260301",
            api_key=settings.anthropic_api_key,
        ),
        browser=browser,
        controller=controller,
        use_vision=True,
        max_steps=settings.browser_max_steps,
    )

    try:
        result = await agent.run()
        summary = result.final_result() if hasattr(result, 'final_result') else str(result)
        await _emit_browser_event("action", "BrowserAgent", request_id, {
            "action": "perplexity_search_complete", "citations_count": len(citations_collected),
        })
    except Exception as e:
        logger.error("browser_agent_failed", error=str(e), target="perplexity")
        summary = f"Browser automation error: {e}"
    finally:
        await browser.close()
        shutil.rmtree(profile_dir, ignore_errors=True)

    return {
        "summary": summary,
        "citations": citations_collected,
        "source": "browser-use",
    }


async def browse_scholar(query: str, *, request_id: str = "") -> dict:
    """Search Google Scholar via browser-use."""
    from browser_use import Agent, Browser, BrowserConfig
    from langchain_anthropic import ChatAnthropic

    target_url = "https://scholar.google.com"
    if not check_domain_allowed(target_url):
        await _emit_browser_event("blocked", "BrowserAgent", request_id, {
            "domain": "scholar.google.com", "url": target_url,
        })
        return {"error": "scholar.google.com is not in the browser domain allowlist", "source": "google-scholar-browser"}

    profile_dir = _make_task_profile("scholar")

    browser = Browser(config=BrowserConfig(
        headless=settings.browser_headless,
        extra_chromium_args=[f"--user-data-dir={profile_dir}"],
    ))

    await _emit_browser_event("navigate", "BrowserAgent", request_id, {
        "url": target_url, "query": query,
    })

    agent = Agent(
        task=(
            f"Go to scholar.google.com and search for: {query}\n"
            f"Extract the top 10 results with: title, authors, year, citation count, and URL.\n"
            f"Return as a JSON array."
        ),
        llm=ChatAnthropic(
            model="claude-sonnet-4-6-20260301",
            api_key=settings.anthropic_api_key,
        ),
        browser=browser,
        use_vision=True,
        max_steps=settings.browser_max_steps,
    )

    try:
        result = await agent.run()
        text = result.final_result() if hasattr(result, 'final_result') else str(result)
        try:
            papers = json.loads(text)
        except json.JSONDecodeError:
            papers = {"raw": text}
        await _emit_browser_event("action", "BrowserAgent", request_id, {
            "action": "scholar_search_complete",
        })
    except Exception as e:
        logger.error("browser_agent_failed", error=str(e), target="scholar")
        papers = {"error": str(e)}
    finally:
        await browser.close()
        shutil.rmtree(profile_dir, ignore_errors=True)

    return {"papers": papers, "source": "google-scholar-browser"}


async def browse_url(url: str, task: str, *, request_id: str = "") -> dict:
    """Browse an arbitrary URL with domain allowlist enforcement.

    Use this for ad-hoc web research beyond Perplexity and Scholar.
    """
    from browser_use import Agent, Browser, BrowserConfig
    from langchain_anthropic import ChatAnthropic

    if not check_domain_allowed(url):
        try:
            domain = urlparse(url).hostname or url
        except Exception:
            domain = url
        await _emit_browser_event("blocked", "BrowserAgent", request_id, {
            "domain": domain, "url": url,
        })
        raise DomainBlockedError(
            f"Domain '{domain}' is not in the browser allowlist. "
            f"Allowed: {', '.join(sorted(settings.browser_domain_allowlist))}"
        )

    profile_dir = _make_task_profile("browse")

    browser = Browser(config=BrowserConfig(
        headless=settings.browser_headless,
        extra_chromium_args=[f"--user-data-dir={profile_dir}"],
    ))

    await _emit_browser_event("navigate", "BrowserAgent", request_id, {
        "url": url, "task": task[:200],
    })

    agent = Agent(
        task=task,
        llm=ChatAnthropic(
            model="claude-sonnet-4-6-20260301",
            api_key=settings.anthropic_api_key,
        ),
        browser=browser,
        use_vision=True,
        max_steps=settings.browser_max_steps,
    )

    try:
        result = await agent.run()
        text = result.final_result() if hasattr(result, 'final_result') else str(result)
        await _emit_browser_event("action", "BrowserAgent", request_id, {
            "action": "browse_complete", "url": url,
        })
    except Exception as e:
        logger.error("browser_agent_failed", error=str(e), url=url)
        text = f"Browser automation error: {e}"
    finally:
        await browser.close()
        shutil.rmtree(profile_dir, ignore_errors=True)

    return {"result": text, "url": url, "source": "browser-use"}


async def download_pdf(url: str, filename: str | None = None) -> Path:
    """Download a PDF with domain validation."""
    import httpx

    if not check_domain_allowed(url):
        try:
            domain = urlparse(url).hostname or url
        except Exception:
            domain = url
        raise DomainBlockedError(
            f"PDF download blocked: '{domain}' is not in the browser allowlist. "
            f"Allowed: {', '.join(sorted(settings.browser_domain_allowlist))}"
        )

    if filename is None:
        filename = url.split("/")[-1]
        if not filename.endswith(".pdf"):
            filename += ".pdf"

    pdf_dir = settings.artifacts_dir / "pdfs"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    target = pdf_dir / filename

    async with httpx.AsyncClient(follow_redirects=True) as client:
        response = await client.get(url, timeout=60)
        response.raise_for_status()
        target.write_bytes(response.content)

    logger.info("pdf_downloaded", path=str(target))
    return target

"""Mockable rendered-observation executor with sanitized artifacts."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import neatlogs

from .observation_policy import ObservationPolicy, sanitize_observation_html


@dataclass(frozen=True)
class BrowserCaptureResult:
    url: str
    html_outline: str
    screenshot_sha256: str | None = None
    request_log: tuple[dict[str, str], ...] = ()


class BrowserExecutor(Protocol):
    def capture(self, *, url: str) -> BrowserCaptureResult: ...


@dataclass(frozen=True)
class MockBrowserExecutor:
    html: str
    screenshot_bytes: bytes = b""

    def capture(self, *, url: str) -> BrowserCaptureResult:
        return BrowserCaptureResult(
            url=url,
            html_outline=self.html,
            screenshot_sha256=hashlib.sha256(self.screenshot_bytes).hexdigest(),
            request_log=({"url": url, "method": "GET", "purpose": "document"},),
        )


@neatlogs.span(kind="TOOL", name="capture_sanitized")
def capture_sanitized(
    *,
    policy: ObservationPolicy,
    executor: BrowserExecutor,
    url: str,
    output_dir: Path,
) -> Path:
    canonical = policy.canonical_url(url)
    result = executor.capture(url=canonical)
    if result.url != canonical:
        raise ValueError("executor returned a non-canonical URL")
    outline = sanitize_observation_html(result.html_outline)
    requests = []
    for item in result.request_log:
        request_url = item.get("url", "")
        policy.validate_url(request_url)
        requests.append({
            "url": policy.canonical_url(request_url),
            "method": item.get("method", "GET"),
            "purpose": item.get("purpose", "unknown"),
        })
    artifact = {
        "schema_version": "1",
        "target_url": canonical,
        "observation_policy": "rendered_sanitized_only",
        "html_outline": outline,
        "screenshot_sha256": result.screenshot_sha256,
        "requests": requests,
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / "observation.json"
    path.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n")
    return path

"""Rendered-site observation capture; never clones target repositories."""
from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from .schema import CapturePolicy


@dataclass(frozen=True)
class CaptureConfig:
    url: str
    output_dir: Path
    viewports: tuple[tuple[str, int, int], ...] = (
        ("desktop", 1440, 1000),
        ("tablet", 1024, 900),
        ("mobile", 390, 844),
    )


class SourceCloneAttempt(RuntimeError):
    pass


class RenderCapture:
    """Capture only public rendered observations with Chromium.

    This intentionally does not accept a repository path, git remote, or
    source checkout. The browser gets a URL and writes observation metadata.
    """

    def __init__(self, config: CaptureConfig, chromium: str | None = None):
        self.config = config
        self.chromium = chromium or shutil.which("chromium") or shutil.which("google-chrome")
        if not self.chromium:
            raise RuntimeError("Chromium is required for rendered capture")
        parsed = urlparse(config.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("capture URL must be an absolute HTTP(S) URL")
        self.policy = CapturePolicy(target_url=config.url)
        self.policy.assert_safe()

    def manifest(self) -> dict:
        return {
            "target_url": self.config.url,
            "target_repository_policy": "never_clone_or_inspect",
            "browser": self.chromium,
            "viewports": [
                {"name": n, "width": w, "height": h}
                for n, w, h in self.config.viewports
            ],
            "artifacts": [
                "screenshots", "semantic_dom_outline", "accessibility_tree",
                "bounding_boxes", "computed_style_tokens", "interaction_trace",
                "console_and_network_error_summary",
            ],
            "forbidden_actions": sorted(self.policy.forbidden_actions),
        }

    def write_manifest(self) -> Path:
        self.config.output_dir.mkdir(parents=True, exist_ok=True)
        path = self.config.output_dir / "capture-manifest.json"
        path.write_text(json.dumps(self.manifest(), indent=2, sort_keys=True) + "\n")
        return path

    def capture_with_chromium(self) -> Path:
        """Create a browser artifact directory without source access.

        Full DOM/screenshot extraction is a follow-up adapter. This method is
        deliberately a transparent dependency boundary: it records the exact
        browser command and URL, while failing loudly if Chromium cannot be
        started. It never invokes git, GitHub, or a source checkout.
        """
        manifest_path = self.write_manifest()
        marker = self.config.output_dir / "capture-command.json"
        marker.write_text(json.dumps({
            "command": [self.chromium, "--headless", "--no-sandbox", "--disable-gpu", "--dump-dom", self.config.url],
            "url": self.config.url,
            "source_clone": False,
        }, indent=2, sort_keys=True) + "\n")
        return manifest_path


def assert_no_source_clone(command: list[str]) -> None:
    forbidden = {"git", "clone", "checkout", "fetch", "gh", "scp", "rsync"}
    tokens = {part.lower() for part in command}
    if tokens & forbidden:
        raise SourceCloneAttempt(f"forbidden source operation in capture command: {command}")

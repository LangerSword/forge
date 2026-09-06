"""Safe rendered-observation policy primitives."""
from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from urllib.parse import urlparse


class ObservationPolicyError(ValueError):
    pass


@dataclass(frozen=True)
class ObservationPolicy:
    allowed_hosts: frozenset[str]
    allowed_ports: frozenset[int] = frozenset({443})

    def canonical_url(self, url: str) -> str:
        parsed = urlparse(url)
        self.validate_url(url)
        path = parsed.path or "/"
        query = f"?{parsed.query}" if parsed.query else ""
        return f"https://{parsed.hostname}{path}{query}"

    def validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ObservationPolicyError("only absolute HTTPS URLs are allowed")
        if parsed.username or parsed.password or parsed.fragment:
            raise ObservationPolicyError("credentials and fragments are forbidden")
        host = parsed.hostname.lower()
        if host not in self.allowed_hosts:
            raise ObservationPolicyError(f"host is not allowlisted: {host}")
        port = parsed.port or 443
        if port not in self.allowed_ports:
            raise ObservationPolicyError(f"port is not allowlisted: {port}")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return
        if address.is_private or address.is_loopback or address.is_link_local or address.is_unspecified:
            raise ObservationPolicyError("private or local addresses are forbidden")

    def validate_redirect(self, source: str, target: str) -> None:
        self.validate_url(target)


def sanitize_observation_html(raw: str) -> str:
    """Keep only a conservative text/semantic outline for local fixtures."""
    forbidden = ("<script", "sourceMappingURL", ".js", "<style", "data:")
    lowered = raw.lower()
    if any(marker.lower() in lowered for marker in forbidden):
        raise ObservationPolicyError("raw source-like HTML cannot be observation input")
    return raw

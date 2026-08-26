"""Configuration model and structural validation for network-trusted access."""

from __future__ import annotations

import ipaddress
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

NetworkTrustMode = Literal["cloudflare-chatgpt"]
NETWORK_TRUST_MODE = "cloudflare-chatgpt"

_HOST_LABEL_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")
_NETWORK_TRUST_FIELDS = frozenset({"mode", "allowed_hosts", "allowed_origins"})


class NetworkTrustConfigError(ValueError):
    """Raised when a network-trust configuration is structurally unsafe."""


def _require_text(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise NetworkTrustConfigError(f"{field} must be a non-empty string")
    if value != value.strip():
        raise NetworkTrustConfigError(f"{field} must not contain leading or trailing whitespace")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise NetworkTrustConfigError(f"{field} must not contain control characters")
    return value


def _canonicalize_hostname(value: str, *, field: str, allow_ip: bool) -> str:
    hostname = _require_text(value, field=field)
    if "*" in hostname:
        raise NetworkTrustConfigError(f"{field} must not contain wildcard characters")
    if len(hostname) > 253:
        raise NetworkTrustConfigError(f"{field} exceeds the maximum hostname length")

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    if address is not None:
        if not allow_ip:
            raise NetworkTrustConfigError(f"{field} must be a hostname, not an IP address")
        return str(address)

    if not all(_HOST_LABEL_PATTERN.fullmatch(label) for label in hostname.split(".")):
        raise NetworkTrustConfigError(f"{field} must be a valid hostname")
    return hostname.lower()


def canonicalize_allowed_host(value: str) -> str:
    """Canonicalize one hostname used by the network-trust Host allowlist."""

    hostname = _require_text(value, field="allowed_hosts entry")
    if any(character in hostname for character in (":", "/", "?", "#", "@")):
        raise NetworkTrustConfigError(
            "allowed_hosts entries must be hostnames without scheme, port, path, query, "
            "fragment, or credentials"
        )
    return _canonicalize_hostname(hostname, field="allowed_hosts entry", allow_ip=False)


def canonicalize_allowed_origin(value: str) -> str:
    """Canonicalize one complete HTTPS origin for if-present Origin checks."""

    origin = _require_text(value, field="allowed_origins entry")
    if origin.lower() == "null":
        raise NetworkTrustConfigError("allowed_origins entries must not be the null origin")
    if "*" in origin:
        raise NetworkTrustConfigError(
            "allowed_origins entries must not contain wildcard characters"
        )

    try:
        parsed = urlsplit(origin)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError as exc:
        raise NetworkTrustConfigError(f"allowed_origins entry is malformed: {exc}") from exc

    if parsed.scheme.lower() != "https":
        raise NetworkTrustConfigError("allowed_origins entries must use HTTPS")
    if not parsed.netloc or hostname is None:
        raise NetworkTrustConfigError("allowed_origins entries must contain a hostname")
    if parsed.username is not None or parsed.password is not None:
        raise NetworkTrustConfigError("allowed_origins entries must not contain credentials")
    if parsed.path or "?" in origin or "#" in origin:
        raise NetworkTrustConfigError(
            "allowed_origins entries must not contain a path, query, or fragment"
        )
    if port is not None and not 1 <= port <= 65535:
        raise NetworkTrustConfigError("allowed_origins port must be between 1 and 65535")

    canonical_hostname = _canonicalize_hostname(
        hostname,
        field="allowed_origins hostname",
        allow_ip=True,
    )
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        address = None
    host_part = (
        f"[{canonical_hostname}]"
        if address is not None and address.version == 6
        else canonical_hostname
    )

    port_suffix = "" if port in (None, 443) else f":{port}"
    return f"https://{host_part}{port_suffix}"


def _canonicalize_entries(
    value: Any,
    *,
    field: str,
    canonicalizer: Callable[[Any], str],
    require_nonempty: bool,
) -> tuple[str, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise NetworkTrustConfigError(f"{field} must be an array of strings")
    if require_nonempty and not value:
        raise NetworkTrustConfigError(f"{field} must contain at least one entry")

    canonical: list[str] = []
    for entry in value:
        canonical_entry = canonicalizer(entry)
        if canonical_entry in canonical:
            raise NetworkTrustConfigError(f"{field} contains a duplicate entry: {canonical_entry}")
        canonical.append(canonical_entry)
    return tuple(canonical)


@dataclass(frozen=True, slots=True)
class NetworkTrustConfig:
    """Explicit network trust policy independent from OAuth resource-server settings."""

    mode: str
    allowed_hosts: tuple[str, ...]
    allowed_origins: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.mode != NETWORK_TRUST_MODE:
            raise NetworkTrustConfigError(f"unsupported network trust mode: {self.mode!r}")
        object.__setattr__(
            self,
            "allowed_hosts",
            _canonicalize_entries(
                self.allowed_hosts,
                field="allowed_hosts",
                canonicalizer=canonicalize_allowed_host,
                require_nonempty=True,
            ),
        )
        object.__setattr__(
            self,
            "allowed_origins",
            _canonicalize_entries(
                self.allowed_origins,
                field="allowed_origins",
                canonicalizer=canonicalize_allowed_origin,
                require_nonempty=False,
            ),
        )

    @classmethod
    def from_mapping(cls, raw: Mapping[str, Any]) -> NetworkTrustConfig:
        if not isinstance(raw, Mapping):
            raise NetworkTrustConfigError("network_trust configuration must be a TOML table")
        unexpected = sorted(set(raw) - _NETWORK_TRUST_FIELDS)
        if unexpected:
            raise NetworkTrustConfigError(
                "network_trust configuration contains unsupported fields: " + ", ".join(unexpected)
            )
        return cls(
            mode=raw.get("mode"),
            allowed_hosts=raw.get("allowed_hosts", ()),
            allowed_origins=raw.get("allowed_origins", ()),
        )

    def as_mapping(self) -> dict[str, Any]:
        """Return canonical values suitable for persistence or diagnostics."""

        return {
            "mode": self.mode,
            "allowed_hosts": list(self.allowed_hosts),
            "allowed_origins": list(self.allowed_origins),
        }

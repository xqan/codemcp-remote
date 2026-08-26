"""OAuth Resource Server verification for protected MCP requests."""

from __future__ import annotations

import base64
import contextvars
import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit

import anyio
from starlette.types import Scope, Send

CONTRACT_VERSION = "1"
CONTRACT_ID = "mcp-rs-verification-v1"
VALIDATION_PATH = "/mcp/resource-server/validate"
AUTH_SCOPE_KEY = "codemcp.auth.principal"
MAX_VALIDATION_RESPONSE_BYTES = 64 * 1024
PROTECTED_RESOURCE_METADATA_PATH = "/.well-known/oauth-protected-resource"


class ResourceAuthError(RuntimeError):
    """Base class for expected OAuth Resource Server failures."""


class InvalidBearerCredential(ResourceAuthError):
    """The caller bearer credential is missing, malformed, or inactive."""


class VerificationServiceUnavailable(ResourceAuthError):
    """The frozen online validation contract could not be completed safely."""


@dataclass(frozen=True, slots=True)
class ResourceServerValidationConfig:
    """Frozen Resource Server Verification Contract v1 consumer configuration."""

    issuer: str
    resource: str
    validation_resource_id: str
    validation_secret: str = field(repr=False)
    timeout_seconds: float = 2.0
    contract_version: str = CONTRACT_VERSION

    def __post_init__(self) -> None:
        _validate_issuer(self.issuer)
        _validate_resource(self.resource)
        if (
            not self.validation_resource_id
            or ":" in self.validation_resource_id
            or any(ord(character) < 0x20 for character in self.validation_resource_id)
        ):
            raise ValueError("validation_resource_id must be a non-empty Basic-auth username without ':'")
        if not self.validation_secret or any(
            ord(character) < 0x20 for character in self.validation_secret
        ):
            raise ValueError("validation_secret must be a non-empty value without control characters")
        if self.timeout_seconds != 2.0:
            raise ValueError("Resource Server Verification Contract v1 requires a 2 second timeout")
        if self.contract_version != CONTRACT_VERSION:
            raise ValueError("unsupported Resource Server verification contract version")

    @property
    def validation_endpoint(self) -> str:
        return f"{self.issuer}{VALIDATION_PATH}"

    @property
    def protected_resource_metadata_url(self) -> str:
        return protected_resource_metadata_url(self.resource)

    @property
    def protected_resource_metadata_path(self) -> str:
        return urlsplit(self.protected_resource_metadata_url).path

    def protected_resource_metadata(self) -> dict[str, Any]:
        return {
            "resource": self.resource,
            "authorization_servers": [self.issuer],
            "bearer_methods_supported": ["header"],
        }


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    """Stable v1 identity projection returned by the Authorization Server."""

    contract_version: str
    issuer: str
    resource: str
    subject: str
    client_id: str
    scopes: tuple[str, ...]
    issued_at: int
    expires_at: int


@dataclass(frozen=True, slots=True)
class ValidationHTTPResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes


class ValidationRequester(Protocol):
    def __call__(
        self,
        *,
        endpoint: str,
        resource_id: str,
        verification_secret: str,
        token: str,
        resource: str,
        timeout_seconds: float,
    ) -> ValidationHTTPResponse: ...


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return None


def _validate_issuer(value: str) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or value.endswith("/")
    ):
        raise ValueError("authorization_server_issuer must be a canonical HTTPS origin without a trailing slash")


def _validate_resource(value: str) -> None:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or not parsed.path.startswith("/")
        or parsed.query
        or parsed.fragment
        or not value.isascii()
        or any(ord(character) < 0x21 or ord(character) == 0x7F for character in value)
        or '"' in value
        or "\\" in value
    ):
        raise ValueError(
            "canonical_resource_uri must be an absolute HTTPS URI without query or fragment"
        )


def protected_resource_metadata_url(resource: str) -> str:
    """Derive the RFC 9728 path-specific metadata URL for a resource URI."""

    _validate_resource(resource)
    parsed = urlsplit(resource)
    resource_path = "" if parsed.path == "/" else parsed.path
    metadata_path = f"{PROTECTED_RESOURCE_METADATA_PATH}{resource_path}"
    return urlunsplit((parsed.scheme, parsed.netloc, metadata_path, "", ""))


def _default_requester(
    *,
    endpoint: str,
    resource_id: str,
    verification_secret: str,
    token: str,
    resource: str,
    timeout_seconds: float,
) -> ValidationHTTPResponse:
    credentials = base64.b64encode(
        f"{resource_id}:{verification_secret}".encode("utf-8")
    ).decode("ascii")
    body = json.dumps(
        {"token": token, "resource": resource},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode("utf-8")
    request = urllib.request.Request(
        endpoint,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    opener = urllib.request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(request, timeout=timeout_seconds) as response:
            payload = response.read(MAX_VALIDATION_RESPONSE_BYTES + 1)
            if len(payload) > MAX_VALIDATION_RESPONSE_BYTES:
                raise VerificationServiceUnavailable("validation response exceeded the size limit")
            return ValidationHTTPResponse(
                status_code=int(response.status),
                headers={key.lower(): value for key, value in response.headers.items()},
                body=payload,
            )
    except VerificationServiceUnavailable:
        raise
    except urllib.error.HTTPError as exc:
        # HTTP failures are infrastructure/protocol failures, not bearer verdicts.
        raise VerificationServiceUnavailable("validation service returned a non-200 response") from exc
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        raise VerificationServiceUnavailable("validation service is unavailable") from exc


class OnlineResourceServerValidator:
    """Validate opaque bearer credentials through the frozen v1 online contract."""

    def __init__(
        self,
        config: ResourceServerValidationConfig,
        *,
        requester: ValidationRequester | None = None,
    ) -> None:
        self.config = config
        self._requester = requester or _default_requester

    async def validate(self, token: str) -> AuthenticatedPrincipal | None:
        if not token:
            raise InvalidBearerCredential("bearer credential is empty")
        try:
            with anyio.fail_after(self.config.timeout_seconds):
                response = await anyio.to_thread.run_sync(
                    lambda: self._requester(
                        endpoint=self.config.validation_endpoint,
                        resource_id=self.config.validation_resource_id,
                        verification_secret=self.config.validation_secret,
                        token=token,
                        resource=self.config.resource,
                        timeout_seconds=self.config.timeout_seconds,
                    ),
                    abandon_on_cancel=True,
                )
        except VerificationServiceUnavailable:
            raise
        except Exception as exc:
            raise VerificationServiceUnavailable("validation service is unavailable") from exc
        return self._validate_response(response)

    def _validate_response(
        self,
        response: ValidationHTTPResponse,
    ) -> AuthenticatedPrincipal | None:
        if response.status_code != 200:
            raise VerificationServiceUnavailable("validation service returned a non-200 response")
        content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
        if content_type != "application/json":
            raise VerificationServiceUnavailable("validation service returned an unexpected content type")
        cache_control = response.headers.get("cache-control", "")
        directives = {item.strip().lower() for item in cache_control.split(",") if item.strip()}
        if "no-store" not in directives:
            raise VerificationServiceUnavailable("validation response is missing Cache-Control: no-store")
        try:
            payload = json.loads(response.body)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise VerificationServiceUnavailable("validation service returned malformed JSON") from exc
        if not isinstance(payload, dict):
            raise VerificationServiceUnavailable("validation response must be a JSON object")
        if payload.get("contract_version") != CONTRACT_VERSION:
            raise VerificationServiceUnavailable("validation response contract version is unsupported")
        active = payload.get("active")
        if not isinstance(active, bool):
            raise VerificationServiceUnavailable("validation response active field is invalid")
        if not active:
            return None

        issuer = payload.get("issuer")
        resource = payload.get("resource")
        subject = payload.get("subject")
        client_id = payload.get("client_id")
        scopes = payload.get("scopes")
        issued_at = payload.get("issued_at")
        expires_at = payload.get("expires_at")
        if issuer != self.config.issuer or resource != self.config.resource:
            raise VerificationServiceUnavailable("validation response identity does not match local configuration")
        if not isinstance(subject, str) or not subject:
            raise VerificationServiceUnavailable("validation response subject is invalid")
        if not isinstance(client_id, str) or not client_id:
            raise VerificationServiceUnavailable("validation response client_id is invalid")
        if (
            not isinstance(scopes, list)
            or not all(isinstance(scope, str) and scope for scope in scopes)
            or len(set(scopes)) != len(scopes)
        ):
            raise VerificationServiceUnavailable("validation response scopes are invalid")
        if (
            isinstance(issued_at, bool)
            or not isinstance(issued_at, int)
            or isinstance(expires_at, bool)
            or not isinstance(expires_at, int)
        ):
            raise VerificationServiceUnavailable("validation response token timestamps are invalid")
        if expires_at <= int(time.time()):
            raise VerificationServiceUnavailable("validation response token is already expired")
        return AuthenticatedPrincipal(
            contract_version=CONTRACT_VERSION,
            issuer=issuer,
            resource=resource,
            subject=subject,
            client_id=client_id,
            scopes=tuple(scopes),
            issued_at=issued_at,
            expires_at=expires_at,
        )


_current_principal: contextvars.ContextVar[AuthenticatedPrincipal | None] = contextvars.ContextVar(
    "codemcp_authenticated_principal",
    default=None,
)


def bind_auth_context(
    principal: AuthenticatedPrincipal,
) -> contextvars.Token[AuthenticatedPrincipal | None]:
    return _current_principal.set(principal)


def reset_auth_context(token: contextvars.Token[AuthenticatedPrincipal | None]) -> None:
    _current_principal.reset(token)


def current_auth_context() -> AuthenticatedPrincipal | None:
    return _current_principal.get()


def auth_audit_details(principal: AuthenticatedPrincipal) -> dict[str, Any]:
    return {
        "contract_version": principal.contract_version,
        "issuer": principal.issuer,
        "resource": principal.resource,
        "subject": principal.subject,
        "client_id": principal.client_id,
        "scopes": list(principal.scopes),
        "issued_at": principal.issued_at,
        "expires_at": principal.expires_at,
    }


class OAuthResourceServerAuthenticator:
    """Authenticate one MCP ASGI request before the MCP transport sees it."""

    def __init__(self, validator: OnlineResourceServerValidator):
        self.validator = validator

    @property
    def protected_resource_metadata_path(self) -> str:
        return self.validator.config.protected_resource_metadata_path

    def protected_resource_metadata(self) -> dict[str, Any]:
        return self.validator.config.protected_resource_metadata()

    async def __call__(self, scope: Scope, send: Send) -> bool:
        token = _extract_bearer(scope)
        if token is None:
            await self._send_auth_response(send, status_code=401, challenge=True)
            return False
        try:
            principal = await self.validator.validate(token)
        except InvalidBearerCredential:
            await self._send_auth_response(send, status_code=401, challenge=True)
            return False
        except VerificationServiceUnavailable:
            await self._send_auth_response(send, status_code=503, challenge=False)
            return False
        if principal is None:
            await self._send_auth_response(send, status_code=401, challenge=True)
            return False
        scope[AUTH_SCOPE_KEY] = principal
        return True

    async def _send_auth_response(
        self,
        send: Send,
        *,
        status_code: int,
        challenge: bool,
    ) -> None:
        challenge_value = None
        if challenge:
            metadata_url = self.validator.config.protected_resource_metadata_url
            challenge_value = f'Bearer resource_metadata="{metadata_url}"'
        await _send_auth_response(
            send,
            status_code=status_code,
            challenge=challenge_value,
        )


def _extract_bearer(scope: Scope) -> str | None:
    authorization_values = [
        value.decode("latin-1")
        for name, value in scope.get("headers", [])
        if name.decode("latin-1").lower() == "authorization"
    ]
    if len(authorization_values) != 1:
        return None
    value = authorization_values[0]
    scheme, separator, token = value.partition(" ")
    if separator != " " or scheme.lower() != "bearer" or not token or token.strip() != token:
        return None
    if any(ord(character) < 0x21 or ord(character) == 0x7F for character in token):
        return None
    return token


async def _send_auth_response(
    send: Send,
    *,
    status_code: int,
    challenge: str | None,
) -> None:
    if status_code == 401:
        body = b'{"error":"unauthorized"}'
    else:
        body = b'{"error":"authorization_service_unavailable"}'
    headers: list[tuple[bytes, bytes]] = [
        (b"content-type", b"application/json"),
        (b"cache-control", b"no-store"),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    if challenge is not None:
        headers.append((b"www-authenticate", challenge.encode("ascii")))
    await send({"type": "http.response.start", "status": status_code, "headers": headers})
    await send({"type": "http.response.body", "body": body})

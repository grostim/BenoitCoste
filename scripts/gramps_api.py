"""Small credential-isolated GrampsWeb HTTP client for local generation.

This module intentionally uses only the Python standard library. It never
prints credentials, response bodies, or authorization headers. It is not used
by the public CI path.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


class GrampsApiError(RuntimeError):
    """A bounded, non-sensitive API error."""


class MissingCredentials(GrampsApiError):
    """Required local credentials are unavailable."""


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def external_credentials(env_file: Path | None = None) -> dict[str, str]:
    """Read credentials from the process environment or an external env file.

    The default file is deliberately outside this repository. Passing a file
    inside the repository is refused, including under ``genealogie/private``;
    raw credentials must not become part of a source checkout.
    """
    values = {
        key: value
        for key, value in os.environ.items()
        if key in {"GRAMPSWEB_API_URL", "GRAMPSWEB_API_USER", "GRAMPSWEB_API_PASS"}
    }
    selected = env_file
    if selected is None:
        configured = os.environ.get("GRAMPSWEB_ENV_FILE")
        selected = Path(configured) if configured else Path("/home/sorg/CloudCLI/Homelab/.env")
    selected = selected.expanduser().resolve()
    repo_root = Path(__file__).resolve().parents[1]
    try:
        selected.relative_to(repo_root)
    except ValueError:
        pass
    else:
        raise MissingCredentials("credential file must be outside the repository")
    for key, value in _parse_env_file(selected).items():
        if key.startswith("GRAMPSWEB_API_") and key not in values:
            values[key] = value
    required = ("GRAMPSWEB_API_URL", "GRAMPSWEB_API_USER", "GRAMPSWEB_API_PASS")
    missing = [key for key in required if not values.get(key)]
    if missing:
        raise MissingCredentials("missing external GrampsWeb environment keys: " + ", ".join(missing))
    return {key: values[key] for key in required}


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _join(base: str, path: str) -> str:
    if path.startswith("http://") or path.startswith("https://"):
        return path
    return base.rstrip("/") + "/" + path.lstrip("/")


def _task_href(base: str, href: str) -> str:
    """Join API-relative Celery hrefs, including ``/api/...`` hrefs."""
    if href.startswith("http://") or href.startswith("https://"):
        return href
    base = base.rstrip("/")
    if href.startswith("/api/") and base.endswith("/api"):
        return base[:-4] + href
    return _join(base, href)


class GrampsApiClient:
    """JWT client with small JSON helpers and bounded retries."""

    def __init__(self, base_url: str, username: str, password: str, *, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.username = username
        self._password = password
        self.timeout = timeout
        self._token: str | None = None

    def _login(self) -> None:
        payload = _json_bytes({"username": self.username, "password": self._password})
        basic = base64.b64encode(f"{self.username}:{self._password}".encode()).decode("ascii")
        request = Request(
            _join(self.base_url, "/token/"),
            data=payload,
            method="POST",
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "Authorization": f"Basic {basic}",
            },
        )
        for attempt in range(5):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    data = json.loads(response.read().decode("utf-8"))
                self._token = data["access_token"]
                return
            except HTTPError as error:
                if error.code == 429 and attempt < 4:
                    time.sleep(5)
                    continue
                raise GrampsApiError(f"login failed HTTP {error.code}") from None
            except (URLError, TimeoutError, KeyError, json.JSONDecodeError) as error:
                raise GrampsApiError("login failed before a token was issued") from error
        raise GrampsApiError("login failed after repeated rate limits")

    def _request(
        self,
        method: str,
        path: str,
        *,
        payload: Any | None = None,
        query: dict[str, str | int] | None = None,
        accept: str = "application/json",
    ) -> tuple[bytes, str]:
        if self._token is None:
            self._login()
        url = _join(self.base_url, path)
        if query:
            url += ("&" if "?" in url else "?") + urlencode(query)
        body = _json_bytes(payload) if payload is not None else None
        headers = {"Accept": accept, "Authorization": f"Bearer {self._token}"}
        if payload is not None:
            headers["Content-Type"] = "application/json"
        request = Request(url, data=body, method=method, headers=headers)
        try:
            with urlopen(request, timeout=self.timeout) as response:
                return response.read(), response.headers.get("Content-Type", "")
        except HTTPError as error:
            if error.code == 401 and self._token is not None:
                self._token = None
                return self._request(method, path, payload=payload, query=query, accept=accept)
            raise GrampsApiError(f"{method} {path} failed HTTP {error.code}") from None
        except (URLError, TimeoutError) as error:
            raise GrampsApiError(f"{method} {path} failed before a response") from error

    def get_json(self, path: str, *, query: dict[str, str | int] | None = None) -> Any:
        data, _content_type = self._request("GET", path, query=query)
        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GrampsApiError(f"GET {path} did not return JSON") from error

    def post_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        query: dict[str, str | int] | None = None,
    ) -> Any:
        data, _content_type = self._request("POST", path, payload=payload, query=query)
        if not data:
            return None
        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GrampsApiError(f"POST {path} did not return JSON") from error

    def put_json(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        query: dict[str, int | str] | None = None,
    ) -> Any:
        data, _content_type = self._request("PUT", path, payload=payload, query=query)
        if not data:
            return None
        try:
            return json.loads(data.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GrampsApiError(f"PUT {path} did not return JSON") from error

    def download(self, href: str) -> bytes:
        data, _content_type = self._request("GET", _task_href(self.base_url, href), accept="*/*")
        return data

    def list_collection(self, collection: str, *, page_size: int = 500, max_pages: int = 200) -> list[dict[str, Any]]:
        """Read a bounded paginated collection without printing its contents."""
        result: list[dict[str, Any]] = []
        for page in range(1, max_pages + 1):
            payload = self.get_json(
                f"/{collection.strip('/')}/",
                query={"page": page, "pagesize": page_size},
            )
            if isinstance(payload, list):
                rows = payload
            elif isinstance(payload, dict):
                rows = next(
                    (payload[key] for key in (collection.strip("/"), "items", "results") if isinstance(payload.get(key), list)),
                    [],
                )
            else:
                raise GrampsApiError(f"unexpected {collection} collection shape")
            result.extend(row for row in rows if isinstance(row, dict))
            if len(rows) < page_size:
                break
        return result


def client_from_external_env(env_file: Path | None = None, *, timeout: int = 60) -> GrampsApiClient:
    values = external_credentials(env_file)
    return GrampsApiClient(
        values["GRAMPSWEB_API_URL"],
        values["GRAMPSWEB_API_USER"],
        values["GRAMPSWEB_API_PASS"],
        timeout=timeout,
    )


__all__ = [
    "GrampsApiError",
    "GrampsApiClient",
    "MissingCredentials",
    "client_from_external_env",
    "external_credentials",
    "_task_href",
]

"""
HTTP client for API Gateway (ingest, dashboard data, settings).

Uses ``requests`` with timeouts, retries on connection errors / selected status codes,
and structured logging.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import Config

logger = logging.getLogger("smart_env_monitor.cloud.client")


class CloudClientError(Exception):
    """
    Raised when a cloud API call fails.

    Carries structured fields so Flask can return JSON (not opaque ``Not Found`` text).
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        error_code: Optional[str] = None,
        url: Optional[str] = None,
        response_body: Optional[str] = None,
        parsed_body: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.url = url
        self.response_body = response_body
        self.parsed_body = parsed_body

    def to_flask_extra(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {}
        if self.error_code:
            out["error_code"] = self.error_code
        if self.status_code is not None:
            out["upstream_http_status"] = self.status_code
        if self.url:
            out["upstream_url"] = self.url
        if self.response_body:
            out["upstream_body_preview"] = self.response_body[:500]
        if self.parsed_body:
            out["upstream_json"] = self.parsed_body
        return out


def _session(timeout: float, total_retries: int, backoff: float) -> requests.Session:
    retry = Retry(
        total=total_retries,
        connect=total_retries,
        read=total_retries,
        status=total_retries,
        backoff_factor=backoff,
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=frozenset(["GET", "POST", "PUT"]),
        raise_on_status=False,
    )
    adapter = HTTPAdapter(max_retries=retry)
    sess = requests.Session()
    sess.mount("https://", adapter)
    sess.mount("http://", adapter)
    sess.headers.update({"Accept": "application/json", "User-Agent": "smart-env-monitor/2.0"})
    return sess


def _normalize_base(url: str) -> str:
    return (url or "").strip().rstrip("/")


def resolve_settings_urls(cfg: type) -> List[str]:
    """
    Candidate URLs for /settings (first match wins on non-404 after trying in order).

    Order:
    1. ``AWS_SETTINGS_URL`` if set and non-empty
    2. ``{AWS_API_BASE}/settings`` (and ``.../settings/`` stripped)
    """
    seen: set[str] = set()
    out: List[str] = []

    def add(u: str) -> None:
        u = (u or "").strip()
        if not u or u in seen:
            return
        seen.add(u)
        out.append(u.rstrip("/"))

    explicit = getattr(cfg, "AWS_SETTINGS_URL", None)
    if explicit:
        add(str(explicit))

    base = _normalize_base(str(getattr(cfg, "AWS_API_BASE", "") or ""))
    if base:
        add(urljoin(base + "/", "settings"))

    return out


def _parse_error_response(resp: requests.Response) -> tuple[Optional[Dict[str, Any]], str]:
    text = (resp.text or "").strip()
    try:
        j = resp.json()
        if isinstance(j, dict):
            return j, text
    except ValueError:
        pass
    return None, text


def _settings_route_not_found_error(url: str, raw: str, parsed: Optional[Dict[str, Any]], verb: str) -> CloudClientError:
    return CloudClientError(
        f"AWS returned 404 for {verb} /settings: the route is not deployed on this API Gateway, "
        "or AWS_SETTINGS_URL is wrong. Add GET and POST routes for `/settings` pointing to "
        "`settings_handler.lambda_handler` (see infrastructure/httpapi-settings-routes.yaml).",
        status_code=404,
        error_code="AWS_SETTINGS_ROUTE_NOT_FOUND",
        url=url,
        response_body=raw,
        parsed_body=parsed,
    )


def _raise_settings_http_error(url: str, resp: requests.Response, http_verb: str) -> None:
    parsed, raw = _parse_error_response(resp)
    msg = raw or f"HTTP {resp.status_code}"
    if parsed:
        msg = str(parsed.get("message") or parsed.get("error") or msg)

    if resp.status_code == 404:
        raise _settings_route_not_found_error(url, raw, parsed, http_verb)

    if resp.status_code == 403:
        raise CloudClientError(
            "AWS returned 403 Forbidden for the settings URL (check IAM / API auth).",
            status_code=403,
            error_code="AWS_SETTINGS_FORBIDDEN",
            url=url,
            response_body=raw,
            parsed_body=parsed,
        )

    raise CloudClientError(
        msg,
        status_code=resp.status_code,
        error_code="AWS_SETTINGS_HTTP_ERROR",
        url=url,
        response_body=raw,
        parsed_body=parsed,
    )


class CloudAPIClient:
    """Thin service layer over AWS HTTP API endpoints."""

    def __init__(self, config_class: type = Config):
        self._cfg = config_class
        self._session = _session(
            timeout=config_class.HTTP_TIMEOUT_SECONDS,
            total_retries=max(0, int(config_class.HTTP_MAX_RETRIES)),
            backoff=float(config_class.HTTP_RETRY_BACKOFF),
        )

    def _timeout_tuple(self) -> tuple[float, float]:
        t = float(self._cfg.HTTP_TIMEOUT_SECONDS)
        return (t, t)

    def fetch_dashboard_data(
        self,
        device_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """
        GET /data — returns ``sensor_data`` list and ``settings`` dict.

        Raises CloudClientError on failure.
        """
        params = {}
        if device_id:
            params["device_id"] = device_id
        url = self._cfg.AWS_DATA_URL
        to = timeout if timeout is not None else float(self._cfg.DASHBOARD_CLOUD_TIMEOUT)
        try:
            resp = self._session.get(url, params=params or None, timeout=(to, to))
        except requests.RequestException as exc:
            logger.warning("Cloud GET /data failed: %s", exc)
            raise CloudClientError(str(exc), error_code="DATA_TRANSPORT_ERROR", url=url) from exc

        if not resp.ok:
            logger.warning("Cloud GET /data HTTP %s: %s", resp.status_code, resp.text[:500])
            raise CloudClientError(
                f"GET /data failed with HTTP {resp.status_code}",
                status_code=resp.status_code,
                error_code="DATA_HTTP_ERROR",
                url=url,
                response_body=resp.text,
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise CloudClientError("Invalid JSON from /data", error_code="DATA_JSON_ERROR", url=url) from exc

        if not isinstance(data, dict):
            raise CloudClientError("Unexpected /data payload shape", error_code="DATA_SHAPE_ERROR", url=url)
        return data

    def post_sensor_reading(self, payload: Dict[str, Any]) -> bool:
        """
        POST /ingest with JSON body. Returns True on 2xx.

        Does not raise on network errors — returns False after retries exhausted
        (urllib3 retry) or on HTTP error.
        """
        url = self._cfg.AWS_INGEST_URL
        if not url:
            logger.error("AWS_INGEST_URL is empty; cannot upload.")
            return False
        try:
            resp = self._session.post(
                url,
                json=payload,
                timeout=self._timeout_tuple(),
                headers={"Content-Type": "application/json"},
            )
        except requests.RequestException as exc:
            logger.warning("Cloud POST /ingest failed: %s", exc)
            return False

        if 200 <= resp.status_code < 300:
            return True
        logger.warning("Ingest rejected: HTTP %s %s", resp.status_code, resp.text[:300])
        return False

    def get_settings(self) -> Dict[str, Any]:
        """
        GET /settings — returns JSON from AWS (expects ``success`` and ``settings``).

        Tries each URL from :func:`resolve_settings_urls` until one does not return 404.
        """
        urls = resolve_settings_urls(self._cfg)
        if not urls:
            raise CloudClientError(
                "No settings URL could be built. Set AWS_SETTINGS_URL or AWS_API_BASE.",
                error_code="SETTINGS_URL_UNCONFIGURED",
            )

        last_exc: Optional[CloudClientError] = None
        for url in urls:
            try:
                resp = self._session.get(url, timeout=self._timeout_tuple())
            except requests.RequestException as exc:
                last_exc = CloudClientError(
                    str(exc),
                    error_code="SETTINGS_TRANSPORT_ERROR",
                    url=url,
                )
                logger.warning("GET %s failed: %s", url, exc)
                continue

            if resp.status_code == 404:
                logger.info("GET settings 404 at %s, trying next candidate.", url)
                parsed, raw = _parse_error_response(resp)
                last_exc = _settings_route_not_found_error(url, raw, parsed, "GET")
                continue

            if not resp.ok:
                _raise_settings_http_error(url, resp, "GET")

            try:
                body = resp.json()
            except ValueError as exc:
                raise CloudClientError(
                    "Invalid JSON from GET /settings",
                    status_code=resp.status_code,
                    error_code="SETTINGS_JSON_ERROR",
                    url=url,
                    response_body=resp.text,
                ) from exc

            if isinstance(body, dict):
                return body
            raise CloudClientError("Unexpected GET /settings payload", error_code="SETTINGS_SHAPE_ERROR", url=url)

        if last_exc:
            raise last_exc
        raise CloudClientError("GET /settings failed", error_code="SETTINGS_UNKNOWN_ERROR")

    def post_settings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        POST thresholds to cloud. Tries each candidate URL (explicit then ``/settings`` under API base).

        Returns parsed JSON. Raises CloudClientError on failure.
        """
        urls = resolve_settings_urls(self._cfg)
        if not urls:
            raise CloudClientError(
                "No settings URL could be built. Set AWS_SETTINGS_URL or AWS_API_BASE.",
                error_code="SETTINGS_URL_UNCONFIGURED",
            )

        last_exc: Optional[CloudClientError] = None
        for url in urls:
            try:
                resp = self._session.post(
                    url,
                    json=payload,
                    timeout=self._timeout_tuple(),
                    headers={"Content-Type": "application/json"},
                )
            except requests.RequestException as exc:
                last_exc = CloudClientError(
                    str(exc),
                    error_code="SETTINGS_TRANSPORT_ERROR",
                    url=url,
                )
                logger.warning("POST %s failed: %s", url, exc)
                continue

            if resp.status_code == 404:
                logger.info("POST settings 404 at %s, trying next candidate.", url)
                parsed, raw = _parse_error_response(resp)
                last_exc = _settings_route_not_found_error(url, raw, parsed, "POST")
                continue

            try:
                body = resp.json()
            except ValueError:
                body = {"success": False, "message": resp.text}

            if not resp.ok:
                _raise_settings_http_error(url, resp, "POST")

            if isinstance(body, dict):
                return body
            raise CloudClientError("Unexpected POST /settings payload", error_code="SETTINGS_SHAPE_ERROR", url=url)

        if last_exc:
            raise last_exc
        raise CloudClientError("POST /settings failed", error_code="SETTINGS_UNKNOWN_ERROR")

    def ping_data_endpoint(self, timeout: float = 3.0) -> bool:
        """Lightweight connectivity check (GET /data)."""
        try:
            self.fetch_dashboard_data(timeout=timeout)
            return True
        except CloudClientError:
            return False

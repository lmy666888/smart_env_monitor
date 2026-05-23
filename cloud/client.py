"""HTTP client for API Gateway (ingest, data, settings, auth, health)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import Config
from config import cloud_config

logger = logging.getLogger("smart_env_monitor.cloud.client")


class CloudClientError(Exception):
    """Raised when a cloud API call fails."""

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
        out: Dict[str, Any] = {"source": "aws"}
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
    sess.headers.update({"Accept": "application/json", "User-Agent": "smart-env-monitor/3.0-aws-brain"})
    return sess


def _parse_error_response(resp: requests.Response) -> Tuple[Optional[Dict[str, Any]], str]:
    text = (resp.text or "").strip()
    try:
        j = resp.json()
        if isinstance(j, dict):
            return j, text
    except ValueError:
        pass
    return None, text


def _settings_route_not_found_error(
    url: str, raw: str, parsed: Optional[Dict[str, Any]], verb: str
) -> CloudClientError:
    return CloudClientError(
        f"AWS returned 404 for {verb} /settings: the route is not deployed on this API Gateway, "
        "or AWS_SETTINGS_URL is wrong.",
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


def resolve_settings_urls(cfg: type) -> List[str]:
    """Candidate URLs for /settings."""
    seen: set[str] = set()
    out: List[str] = []

    def add(u: str) -> None:
        u = (u or "").strip().rstrip("/")
        if not u or u in seen:
            return
        seen.add(u)
        out.append(u)

    explicit = getattr(cfg, "AWS_SETTINGS_URL", None)
    if explicit:
        add(str(explicit))
    add(cloud_config.endpoint_url(cloud_config.SETTINGS_ENDPOINT))
    return out


class CloudAPIClient:
    """Thin proxy over AWS API Gateway endpoints (authoritative AWS Brain)."""

    def __init__(self, config_class: type = Config):
        self._cfg = config_class
        self._session = _session(
            timeout=float(config_class.HTTP_TIMEOUT_SECONDS),
            total_retries=max(0, int(config_class.HTTP_MAX_RETRIES)),
            backoff=float(config_class.HTTP_RETRY_BACKOFF),
        )

    def _timeout_tuple(self) -> tuple[float, float]:
        t = float(self._cfg.HTTP_TIMEOUT_SECONDS)
        return (t, t)

    def _dashboard_timeout(self, timeout: Optional[float]) -> tuple[float, float]:
        to = float(timeout if timeout is not None else self._cfg.DASHBOARD_CLOUD_TIMEOUT)
        return (to, to)

    def _device_key_headers(self) -> Dict[str, str]:
        key = str(getattr(self._cfg, "DEVICE_API_KEY", "") or cloud_config.DEVICE_API_KEY or "").strip()
        if key:
            return {"X-DEVICE-KEY": key}
        return {}

    def request_json(
        self,
        method: str,
        url: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json_body: Optional[Dict[str, Any]] = None,
        timeout: Optional[float] = None,
        error_code: str = "AWS_API_ERROR",
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Perform HTTP request and return parsed JSON dict.

        Raises CloudClientError on transport failure or non-2xx (unless body is JSON error).
        """
        to = self._timeout_tuple() if timeout is None else (float(timeout), float(timeout))
        headers: Dict[str, str] = {}
        if json_body is not None:
            headers["Content-Type"] = "application/json"
        if extra_headers:
            headers.update(extra_headers)
        try:
            resp = self._session.request(
                method.upper(),
                url,
                params=params,
                json=json_body,
                timeout=to,
                headers=headers or None,
            )
        except requests.RequestException as exc:
            logger.warning("%s %s failed: %s", method.upper(), url, exc)
            raise CloudClientError(
                str(exc),
                error_code="AWS_API_UNAVAILABLE",
                url=url,
            ) from exc

        parsed, raw = _parse_error_response(resp)
        if not resp.ok:
            msg = raw or f"HTTP {resp.status_code}"
            if parsed:
                msg = str(parsed.get("message") or parsed.get("error") or msg)
            code = error_code
            if parsed and parsed.get("error_code"):
                code = str(parsed["error_code"])
            raise CloudClientError(
                msg,
                status_code=resp.status_code,
                error_code=code,
                url=url,
                response_body=raw,
                parsed_body=parsed,
            )

        if parsed is not None:
            return parsed
        if not raw:
            return {}
        raise CloudClientError(
            "Invalid JSON from AWS API",
            error_code="AWS_JSON_ERROR",
            url=url,
            response_body=raw,
        )

    def fetch_dashboard_data(
        self,
        device_id: Optional[str] = None,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """GET /data — authoritative dashboard payload from Lambda."""
        params: Dict[str, Any] = {}
        if device_id:
            params["device_id"] = device_id
        url = getattr(self._cfg, "AWS_DATA_URL", cloud_config.endpoint_url(cloud_config.DATA_ENDPOINT))
        try:
            resp = self._session.get(url, params=params or None, timeout=self._dashboard_timeout(timeout))
        except requests.RequestException as exc:
            logger.warning("Cloud GET /data failed: %s", exc)
            raise CloudClientError(str(exc), error_code="AWS_API_UNAVAILABLE", url=url) from exc

        if not resp.ok:
            parsed, raw = _parse_error_response(resp)
            raise CloudClientError(
                f"GET /data failed with HTTP {resp.status_code}",
                status_code=resp.status_code,
                error_code="DATA_HTTP_ERROR",
                url=url,
                response_body=raw,
                parsed_body=parsed,
            )

        try:
            data = resp.json()
        except ValueError as exc:
            raise CloudClientError("Invalid JSON from /data", error_code="DATA_JSON_ERROR", url=url) from exc

        if not isinstance(data, dict):
            raise CloudClientError("Unexpected /data payload shape", error_code="DATA_SHAPE_ERROR", url=url)
        return data

    def post_sensor_reading(self, payload: Dict[str, Any]) -> bool:
        """POST /ingest — returns True on 2xx (collector compatibility)."""
        result = self.post_ingest(payload)
        return bool(result.get("success", True))

    def post_ingest(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST /ingest — returns parsed AWS JSON body."""
        url = getattr(self._cfg, "AWS_INGEST_URL", cloud_config.endpoint_url(cloud_config.INGEST_ENDPOINT))
        if not url:
            logger.error("AWS_INGEST_URL is empty; cannot upload.")
            return {"success": False, "message": "Ingest URL not configured.", "error_code": "INGEST_URL_UNCONFIGURED"}
        extra_headers = self._device_key_headers()
        try:
            return self.request_json(
                "POST",
                url,
                json_body=payload,
                error_code="INGEST_HTTP_ERROR",
                extra_headers=extra_headers or None,
            )
        except CloudClientError as exc:
            logger.warning("Cloud POST /ingest failed: %s", exc)
            return {
                "success": False,
                "message": str(exc),
                "error_code": exc.error_code or "AWS_API_UNAVAILABLE",
                "source": "aws",
            }

    def get_settings(self, device_id: Optional[str] = None) -> Dict[str, Any]:
        """GET /settings for a device (query ``device_id``, default from config)."""
        urls = resolve_settings_urls(self._cfg)
        if not urls:
            raise CloudClientError(
                "No settings URL configured.",
                error_code="SETTINGS_URL_UNCONFIGURED",
            )

        did = device_id or getattr(self._cfg, "DEVICE_ID", "pi-001")
        params = {"device_id": did}

        last_exc: Optional[CloudClientError] = None
        for url in urls:
            try:
                resp = self._session.get(url, params=params, timeout=self._timeout_tuple())
            except requests.RequestException as exc:
                last_exc = CloudClientError(str(exc), error_code="AWS_API_UNAVAILABLE", url=url)
                continue

            if resp.status_code == 404:
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

    def post_settings(self, payload: Dict[str, Any], device_id: Optional[str] = None) -> Dict[str, Any]:
        """POST /settings for a device (includes ``device_id`` in JSON body)."""
        body = dict(payload)
        body.setdefault("device_id", device_id or getattr(self._cfg, "DEVICE_ID", "pi-001"))
        urls = resolve_settings_urls(self._cfg)
        if not urls:
            raise CloudClientError(
                "No settings URL configured.",
                error_code="SETTINGS_URL_UNCONFIGURED",
            )

        last_exc: Optional[CloudClientError] = None
        for url in urls:
            try:
                resp = self._session.post(
                    url,
                    json=body,
                    timeout=self._timeout_tuple(),
                    headers={"Content-Type": "application/json"},
                )
            except requests.RequestException as exc:
                last_exc = CloudClientError(str(exc), error_code="AWS_API_UNAVAILABLE", url=url)
                continue

            if resp.status_code == 404:
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

    def post_login(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST /login — DynamoDB Users table via auth_handler Lambda."""
        url = getattr(self._cfg, "AWS_LOGIN_URL", cloud_config.endpoint_url(cloud_config.LOGIN_ENDPOINT))
        return self.request_json("POST", url, json_body=payload, error_code="LOGIN_HTTP_ERROR")

    def post_register(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """POST /register."""
        url = getattr(
            self._cfg,
            "AWS_REGISTER_URL",
            cloud_config.endpoint_url(cloud_config.REGISTER_ENDPOINT),
        )
        return self.request_json("POST", url, json_body=payload, error_code="REGISTER_HTTP_ERROR")

    def fetch_health(self, timeout: float = 5.0) -> Dict[str, Any]:
        """GET /health."""
        url = getattr(self._cfg, "AWS_HEALTH_URL", cloud_config.endpoint_url(cloud_config.HEALTH_ENDPOINT))
        return self.request_json("GET", url, timeout=timeout, error_code="HEALTH_HTTP_ERROR")

    def ping_data_endpoint(self, timeout: float = 3.0) -> bool:
        try:
            self.fetch_dashboard_data(timeout=timeout)
            return True
        except CloudClientError:
            return False

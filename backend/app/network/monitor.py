from __future__ import annotations

import logging
import math
import re
import ssl
import statistics
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib import error, request
from urllib.parse import urlparse

from .audit import MariaDBAuditStorage
from .mariadb_storage import MariaDBStorage
from .notifications import NotificationService
from .snmp_switch import collect_switch


LOGGER = logging.getLogger(__name__)
PING_PATTERN = re.compile(r"(?:tempo|time)\s*[=<]\s*(\d+(?:[.,]\d+)?)\s*ms", re.IGNORECASE)
PING_REPLY_MARKERS = ("bytes from", "bytes de", "reply from", "resposta de")
HTTP_SUCCESS_STATUSES = range(200, 400)


def build_unavailable_result(
    check_type: str,
    sent: int,
    error_message: str | None = None,
) -> dict[str, Any]:
    return {
        "check_type": check_type,
        "http_status_code": None,
        "error": error_message,
        "online": False,
        "sent": sent,
        "received": 0,
        "packet_loss_pct": 100.0,
        "avg_latency_ms": None,
        "min_latency_ms": None,
        "max_latency_ms": None,
        "jitter_ms": None,
        "samples_ms": [],
    }


def parse_ping_times(output: str) -> list[float]:
    latencies: list[float] = []

    for line in output.splitlines():
        if not any(marker in line.lower() for marker in PING_REPLY_MARKERS):
            continue

        match = PING_PATTERN.search(line)
        if match:
            latencies.append(float(match.group(1).replace(",", ".")))

    return latencies


def calculate_jitter(latencies: list[float]) -> float | None:
    if len(latencies) < 2:
        return None

    deltas = [abs(current - previous) for previous, current in zip(latencies, latencies[1:])]
    return round(sum(deltas) / len(deltas), 2)


def normalize_ping_target(address: str) -> str:
    value = address.strip()
    if not value:
        return ""

    parsed = urlparse(value if "://" in value else f"//{value}")
    if parsed.hostname:
        return parsed.hostname

    return value


def is_http_target(address: str) -> bool:
    parsed = urlparse(address.strip())
    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)


def ping_host(host: str, count: int, timeout_ms: int) -> dict[str, Any]:
    ping_target = normalize_ping_target(host)
    timeout_seconds = max(1, math.ceil(timeout_ms / 1000))
    if sys.platform == "win32":
        command = ["ping", "-n", str(count), "-w", str(timeout_ms), ping_target]
    else:
        command = ["ping", "-c", str(count), "-W", str(timeout_seconds), ping_target]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
            timeout=(timeout_seconds * max(1, count)) + 5,
        )
    except subprocess.TimeoutExpired as exc:
        return build_unavailable_result(
            "ping",
            count,
            f"Ping timed out after {exc.timeout} seconds",
        )
    except OSError as exc:
        return build_unavailable_result("ping", count, str(exc))

    output = "\n".join(part for part in [completed.stdout, completed.stderr] if part)
    latencies = parse_ping_times(output)
    received = len(latencies)
    sent = count
    packet_loss_pct = round(((sent - received) / sent) * 100, 2)
    online = received > 0

    if latencies:
        avg_latency = round(statistics.fmean(latencies), 2)
        min_latency = round(min(latencies), 2)
        max_latency = round(max(latencies), 2)
        jitter = calculate_jitter(latencies)
    else:
        avg_latency = None
        min_latency = None
        max_latency = None
        jitter = None

    return {
        "check_type": "ping",
        "http_status_code": None,
        "error": None,
        "online": online,
        "sent": sent,
        "received": received,
        "packet_loss_pct": packet_loss_pct,
        "avg_latency_ms": avg_latency,
        "min_latency_ms": min_latency,
        "max_latency_ms": max_latency,
        "jitter_ms": jitter,
        "samples_ms": latencies,
    }


def normalize_http_url(url: str) -> str:
    parsed = urlparse(url.strip())
    return parsed._replace(fragment="").geturl()


def create_compatible_ssl_context() -> ssl.SSLContext:
    context = ssl.create_default_context()
    context.set_ciphers("DEFAULT:@SECLEVEL=1")
    return context


def is_tls_handshake_failure(exc: BaseException) -> bool:
    return "sslv3 alert handshake failure" in str(exc).lower()


def open_http_response(url: str, timeout_seconds: float, context: ssl.SSLContext | None = None) -> int:
    http_request = request.Request(
        url,
        headers={"User-Agent": "MonitorNet/1.0"},
        method="GET",
    )
    with request.urlopen(http_request, timeout=timeout_seconds, context=context) as response:
        status_code = response.getcode()
        response.read(1)
        return status_code


def check_http_endpoint(url: str, timeout_ms: int) -> dict[str, Any]:
    normalized_url = normalize_http_url(url)
    started_at = time.perf_counter()
    timeout_seconds = max(0.1, timeout_ms / 1000)
    http_status_code: int | None = None
    error_message: str | None = None

    try:
        http_status_code = open_http_response(normalized_url, timeout_seconds)
    except error.HTTPError as exc:
        http_status_code = exc.code
        error_message = str(exc)
    except (error.URLError, TimeoutError, OSError) as exc:
        if normalized_url.startswith("https://") and is_tls_handshake_failure(exc):
            try:
                http_status_code = open_http_response(
                    normalized_url,
                    timeout_seconds,
                    context=create_compatible_ssl_context(),
                )
            except error.HTTPError as fallback_exc:
                http_status_code = fallback_exc.code
                error_message = str(fallback_exc)
            except (error.URLError, TimeoutError, OSError) as fallback_exc:
                error_message = str(fallback_exc)
        else:
            error_message = str(exc)

    response_time_ms = round((time.perf_counter() - started_at) * 1000, 2)
    has_http_response = http_status_code is not None
    online = http_status_code in HTTP_SUCCESS_STATUSES if has_http_response else False

    return {
        "check_type": "http",
        "http_status_code": http_status_code,
        "error": error_message,
        "online": online,
        "sent": 1,
        "received": 1 if has_http_response else 0,
        "packet_loss_pct": 0.0 if has_http_response else 100.0,
        "avg_latency_ms": response_time_ms if has_http_response else None,
        "min_latency_ms": response_time_ms if has_http_response else None,
        "max_latency_ms": response_time_ms if has_http_response else None,
        "jitter_ms": None,
        "samples_ms": [response_time_ms] if has_http_response else [],
    }


def resolve_status(online: bool, avg_latency_ms: float | None, threshold: int | None) -> str:
    if not online:
        return "offline"
    if threshold is not None and avg_latency_ms is not None and avg_latency_ms >= threshold:
        return "degraded"
    return "online"


class MonitorService:
    """Background service that updates host measurements periodically."""

    def __init__(
        self,
        storage: MariaDBStorage,
        audit_storage: MariaDBAuditStorage,
        interval_seconds: int = 15,
        ping_count: int = 4,
        timeout_ms: int = 1000,
        stability_window: int = 20,
        max_entries: int = 1000,
        ping_concurrency: int = 8,
        history_retention_days: int = 1,
        history_prune_interval_seconds: int = 3600,
        snmp_interval_seconds: int = 60,
        notification_service: NotificationService | None = None,
    ) -> None:
        self.storage = storage
        self.audit_storage = audit_storage
        self.notification_service = notification_service or NotificationService(storage)
        self.interval_seconds = interval_seconds
        self.ping_count = ping_count
        self.timeout_ms = timeout_ms
        self.stability_window = stability_window
        self.max_entries = max_entries
        self.ping_concurrency = max(1, ping_concurrency)
        self.history_retention_days = max(1, history_retention_days)
        self.history_prune_interval_seconds = max(60, history_prune_interval_seconds)
        self.snmp_interval_seconds = max(5, snmp_interval_seconds)
        self._last_switch_poll: dict[str, float] = {}
        self.current_status: dict[str, dict[str, Any]] = {}
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._cycle_lock = threading.Lock()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2)

    def _run_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.run_cycle()
            except Exception:
                LOGGER.exception("Monitor cycle failed")
            self._stop_event.wait(self.interval_seconds)

    def _prune_history_if_due(self) -> None:
        now = datetime.now(timezone.utc)
        last_prune = self.storage.get_last_reset()

        if last_prune is not None:
            elapsed = (now - last_prune).total_seconds()
            if elapsed < self.history_prune_interval_seconds:
                return

        cutoff = now - timedelta(days=self.history_retention_days)
        self.storage.delete_history_before(cutoff)
        self.storage.set_last_reset(now)

    def run_cycle(self, service_ids: set[str] | None = None) -> None:
        requested_ids = set(service_ids) if service_ids else None

        with self._cycle_lock:
            self._prune_history_if_due()
            services = self.storage.load_services()
            existing_ids = {str(service["id"]) for service in services}

            for stale_id in list(self.current_status):
                if stale_id not in existing_ids:
                    self.current_status.pop(stale_id, None)
                    self._last_switch_poll.pop(stale_id, None)

            selected_services: list[dict[str, Any]] = []
            for service in services:
                service_id = str(service["id"])
                if requested_ids is not None and service_id not in requested_ids:
                    continue
                if not all(key in service for key in ("id", "name", "host")):
                    continue
                selected_services.append(service)

            measured_entries = self._measure_services(selected_services)
            for service_id, entry in measured_entries:
                persisted_entry = self.storage.append_history_entry(
                    entry,
                    max_entries=self.max_entries,
                    stability_window=self.stability_window,
                )
                if persisted_entry is None:
                    continue

                try:
                    self.audit_storage.record_status(persisted_entry)
                except Exception:
                    LOGGER.exception("Unable to persist audit event for %s", service_id)

                try:
                    self.notification_service.process_entry(persisted_entry)
                except Exception:
                    LOGGER.exception("Unable to process notification for %s", service_id)

                self.current_status[service_id] = persisted_entry

    def _measure_services(self, services: list[dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
        if not services:
            return []

        worker_count = min(self.ping_concurrency, len(services))
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            return list(executor.map(self._measure_service, services))

    def _measure_service(self, service: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        service_id = str(service["id"])
        host = str(service["host"])
        check_type = "http" if is_http_target(host) else "ping"
        sent = 1 if check_type == "http" else self.ping_count

        try:
            if check_type == "http":
                result = check_http_endpoint(host, self.timeout_ms)
            else:
                result = ping_host(host, self.ping_count, self.timeout_ms)
        except Exception as exc:
            LOGGER.exception("Unable to measure service %s", service_id)
            result = build_unavailable_result(check_type, sent, str(exc))

        should_poll_switch = (
            service_id not in self._last_switch_poll
            or time.monotonic() - self._last_switch_poll[service_id] >= self.snmp_interval_seconds
        )
        switch_config = self.storage.get_switch_config(service_id) if should_poll_switch else None
        if switch_config:
            try:
                snapshot = collect_switch(
                    normalize_ping_target(host),
                    switch_config["community"],
                    switch_config["port"],
                )
            except Exception as exc:
                LOGGER.warning("SNMP collection failed for %s: %s", service_id, exc)
                snapshot = {
                    "collectedAt": datetime.now(timezone.utc).isoformat(),
                    "system": {},
                    "interfaces": [],
                    "error": "Sem resposta SNMP. Verifique community, porta UDP e acesso ao switch.",
                }
            try:
                self.storage.save_switch_snapshot(service_id, snapshot)
            except Exception:
                LOGGER.exception("Unable to persist SNMP snapshot for %s", service_id)
            self._last_switch_poll[service_id] = time.monotonic()

        return service_id, self._build_entry(service, result)

    def _build_entry(self, service: dict[str, Any], ping_result: dict[str, Any]) -> dict[str, Any]:
        timestamp = datetime.now(timezone.utc).isoformat()
        threshold = service.get("threshold")

        return {
            "timestamp": timestamp,
            "service": {
                "id": service["id"],
                "name": service["name"],
                "host": service["host"],
                "threshold": threshold,
                "check_type": ping_result["check_type"],
            },
            "check_type": ping_result["check_type"],
            "http_status_code": ping_result.get("http_status_code"),
            "error": ping_result.get("error"),
            "online": ping_result["online"],
            "status": resolve_status(ping_result["online"], ping_result["avg_latency_ms"], threshold),
            "sent": ping_result["sent"],
            "received": ping_result["received"],
            "packet_loss_pct": ping_result["packet_loss_pct"],
            "avg_latency_ms": ping_result["avg_latency_ms"],
            "min_latency_ms": ping_result["min_latency_ms"],
            "max_latency_ms": ping_result["max_latency_ms"],
            "jitter_ms": ping_result["jitter_ms"],
            "samples_ms": ping_result["samples_ms"],
            "stability_pct": 0.0,
        }

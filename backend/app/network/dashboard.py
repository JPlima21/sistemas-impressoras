from __future__ import annotations

from typing import Any
from urllib.parse import urlparse


def average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def get_check_type(service: dict[str, Any], latest: dict[str, Any] | None = None) -> str:
    if latest and latest.get("check_type"):
        return str(latest["check_type"])

    parsed = urlparse(str(service.get("host", "")).strip())
    if parsed.scheme.lower() in {"http", "https"} and parsed.netloc:
        return "http"
    return "ping"


def build_dashboard_data(
    services: list[dict[str, Any]],
    history: dict[str, list[dict[str, Any]]],
    next_update_seconds: int = 15,
) -> dict[str, Any]:
    snapshots: list[dict[str, Any]] = []

    for service in services:
        entries = history.get(service["id"], [])
        latest = entries[-1] if entries else None

        check_type = get_check_type(service, latest)

        if latest is None:
            snapshots.append(
                {
                    "id": service["id"],
                    "name": service["name"],
                    "host": service["host"],
                    "threshold": service.get("threshold", 100),
                    "imageUrl": service.get("imageUrl", ""),
                    "sortOrder": service.get("sortOrder", 0),
                    "kind": service.get("kind", "service"),
                    "snmpPort": service.get("snmpPort"),
                    "checkType": check_type,
                    "httpStatusCode": None,
                    "error": None,
                    "online": False,
                    "status": "offline",
                    "avgLatencyMs": None,
                    "minLatencyMs": None,
                    "maxLatencyMs": None,
                    "packetLossPct": None,
                    "jitterMs": None,
                    "stabilityPct": None,
                    "sent": None,
                    "received": None,
                    "samplesMs": [],
                    "lastUpdate": None,
                }
            )
            continue

        snapshots.append(
            {
                "id": service["id"],
                "name": service["name"],
                "host": service["host"],
                "threshold": service.get("threshold", 100),
                "imageUrl": service.get("imageUrl", ""),
                "sortOrder": service.get("sortOrder", 0),
                "kind": service.get("kind", "service"),
                "snmpPort": service.get("snmpPort"),
                "checkType": check_type,
                "httpStatusCode": latest.get("http_status_code"),
                "error": latest.get("error"),
                "online": latest["online"],
                "status": latest["status"],
                "avgLatencyMs": latest["avg_latency_ms"],
                "minLatencyMs": latest["min_latency_ms"],
                "maxLatencyMs": latest["max_latency_ms"],
                "packetLossPct": latest["packet_loss_pct"],
                "jitterMs": latest["jitter_ms"],
                "stabilityPct": latest["stability_pct"],
                "sent": latest["sent"],
                "received": latest["received"],
                "samplesMs": latest["samples_ms"],
                "lastUpdate": latest["timestamp"],
            }
        )

    normalized_history = {
        service["id"]: [
            {
                "timestamp": entry["timestamp"],
                "latencyMs": entry["avg_latency_ms"],
                "online": entry["online"],
                "status": entry["status"],
                "packetLossPct": entry["packet_loss_pct"],
                "jitterMs": entry["jitter_ms"],
                "stabilityPct": entry["stability_pct"],
                "threshold": entry["service"].get("threshold", 100),
                "checkType": entry.get("check_type", get_check_type(service)),
                "httpStatusCode": entry.get("http_status_code"),
            }
            for entry in history.get(service["id"], [])
        ]
        for service in services
    }

    last_updates = [service["lastUpdate"] for service in snapshots if service["lastUpdate"]]
    latency_values = [service["avgLatencyMs"] for service in snapshots if isinstance(service["avgLatencyMs"], (int, float))]
    stability_values = [service["stabilityPct"] for service in snapshots if isinstance(service["stabilityPct"], (int, float))]

    return {
        "meta": {
            "source": "python",
            "lastUpdate": max(last_updates) if last_updates else None,
            "nextUpdateSeconds": next_update_seconds,
        },
        "summary": {
            "total": len(snapshots),
            "online": sum(1 for service in snapshots if service["status"] == "online"),
            "degraded": sum(1 for service in snapshots if service["status"] == "degraded"),
            "offline": sum(1 for service in snapshots if service["status"] == "offline"),
            "avgLatencyMs": average(latency_values),
            "avgStabilityPct": average(stability_values),
        },
        "services": snapshots,
        "history": normalized_history,
    }

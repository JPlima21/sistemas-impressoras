from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

import pymysql
from pymysql.cursors import DictCursor

from .database import connect_mariadb


class MariaDBAuditStorage:
    """Persiste incidentes de indisponibilidade e instabilidade no MariaDB."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._connection = self._connect()
        self._ensure_table()

    def _connect(self) -> pymysql.Connection:
        return connect_mariadb()

    def _cursor(self) -> DictCursor:
        try:
            self._connection.ping(reconnect=True)
        except pymysql.MySQLError:
            self._connection = self._connect()
        return self._connection.cursor()

    def _ensure_table(self) -> None:
        with self._lock:
            cursor = self._cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS monitor_audit_events (
                    id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                    service_id VARCHAR(191) NOT NULL,
                    service_name VARCHAR(255) NOT NULL,
                    service_host VARCHAR(2048) NOT NULL,
                    event_type ENUM('outage', 'instability') NOT NULL,
                    status VARCHAR(20) NOT NULL,
                    started_at VARCHAR(40) NOT NULL,
                    ended_at VARCHAR(40) NULL,
                    duration_seconds BIGINT UNSIGNED NULL,
                    packet_loss_pct DOUBLE NULL,
                    avg_latency_ms DOUBLE NULL,
                    threshold_ms INT NULL,
                    check_type VARCHAR(20) NOT NULL,
                    http_status_code INT NULL,
                    error TEXT NULL,
                    INDEX idx_audit_service_started (service_id, started_at),
                    INDEX idx_audit_open_event (service_id, ended_at)
                ) ENGINE=InnoDB
                  DEFAULT CHARSET=utf8mb4
                  COLLATE=utf8mb4_unicode_ci
                """
            )
            self._connection.commit()

    def record_status(self, entry: dict[str, Any]) -> None:
        """Abre, troca ou encerra um incidente conforme o estado medido."""
        service = entry["service"]
        service_id = str(service["id"])
        current_status = str(entry["status"])
        event_type = "outage" if current_status == "offline" else None

        with self._lock:
            cursor = self._cursor()
            cursor.execute(
                """
                SELECT id, event_type, started_at
                FROM monitor_audit_events
                WHERE service_id = %s AND ended_at IS NULL
                ORDER BY id DESC
                LIMIT 1
                FOR UPDATE
                """,
                (service_id,),
            )
            open_event = cursor.fetchone()

            if open_event and open_event["event_type"] == event_type:
                self._connection.commit()
                return

            timestamp = str(entry["timestamp"])
            if open_event:
                duration = self._duration_seconds(open_event["started_at"], timestamp)
                cursor.execute(
                    """
                    UPDATE monitor_audit_events
                    SET ended_at = %s, duration_seconds = %s
                    WHERE id = %s
                    """,
                    (timestamp, duration, open_event["id"]),
                )

            if event_type:
                cursor.execute(
                    """
                    INSERT INTO monitor_audit_events (
                        service_id, service_name, service_host, event_type,
                        status, started_at, packet_loss_pct, avg_latency_ms,
                        threshold_ms, check_type, http_status_code, error
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        service_id,
                        str(service["name"]),
                        str(service["host"]),
                        event_type,
                        current_status,
                        timestamp,
                        entry.get("packet_loss_pct"),
                        entry.get("avg_latency_ms"),
                        service.get("threshold"),
                        entry.get("check_type", "ping"),
                        entry.get("http_status_code"),
                        entry.get("error"),
                    ),
                )

            self._connection.commit()

    @staticmethod
    def _duration_seconds(started_at: str, ended_at: str) -> int:
        try:
            started = datetime.fromisoformat(started_at)
            ended = datetime.fromisoformat(ended_at)
            return max(0, int((ended - started).total_seconds()))
        except ValueError:
            return 0

    def load_events(self, limit: int = 500) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit), 5000))
        with self._lock:
            cursor = self._cursor()
            cursor.execute(
                """
                SELECT id, service_id, service_name, service_host, event_type,
                       status, started_at, ended_at, duration_seconds,
                       packet_loss_pct, avg_latency_ms, threshold_ms,
                       check_type, http_status_code, error
                FROM monitor_audit_events
                WHERE event_type = 'outage'
                ORDER BY id DESC
                LIMIT %s
                """,
                (safe_limit,),
            )
            rows = cursor.fetchall()

        return [
            {**row, "id": int(row["id"]), "ongoing": row["ended_at"] is None}
            for row in rows
        ]

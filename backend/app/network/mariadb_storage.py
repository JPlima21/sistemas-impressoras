from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from typing import Any, Iterable

import pymysql
from pymysql.cursors import DictCursor

from .database import connect_mariadb


def _slugify_name(name: str) -> str:
    normalized = "".join(char.lower() if char.isalnum() else "-" for char in name.strip())
    compact = "-".join(part for part in normalized.split("-") if part)
    return compact or "service"


class MariaDBStorage:
    """Primary application storage backed entirely by MariaDB."""

    TABLES = {
        "services": "monitor_services",
        "history": "monitor_history",
        "notification_settings": "monitor_notification_settings",
        "notification_recipients": "monitor_notification_recipients",
        "notification_services": "monitor_notification_services",
        "notification_subscriptions": "monitor_notification_subscriptions",
        "notification_incidents": "monitor_notification_incidents",
        "runtime_state": "monitor_runtime_state",
    }

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._connection = self._connect()
        self._ensure_tables()

    def _connect(self) -> pymysql.Connection:
        return connect_mariadb()

    def _cursor(self) -> DictCursor:
        try:
            self._connection.ping(reconnect=True)
        except pymysql.MySQLError:
            self._connection = self._connect()
        return self._connection.cursor()

    def _ensure_tables(self) -> None:
        statements = (
            """
            CREATE TABLE IF NOT EXISTS monitor_services (
                id VARCHAR(191) NOT NULL PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                host TEXT NOT NULL,
                threshold INT UNSIGNED NOT NULL DEFAULT 100,
                image_url LONGTEXT NOT NULL,
                sort_order INT NOT NULL DEFAULT 0,
                INDEX idx_monitor_services_order (sort_order, name)
            ) ENGINE=InnoDB
              DEFAULT CHARSET=utf8mb4
              COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS monitor_history (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
                service_id VARCHAR(191) NOT NULL,
                timestamp VARCHAR(40) NOT NULL,
                online TINYINT(1) NOT NULL,
                status VARCHAR(20) NOT NULL,
                sent INT UNSIGNED NOT NULL,
                received INT UNSIGNED NOT NULL,
                packet_loss_pct DOUBLE NOT NULL,
                avg_latency_ms DOUBLE NULL,
                min_latency_ms DOUBLE NULL,
                max_latency_ms DOUBLE NULL,
                jitter_ms DOUBLE NULL,
                samples_ms LONGTEXT NOT NULL,
                stability_pct DOUBLE NOT NULL,
                service_threshold INT NULL,
                check_type VARCHAR(20) NOT NULL DEFAULT 'ping',
                http_status_code INT NULL,
                error TEXT NULL,
                CONSTRAINT fk_monitor_history_service
                    FOREIGN KEY (service_id) REFERENCES monitor_services(id)
                    ON DELETE CASCADE,
                UNIQUE KEY uq_monitor_history_service_timestamp (service_id, timestamp),
                INDEX idx_monitor_history_timestamp (timestamp)
            ) ENGINE=InnoDB
              DEFAULT CHARSET=utf8mb4
              COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS monitor_notification_settings (
                id TINYINT UNSIGNED NOT NULL PRIMARY KEY,
                enabled TINYINT(1) NOT NULL DEFAULT 0,
                recipient VARCHAR(320) NOT NULL DEFAULT ''
            ) ENGINE=InnoDB
              DEFAULT CHARSET=utf8mb4
              COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS monitor_switch_config (
                service_id VARCHAR(191) NOT NULL PRIMARY KEY,
                community VARCHAR(255) NOT NULL,
                port SMALLINT UNSIGNED NOT NULL DEFAULT 161,
                CONSTRAINT fk_monitor_switch_config_service
                    FOREIGN KEY (service_id) REFERENCES monitor_services(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB
              DEFAULT CHARSET=utf8mb4
              COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS monitor_switch_snapshot (
                service_id VARCHAR(191) NOT NULL PRIMARY KEY,
                collected_at VARCHAR(40) NOT NULL,
                payload LONGTEXT NOT NULL,
                CONSTRAINT fk_monitor_switch_snapshot_service
                    FOREIGN KEY (service_id) REFERENCES monitor_services(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB
              DEFAULT CHARSET=utf8mb4
              COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS monitor_notification_recipients (
                email VARCHAR(320) NOT NULL PRIMARY KEY
            ) ENGINE=InnoDB
              DEFAULT CHARSET=utf8mb4
              COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS monitor_notification_services (
                service_id VARCHAR(191) NOT NULL PRIMARY KEY,
                CONSTRAINT fk_monitor_notification_selection_service
                    FOREIGN KEY (service_id) REFERENCES monitor_services(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB
              DEFAULT CHARSET=utf8mb4
              COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS monitor_notification_subscriptions (
                email VARCHAR(320) NOT NULL,
                service_id VARCHAR(191) NOT NULL,
                PRIMARY KEY (email, service_id),
                CONSTRAINT fk_monitor_subscription_recipient
                    FOREIGN KEY (email) REFERENCES monitor_notification_recipients(email)
                    ON DELETE CASCADE,
                CONSTRAINT fk_monitor_subscription_service
                    FOREIGN KEY (service_id) REFERENCES monitor_services(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB
              DEFAULT CHARSET=utf8mb4
              COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS monitor_notification_incidents (
                service_id VARCHAR(191) NOT NULL PRIMARY KEY,
                offline_since VARCHAR(40) NOT NULL,
                notified_at VARCHAR(40) NULL,
                CONSTRAINT fk_monitor_notification_service
                    FOREIGN KEY (service_id) REFERENCES monitor_services(id)
                    ON DELETE CASCADE
            ) ENGINE=InnoDB
              DEFAULT CHARSET=utf8mb4
              COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS monitor_runtime_state (
                state_key VARCHAR(100) NOT NULL PRIMARY KEY,
                state_value TEXT NOT NULL
            ) ENGINE=InnoDB
              DEFAULT CHARSET=utf8mb4
              COLLATE=utf8mb4_unicode_ci
            """,
            """
            INSERT IGNORE INTO monitor_notification_settings (id, enabled, recipient)
            VALUES (1, 0, '')
            """,
        )

        with self._lock:
            cursor = self._cursor()
            try:
                for statement in statements:
                    cursor.execute(statement)
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

        self._migrate_legacy_notification_settings()
        self._migrate_global_notification_selections()

    def _migrate_legacy_notification_settings(self) -> None:
        """Preserve the previous single-recipient/all-services behavior once."""
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute(
                    """
                    SELECT state_value
                    FROM monitor_runtime_state
                    WHERE state_key = 'notification_settings_v2_migrated'
                    """
                )
                if cursor.fetchone() is not None:
                    self._connection.rollback()
                    return

                cursor.execute(
                    "SELECT recipient FROM monitor_notification_settings WHERE id = 1"
                )
                row = cursor.fetchone()
                legacy_recipient = str(row["recipient"] or "").strip() if row else ""
                if legacy_recipient:
                    cursor.execute(
                        "INSERT IGNORE INTO monitor_notification_recipients (email) VALUES (%s)",
                        (legacy_recipient,),
                    )
                    cursor.execute(
                        """
                        INSERT IGNORE INTO monitor_notification_services (service_id)
                        SELECT id FROM monitor_services
                        """
                    )

                cursor.execute(
                    """
                    INSERT INTO monitor_runtime_state (state_key, state_value)
                    VALUES ('notification_settings_v2_migrated', '1')
                    ON DUPLICATE KEY UPDATE state_value = VALUES(state_value)
                    """
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

    def _migrate_global_notification_selections(self) -> None:
        """Convert the previous recipients/global-services model to subscriptions."""
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute(
                    """
                    SELECT state_value
                    FROM monitor_runtime_state
                    WHERE state_key = 'notification_settings_v3_migrated'
                    """
                )
                if cursor.fetchone() is not None:
                    self._connection.rollback()
                    return

                cursor.execute(
                    """
                    INSERT IGNORE INTO monitor_notification_subscriptions (email, service_id)
                    SELECT recipient.email, selected.service_id
                    FROM monitor_notification_recipients AS recipient
                    CROSS JOIN monitor_notification_services AS selected
                    """
                )
                cursor.execute(
                    """
                    INSERT INTO monitor_runtime_state (state_key, state_value)
                    VALUES ('notification_settings_v3_migrated', '1')
                    ON DUPLICATE KEY UPDATE state_value = VALUES(state_value)
                    """
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

    @staticmethod
    def _service_from_row(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "name": str(row["name"]),
            "host": str(row["host"]),
            "threshold": int(row["threshold"]),
            "imageUrl": str(row.get("image_url") or ""),
            "sortOrder": int(row["sort_order"]),
            "kind": "switch" if row.get("switch_service_id") else "service",
            "snmpConfigured": bool(row.get("switch_service_id")),
            "snmpPort": int(row["snmp_port"]) if row.get("snmp_port") else None,
        }

    def load_services(self) -> list[dict[str, Any]]:
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute(
                    """
                    SELECT s.id, s.name, s.host, s.threshold, s.image_url, s.sort_order,
                           c.service_id AS switch_service_id, c.port AS snmp_port
                    FROM monitor_services AS s
                    LEFT JOIN monitor_switch_config AS c ON c.service_id = s.id
                    ORDER BY s.sort_order ASC, s.name ASC
                    """
                )
                return [self._service_from_row(row) for row in cursor.fetchall()]
            finally:
                cursor.close()

    def get_switch_config(self, service_id: str) -> dict[str, Any] | None:
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute(
                    "SELECT community, port FROM monitor_switch_config WHERE service_id = %s",
                    (service_id,),
                )
                row = cursor.fetchone()
                return {"community": row["community"], "port": int(row["port"])} if row else None
            finally:
                cursor.close()

    def save_switch_config(self, service_id: str, community: str, port: int = 161) -> None:
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute(
                    """INSERT INTO monitor_switch_config (service_id, community, port)
                       VALUES (%s, %s, %s)
                       ON DUPLICATE KEY UPDATE community = VALUES(community), port = VALUES(port)""",
                    (service_id, community, port),
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

    def remove_switch_config(self, service_id: str) -> None:
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute("DELETE FROM monitor_switch_config WHERE service_id = %s", (service_id,))
                cursor.execute("DELETE FROM monitor_switch_snapshot WHERE service_id = %s", (service_id,))
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

    def save_switch_snapshot(self, service_id: str, snapshot: dict[str, Any]) -> None:
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute(
                    """INSERT INTO monitor_switch_snapshot (service_id, collected_at, payload)
                       VALUES (%s, %s, %s)
                       ON DUPLICATE KEY UPDATE collected_at = VALUES(collected_at), payload = VALUES(payload)""",
                    (service_id, snapshot["collectedAt"], json.dumps(snapshot, ensure_ascii=False)),
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

    def load_switch_snapshot(self, service_id: str) -> dict[str, Any] | None:
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute("SELECT payload FROM monitor_switch_snapshot WHERE service_id = %s", (service_id,))
                row = cursor.fetchone()
                return json.loads(row["payload"]) if row else None
            finally:
                cursor.close()

    def save_services(self, services: list[dict[str, Any]]) -> None:
        """Upsert services without deleting rows already present in MariaDB."""
        if not services:
            return

        values = [
            (
                str(service["id"]),
                str(service["name"]),
                str(service["host"]),
                int(service.get("threshold", 100)),
                str(service.get("imageUrl", "") or ""),
                int(service.get("sortOrder", index)),
            )
            for index, service in enumerate(services)
        ]

        with self._lock:
            cursor = self._cursor()
            try:
                cursor.executemany(
                    """
                    INSERT INTO monitor_services (
                        id, name, host, threshold, image_url, sort_order
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        name = VALUES(name),
                        host = VALUES(host),
                        threshold = VALUES(threshold),
                        image_url = VALUES(image_url),
                        sort_order = VALUES(sort_order)
                    """,
                    values,
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

    def add_service(
        self,
        name: str,
        host: str,
        threshold: int = 100,
        image_url: str = "",
    ) -> dict[str, Any]:
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute("SELECT id FROM monitor_services FOR UPDATE")
                existing_ids = {str(row["id"]) for row in cursor.fetchall()}
                cursor.execute(
                    "SELECT COALESCE(MAX(sort_order), -1) + 1 AS next_sort_order FROM monitor_services"
                )
                next_sort_order = int(cursor.fetchone()["next_sort_order"])

                base = _slugify_name(name)
                service_id = base
                index = 2
                while service_id in existing_ids:
                    service_id = f"{base}-{index}"
                    index += 1

                service = {
                    "id": service_id,
                    "name": name,
                    "host": host,
                    "threshold": threshold,
                    "imageUrl": image_url,
                    "sortOrder": next_sort_order,
                }
                cursor.execute(
                    """
                    INSERT INTO monitor_services (
                        id, name, host, threshold, image_url, sort_order
                    ) VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        service["id"],
                        service["name"],
                        service["host"],
                        service["threshold"],
                        service["imageUrl"],
                        service["sortOrder"],
                    ),
                )
                self._connection.commit()
                return service
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

    def update_service(
        self,
        service_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any] | None:
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute(
                    """
                    SELECT id, name, host, threshold, image_url, sort_order
                    FROM monitor_services
                    WHERE id = %s
                    FOR UPDATE
                    """,
                    (service_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    self._connection.rollback()
                    return None

                updated = self._service_from_row(row)
                if "name" in payload:
                    name = str(payload.get("name") or "").strip()
                    if name:
                        updated["name"] = name
                if "host" in payload:
                    host = str(payload.get("host") or "").strip()
                    if host:
                        updated["host"] = host
                if "threshold" in payload:
                    threshold = payload.get("threshold")
                    if threshold in (None, ""):
                        updated["threshold"] = 100
                    else:
                        try:
                            updated_threshold = int(threshold)
                        except (TypeError, ValueError):
                            raise ValueError("Threshold must be a positive integer") from None
                        if updated_threshold < 1:
                            raise ValueError("Threshold must be a positive integer")
                        updated["threshold"] = updated_threshold
                if "imageUrl" in payload:
                    updated["imageUrl"] = str(payload.get("imageUrl") or "").strip()

                cursor.execute(
                    """
                    UPDATE monitor_services
                    SET name = %s, host = %s, threshold = %s, image_url = %s
                    WHERE id = %s
                    """,
                    (
                        updated["name"],
                        updated["host"],
                        updated["threshold"],
                        updated["imageUrl"],
                        service_id,
                    ),
                )
                self._connection.commit()
                return updated
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

    def reorder_services(self, service_ids: list[str]) -> list[dict[str, Any]]:
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute("SELECT id FROM monitor_services FOR UPDATE")
                existing_ids = {str(row["id"]) for row in cursor.fetchall()}
                incoming_ids = [str(service_id) for service_id in service_ids]
                if set(incoming_ids) != existing_ids or len(incoming_ids) != len(existing_ids):
                    raise ValueError("Service order payload must include every service exactly once")

                cursor.executemany(
                    "UPDATE monitor_services SET sort_order = %s WHERE id = %s",
                    [(index, service_id) for index, service_id in enumerate(incoming_ids)],
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

        return self.load_services()

    @staticmethod
    def _decode_samples(value: object) -> list[float]:
        if isinstance(value, list):
            return value
        try:
            parsed = json.loads(str(value or "[]"))
        except (TypeError, ValueError, json.JSONDecodeError):
            return []
        return parsed if isinstance(parsed, list) else []

    def load_history(self) -> dict[str, list[dict[str, Any]]]:
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute(
                    """
                    SELECT h.*, s.name AS service_name, s.host AS service_host,
                           s.threshold AS current_threshold
                    FROM monitor_history AS h
                    INNER JOIN monitor_services AS s ON s.id = h.service_id
                    ORDER BY h.service_id, h.timestamp ASC
                    """
                )
                rows = cursor.fetchall()
            finally:
                cursor.close()

        history: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            service_id = str(row["service_id"])
            threshold = row["service_threshold"]
            if threshold is None:
                threshold = row["current_threshold"]
            history.setdefault(service_id, []).append(
                {
                    "timestamp": str(row["timestamp"]),
                    "service": {
                        "id": service_id,
                        "name": str(row["service_name"]),
                        "host": str(row["service_host"]),
                        "threshold": None if threshold is None else int(threshold),
                        "check_type": str(row["check_type"]),
                    },
                    "check_type": str(row["check_type"]),
                    "http_status_code": row["http_status_code"],
                    "error": row["error"],
                    "online": bool(row["online"]),
                    "status": str(row["status"]),
                    "sent": int(row["sent"]),
                    "received": int(row["received"]),
                    "packet_loss_pct": float(row["packet_loss_pct"]),
                    "avg_latency_ms": row["avg_latency_ms"],
                    "min_latency_ms": row["min_latency_ms"],
                    "max_latency_ms": row["max_latency_ms"],
                    "jitter_ms": row["jitter_ms"],
                    "samples_ms": self._decode_samples(row["samples_ms"]),
                    "stability_pct": float(row["stability_pct"]),
                }
            )
        return history

    @staticmethod
    def _history_values(service_id: str, entry: dict[str, Any]) -> tuple[Any, ...]:
        service = entry.get("service") or {}
        service_threshold = service.get("threshold")
        check_type = entry.get("check_type") or service.get("check_type") or "ping"
        return (
            service_id,
            str(entry["timestamp"]),
            int(bool(entry["online"])),
            str(entry["status"]),
            int(entry["sent"]),
            int(entry["received"]),
            float(entry["packet_loss_pct"]),
            None if entry.get("avg_latency_ms") is None else float(entry["avg_latency_ms"]),
            None if entry.get("min_latency_ms") is None else float(entry["min_latency_ms"]),
            None if entry.get("max_latency_ms") is None else float(entry["max_latency_ms"]),
            None if entry.get("jitter_ms") is None else float(entry["jitter_ms"]),
            json.dumps(entry.get("samples_ms", []), ensure_ascii=False),
            float(entry.get("stability_pct", 0.0)),
            None if service_threshold is None else int(service_threshold),
            str(check_type),
            None if entry.get("http_status_code") is None else int(entry["http_status_code"]),
            None if entry.get("error") is None else str(entry["error"]),
        )

    @staticmethod
    def _history_insert_sql(upsert: bool = False) -> str:
        sql = """
            INSERT INTO monitor_history (
                service_id, timestamp, online, status, sent, received,
                packet_loss_pct, avg_latency_ms, min_latency_ms, max_latency_ms,
                jitter_ms, samples_ms, stability_pct, service_threshold,
                check_type, http_status_code, error
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        if upsert:
            sql += """
                ON DUPLICATE KEY UPDATE
                    online = VALUES(online), status = VALUES(status),
                    sent = VALUES(sent), received = VALUES(received),
                    packet_loss_pct = VALUES(packet_loss_pct),
                    avg_latency_ms = VALUES(avg_latency_ms),
                    min_latency_ms = VALUES(min_latency_ms),
                    max_latency_ms = VALUES(max_latency_ms),
                    jitter_ms = VALUES(jitter_ms), samples_ms = VALUES(samples_ms),
                    stability_pct = VALUES(stability_pct),
                    service_threshold = VALUES(service_threshold),
                    check_type = VALUES(check_type),
                    http_status_code = VALUES(http_status_code), error = VALUES(error)
            """
        return sql

    def append_history_entry(
        self,
        entry: dict[str, Any],
        max_entries: int,
        stability_window: int,
    ) -> dict[str, Any] | None:
        service_id = str(entry["service"]["id"])
        window = max(1, stability_window)

        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute(
                    "SELECT threshold FROM monitor_services WHERE id = %s",
                    (service_id,),
                )
                service_row = cursor.fetchone()
                if service_row is None:
                    self._connection.rollback()
                    return None

                cursor.execute(
                    """
                    SELECT online
                    FROM monitor_history
                    WHERE service_id = %s
                    ORDER BY timestamp DESC
                    LIMIT %s
                    """,
                    (service_id, max(0, window - 1)),
                )
                recent_rows = cursor.fetchall()
                online_flags = [bool(row["online"]) for row in reversed(recent_rows)]
                online_flags.append(bool(entry["online"]))
                stability_pct = round((sum(online_flags) / len(online_flags)) * 100, 2)

                persisted_entry = {
                    **entry,
                    "service": {
                        **entry["service"],
                        "threshold": int(service_row["threshold"]),
                    },
                    "check_type": entry.get("check_type", "ping"),
                    "http_status_code": entry.get("http_status_code"),
                    "error": entry.get("error"),
                    "stability_pct": stability_pct,
                }
                cursor.execute(
                    self._history_insert_sql(),
                    self._history_values(service_id, persisted_entry),
                )

                if max_entries > 0:
                    cursor.execute(
                        """
                        SELECT id
                        FROM monitor_history
                        WHERE service_id = %s
                        ORDER BY timestamp DESC
                        LIMIT %s, 18446744073709551615
                        """,
                        (service_id, max_entries),
                    )
                    stale_ids = [int(row["id"]) for row in cursor.fetchall()]
                    if stale_ids:
                        placeholders = ", ".join(["%s"] * len(stale_ids))
                        cursor.execute(
                            f"DELETE FROM monitor_history WHERE id IN ({placeholders})",
                            tuple(stale_ids),
                        )

                self._connection.commit()
                return persisted_entry
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

    def import_history_entries(
        self,
        entries: Iterable[tuple[str, dict[str, Any]]],
        batch_size: int = 500,
    ) -> int:
        batch: list[tuple[Any, ...]] = []
        imported = 0

        with self._lock:
            cursor = self._cursor()
            try:
                for service_id, entry in entries:
                    batch.append(self._history_values(str(service_id), entry))
                    if len(batch) >= batch_size:
                        cursor.executemany(self._history_insert_sql(upsert=True), batch)
                        imported += len(batch)
                        batch.clear()
                if batch:
                    cursor.executemany(self._history_insert_sql(upsert=True), batch)
                    imported += len(batch)
                self._connection.commit()
                return imported
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

    def load_notification_settings(self) -> dict[str, Any]:
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute(
                    "SELECT enabled FROM monitor_notification_settings WHERE id = 1"
                )
                row = cursor.fetchone()
                cursor.execute(
                    """
                    SELECT recipient.email, subscription.service_id
                    FROM monitor_notification_recipients AS recipient
                    LEFT JOIN monitor_notification_subscriptions AS subscription
                        ON subscription.email = recipient.email
                    LEFT JOIN monitor_services AS service
                        ON service.id = subscription.service_id
                    ORDER BY recipient.email, service.sort_order, service.name
                    """
                )
                subscription_rows = cursor.fetchall()
            finally:
                cursor.close()
                self._connection.rollback()

        subscriptions_by_email: dict[str, list[str]] = {}
        for item in subscription_rows:
            email = str(item["email"])
            subscriptions_by_email.setdefault(email, [])
            if item["service_id"] is not None:
                subscriptions_by_email[email].append(str(item["service_id"]))

        subscriptions = [
            {"email": email, "serviceIds": service_ids}
            for email, service_ids in subscriptions_by_email.items()
        ]
        recipients = [subscription["email"] for subscription in subscriptions]
        service_ids = list(
            dict.fromkeys(
                service_id
                for subscription in subscriptions
                for service_id in subscription["serviceIds"]
            )
        )
        return {
            "enabled": bool(row["enabled"]) if row else False,
            "subscriptions": subscriptions,
            "recipients": recipients,
            "serviceIds": service_ids,
            "recipient": recipients[0] if recipients else "",
        }

    def save_notification_settings(
        self,
        enabled: bool,
        subscriptions_or_recipients: list[dict[str, Any]] | list[str] | str,
        service_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            cursor = self._cursor()
            try:
                if isinstance(subscriptions_or_recipients, str):
                    recipients = (
                        [subscriptions_or_recipients]
                        if subscriptions_or_recipients.strip()
                        else []
                    )
                    raw_subscriptions: list[dict[str, Any]] | None = None
                elif all(isinstance(item, str) for item in subscriptions_or_recipients):
                    recipients = [str(item) for item in subscriptions_or_recipients]
                    raw_subscriptions = None
                else:
                    recipients = []
                    raw_subscriptions = [
                        dict(item) for item in subscriptions_or_recipients if isinstance(item, dict)
                    ]

                if raw_subscriptions is None:
                    if service_ids is None:
                        cursor.execute("SELECT id FROM monitor_services ORDER BY sort_order, name")
                        selected_service_ids = [str(row["id"]) for row in cursor.fetchall()]
                    else:
                        selected_service_ids = list(
                            dict.fromkeys(str(item) for item in service_ids)
                        )
                    raw_subscriptions = [
                        {"email": recipient, "serviceIds": selected_service_ids}
                        for recipient in recipients
                    ]

                subscriptions_by_key: dict[str, dict[str, Any]] = {}
                for subscription in raw_subscriptions:
                    email = str(subscription.get("email") or "").strip()
                    if not email:
                        continue
                    key = email.lower()
                    normalized = subscriptions_by_key.setdefault(
                        key,
                        {"email": email, "serviceIds": []},
                    )
                    normalized["serviceIds"] = list(
                        dict.fromkeys(
                            [
                                *normalized["serviceIds"],
                                *[
                                    str(item)
                                    for item in subscription.get("serviceIds", [])
                                ],
                            ]
                        )
                    )

                normalized_subscriptions = list(subscriptions_by_key.values())
                normalized_recipients = [
                    subscription["email"] for subscription in normalized_subscriptions
                ]
                normalized_service_ids = list(
                    dict.fromkeys(
                        service_id
                        for subscription in normalized_subscriptions
                        for service_id in subscription["serviceIds"]
                    )
                )

                cursor.execute(
                    """
                    INSERT INTO monitor_notification_settings (id, enabled, recipient)
                    VALUES (1, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        enabled = VALUES(enabled), recipient = VALUES(recipient)
                    """,
                    (
                        int(enabled),
                        normalized_recipients[0] if normalized_recipients else "",
                    ),
                )
                cursor.execute("DELETE FROM monitor_notification_subscriptions")
                cursor.execute("DELETE FROM monitor_notification_recipients")
                if normalized_recipients:
                    cursor.executemany(
                        "INSERT INTO monitor_notification_recipients (email) VALUES (%s)",
                        [(recipient,) for recipient in normalized_recipients],
                    )

                cursor.execute("DELETE FROM monitor_notification_services")
                if normalized_service_ids:
                    cursor.executemany(
                        """
                        INSERT INTO monitor_notification_services (service_id)
                        VALUES (%s)
                        """,
                        [(service_id,) for service_id in normalized_service_ids],
                    )
                subscription_values = [
                    (subscription["email"], service_id)
                    for subscription in normalized_subscriptions
                    for service_id in subscription["serviceIds"]
                ]
                if subscription_values:
                    cursor.executemany(
                        """
                        INSERT INTO monitor_notification_subscriptions (email, service_id)
                        VALUES (%s, %s)
                        """,
                        subscription_values,
                    )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()
        return {
            "enabled": enabled,
            "subscriptions": normalized_subscriptions,
            "recipients": normalized_recipients,
            "serviceIds": normalized_service_ids,
            "recipient": normalized_recipients[0] if normalized_recipients else "",
        }

    def get_or_create_notification_incident(
        self,
        service_id: str,
        offline_since: datetime,
    ) -> dict[str, str | None]:
        offline_since_text = offline_since.astimezone(timezone.utc).isoformat()
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute(
                    """
                    INSERT IGNORE INTO monitor_notification_incidents (
                        service_id, offline_since, notified_at
                    ) VALUES (%s, %s, NULL)
                    """,
                    (service_id, offline_since_text),
                )
                cursor.execute(
                    """
                    SELECT offline_since, notified_at
                    FROM monitor_notification_incidents
                    WHERE service_id = %s
                    """,
                    (service_id,),
                )
                row = cursor.fetchone()
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

        if row is None:
            raise RuntimeError(f"Unable to create notification incident for {service_id}")
        return {
            "offlineSince": str(row["offline_since"]),
            "notifiedAt": None if row["notified_at"] is None else str(row["notified_at"]),
        }

    def import_notification_incidents(self, incidents: list[dict[str, Any]]) -> None:
        if not incidents:
            return
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.executemany(
                    """
                    INSERT INTO monitor_notification_incidents (
                        service_id, offline_since, notified_at
                    ) VALUES (%s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        offline_since = VALUES(offline_since),
                        notified_at = VALUES(notified_at)
                    """,
                    [
                        (
                            str(incident["service_id"]),
                            str(incident["offline_since"]),
                            incident.get("notified_at"),
                        )
                        for incident in incidents
                    ],
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

    def mark_notification_sent(self, service_id: str, notified_at: datetime) -> None:
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute(
                    """
                    UPDATE monitor_notification_incidents
                    SET notified_at = %s
                    WHERE service_id = %s
                    """,
                    (notified_at.astimezone(timezone.utc).isoformat(), service_id),
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

    def clear_notification_incident(self, service_id: str) -> None:
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute(
                    "DELETE FROM monitor_notification_incidents WHERE service_id = %s",
                    (service_id,),
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

    def clear_history(self) -> None:
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute("DELETE FROM monitor_history")
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

    def delete_history_before(self, cutoff: datetime) -> int:
        cutoff_text = cutoff.astimezone(timezone.utc).isoformat()
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute(
                    "DELETE FROM monitor_history WHERE timestamp < %s",
                    (cutoff_text,),
                )
                deleted = cursor.rowcount
                self._connection.commit()
                return int(deleted)
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

    def has_history(self) -> bool:
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute("SELECT 1 FROM monitor_history LIMIT 1")
                return cursor.fetchone() is not None
            finally:
                cursor.close()

    def delete_service(self, service_id: str) -> bool:
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute("DELETE FROM monitor_services WHERE id = %s", (service_id,))
                removed = cursor.rowcount > 0
                self._connection.commit()
                return removed
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

    def get_last_reset(self) -> datetime | None:
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute(
                    "SELECT state_value FROM monitor_runtime_state WHERE state_key = 'last_history_prune'"
                )
                row = cursor.fetchone()
            finally:
                cursor.close()
        if not row:
            return None
        try:
            return datetime.fromisoformat(str(row["state_value"]))
        except ValueError:
            return None

    def set_last_reset(self, ts: datetime) -> None:
        value = ts.astimezone(timezone.utc).isoformat()
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute(
                    """
                    INSERT INTO monitor_runtime_state (state_key, state_value)
                    VALUES ('last_history_prune', %s)
                    ON DUPLICATE KEY UPDATE state_value = VALUES(state_value)
                    """,
                    (value,),
                )
                self._connection.commit()
            except Exception:
                self._connection.rollback()
                raise
            finally:
                cursor.close()

    def count_rows(self, table: str) -> int:
        table_name = self.TABLES.get(table)
        if table_name is None:
            raise ValueError(f"Unknown storage table: {table}")
        with self._lock:
            cursor = self._cursor()
            try:
                cursor.execute(f"SELECT COUNT(*) AS total FROM {table_name}")
                return int(cursor.fetchone()["total"])
            finally:
                cursor.close()

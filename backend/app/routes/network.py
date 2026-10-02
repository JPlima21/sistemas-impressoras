"""Flask API for the network monitor, hosted beside the printer API."""

from __future__ import annotations

import logging
import os
from email.utils import parseaddr

import pymysql
from flask import Blueprint, jsonify, request

from network.audit import MariaDBAuditStorage
from network.dashboard import build_dashboard_data
from network.mariadb_storage import MariaDBStorage
from network.monitor import MonitorService


LOGGER = logging.getLogger(__name__)


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _threshold(value: object) -> int:
    if value in (None, ""):
        return 100
    try:
        result = int(value)
    except (TypeError, ValueError):
        raise ValueError("Threshold must be a positive integer") from None
    if result < 1:
        raise ValueError("Threshold must be a positive integer")
    return result


def _valid_email(value: str) -> bool:
    if not value or len(value) > 320 or "\r" in value or "\n" in value:
        return False
    _, address = parseaddr(value)
    local, separator, domain = address.rpartition("@")
    return address == value and bool(local and separator and "." in domain)


def _payload() -> dict:
    data = request.get_json(silent=True)
    return data if isinstance(data, dict) else {}


def _switch_settings(data: dict, existing: dict | None = None) -> tuple[str, int]:
    raw_community = data.get("snmpCommunity")
    if raw_community is not None and not isinstance(raw_community, str):
        raise ValueError("A community SNMP deve ser um texto.")
    community = (raw_community or "").strip()
    if not community and existing:
        community = existing["community"]
    if not community or len(community) > 255:
        raise ValueError("Informe uma community SNMPv2c válida (até 255 caracteres).")
    try:
        raw_port = data.get("snmpPort")
        port = int(raw_port if raw_port not in (None, "") else (existing["port"] if existing else 161))
    except (TypeError, ValueError):
        raise ValueError("A porta SNMP deve estar entre 1 e 65535.") from None
    if not 1 <= port <= 65535:
        raise ValueError("A porta SNMP deve estar entre 1 e 65535.")
    return community, port


def _service_kind(data: dict, current: str = "service") -> str:
    kind = data.get("kind", current)
    if not isinstance(kind, str) or kind not in {"service", "switch"}:
        raise ValueError("O tipo deve ser serviço ou switch.")
    return kind


def create_network_monitor():
    """Use the shared database unless NETWORK_MARIADB_* selects the old one."""
    database = os.getenv("NETWORK_MARIADB_DATABASE") or os.getenv("MARIADB_DATABASE")
    if not database:
        LOGGER.warning("Network monitor disabled: MariaDB database is not configured")
        return None, None, None

    try:
        storage = MariaDBStorage()
        audit = MariaDBAuditStorage()
    except (pymysql.MySQLError, RuntimeError):
        LOGGER.exception("Network monitor could not connect to MariaDB")
        return None, None, None
    monitor = MonitorService(
        storage=storage,
        audit_storage=audit,
        interval_seconds=_env_int("NETWORK_MONITOR_INTERVAL_SECONDS", 5),
        ping_count=_env_int("NETWORK_PING_COUNT", 4),
        timeout_ms=_env_int("NETWORK_PING_TIMEOUT_MS", 1000),
        stability_window=_env_int("NETWORK_STABILITY_WINDOW", 20),
        max_entries=_env_int("NETWORK_MAX_ENTRIES", 1000),
        ping_concurrency=_env_int("NETWORK_PING_CONCURRENCY", 8),
        history_retention_days=_env_int("NETWORK_HISTORY_RETENTION_DAYS", 1),
        history_prune_interval_seconds=_env_int("NETWORK_HISTORY_PRUNE_INTERVAL_SECONDS", 3600, 60),
        snmp_interval_seconds=_env_int("NETWORK_SNMP_INTERVAL_SECONDS", 60, 5),
    )
    return storage, audit, monitor


def create_network_blueprint(storage, audit, monitor):
    bp = Blueprint("network", __name__, url_prefix="/api/rede")

    @bp.before_request
    def require_network_monitor():
        if monitor is None:
            return jsonify({"error": "Configure o MariaDB para ativar o monitor de rede."}), 503
        return None

    def dashboard():
        return build_dashboard_data(
            storage.load_services(), storage.load_history(),
            next_update_seconds=monitor.interval_seconds,
        )

    @bp.get("/dashboard")
    def get_dashboard():
        return jsonify(dashboard())

    @bp.get("/status")
    def get_status():
        return jsonify(dashboard()["services"])

    @bp.get("/history")
    def get_history():
        return jsonify(dashboard()["history"])

    @bp.get("/services")
    def get_services():
        return jsonify(storage.load_services())

    @bp.post("/services")
    def add_service():
        data = _payload()
        name = str(data.get("name") or "").strip()
        host = str(data.get("host") or "").strip()
        if not name or not host:
            return jsonify({"error": "Name and host are required"}), 400
        try:
            kind = _service_kind(data)
            if kind == "switch" and "://" in host:
                raise ValueError("Informe o IP ou nome de gerenciamento do switch, sem URL.")
            switch = _switch_settings(data) if kind == "switch" else None
            threshold = _threshold(data.get("threshold"))
            service = storage.add_service(
                name=name, host=host, threshold=threshold,
                image_url=str(data.get("imageUrl") or "").strip(),
            )
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if switch:
            try:
                storage.save_switch_config(service["id"], *switch)
            except Exception:
                storage.delete_service(service["id"])
                raise
            service["kind"] = "switch"
            service["snmpConfigured"] = True
            service["snmpPort"] = switch[1]
        else:
            service.update({"kind": "service", "snmpConfigured": False, "snmpPort": None})
        monitor.run_cycle({service["id"]})
        return jsonify({"message": "Service added", "service": service}), 201

    @bp.put("/services/reorder")
    def reorder_services():
        ids = _payload().get("serviceIds")
        if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
            return jsonify({"error": "serviceIds must be a list of strings"}), 400
        try:
            services = storage.reorder_services(ids)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        return jsonify({"message": "Service order updated", "services": services})

    @bp.put("/services/<service_id>")
    def update_service(service_id):
        data = _payload()
        try:
            current = next((item for item in storage.load_services() if item["id"] == service_id), None)
            if current is None:
                return jsonify({"error": "Service not found"}), 404
            kind = _service_kind(data, current["kind"])
            host = str(data.get("host") or current["host"]).strip()
            if kind == "switch" and "://" in host:
                raise ValueError("Informe o IP ou nome de gerenciamento do switch, sem URL.")
            existing_switch = storage.get_switch_config(service_id)
            switch = _switch_settings(data, existing_switch) if kind == "switch" else None
            if "threshold" in data:
                data["threshold"] = _threshold(data["threshold"])
            service = storage.update_service(service_id, data)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        if service is None:
            return jsonify({"error": "Service not found"}), 404
        if switch:
            storage.save_switch_config(service_id, *switch)
            service["kind"] = "switch"
            service["snmpConfigured"] = True
            service["snmpPort"] = switch[1]
            monitor._last_switch_poll.pop(service_id, None)
        elif existing_switch:
            storage.remove_switch_config(service_id)
            service["kind"] = "service"
            service["snmpConfigured"] = False
            service["snmpPort"] = None
            monitor._last_switch_poll.pop(service_id, None)
        monitor.run_cycle({service_id})
        return jsonify({"message": "Service updated", "service": service})

    @bp.get("/services/<service_id>/switch")
    def get_switch_snapshot(service_id):
        if storage.get_switch_config(service_id) is None:
            return jsonify({"error": "Switch não encontrado."}), 404
        return jsonify(storage.load_switch_snapshot(service_id))

    @bp.delete("/services/<service_id>")
    def delete_service(service_id):
        if not storage.delete_service(service_id):
            return jsonify({"error": "Service not found"}), 404
        monitor.current_status.pop(service_id, None)
        monitor._last_switch_poll.pop(service_id, None)
        return jsonify({"message": "Service removed"})

    @bp.get("/audit")
    def get_audit():
        return jsonify(audit.load_events())

    @bp.get("/settings/notifications")
    def get_notifications():
        return jsonify({
            **storage.load_notification_settings(),
            "outageThresholdMinutes": monitor.notification_service.outage_threshold_minutes,
            "smtpConfigured": monitor.notification_service.smtp_configured,
        })

    @bp.put("/settings/notifications")
    def put_notifications():
        data = _payload()
        enabled = data.get("enabled")
        if not isinstance(enabled, bool):
            return jsonify({"error": "O campo enabled deve ser verdadeiro ou falso."}), 400

        service_ids = {str(service["id"]) for service in storage.load_services()}
        subscriptions = data.get("subscriptions")
        if subscriptions is None:
            recipients = data.get("recipients")
            if recipients is None:
                recipient = str(data.get("recipient") or "").strip()
                recipients = [recipient] if recipient else []
            selected = data.get("serviceIds", list(service_ids))
            if not isinstance(recipients, list) or not all(isinstance(x, str) for x in recipients):
                return jsonify({"error": "O campo recipients deve ser uma lista de e-mails."}), 400
            if not isinstance(selected, list) or not all(isinstance(x, str) for x in selected):
                return jsonify({"error": "O campo serviceIds deve ser uma lista de identificadores."}), 400
            subscriptions = [{"email": email, "serviceIds": selected} for email in recipients]

        if not isinstance(subscriptions, list) or not all(isinstance(x, dict) for x in subscriptions):
            return jsonify({"error": "O campo subscriptions deve ser uma lista de assinaturas."}), 400

        by_email = {}
        for item in subscriptions:
            email = str(item.get("email") or "").strip()
            selected = item.get("serviceIds")
            if not _valid_email(email):
                return jsonify({"error": f"E-mail inválido: {email or '(vazio)'}"}), 400
            if not isinstance(selected, list) or not all(isinstance(x, str) for x in selected):
                return jsonify({"error": f"Seleção de aplicações inválida para {email}."}), 400
            entry = by_email.setdefault(email.lower(), {"email": email, "serviceIds": []})
            entry["serviceIds"] = list(dict.fromkeys([*entry["serviceIds"], *selected]))

        subscriptions = list(by_email.values())
        if len(subscriptions) > 50:
            return jsonify({"error": "Informe no máximo 50 destinatários."}), 400
        if any(x not in service_ids for item in subscriptions for x in item["serviceIds"]):
            return jsonify({"error": "Uma ou mais aplicações selecionadas não existem."}), 400
        if enabled and not subscriptions:
            return jsonify({"error": "Informe pelo menos um e-mail que receberá os alertas."}), 400
        if enabled:
            empty = next((item for item in subscriptions if not item["serviceIds"]), None)
            if empty:
                return jsonify({"error": f"Selecione pelo menos uma aplicação para {empty['email']}."}), 400
            if not monitor.notification_service.smtp_configured:
                return jsonify({"error": "Configure o servidor SMTP antes de ativar os alertas."}), 400

        settings = storage.save_notification_settings(enabled, subscriptions)
        return jsonify({
            "message": "Configurações de notificação atualizadas.", **settings,
            "outageThresholdMinutes": monitor.notification_service.outage_threshold_minutes,
            "smtpConfigured": monitor.notification_service.smtp_configured,
        })

    return bp

from __future__ import annotations

import logging
import os
import smtplib
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from html import escape
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .mariadb_storage import MariaDBStorage


LOGGER = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value in (None, ""):
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return max(minimum, value)


def _notification_timezone() -> timezone | ZoneInfo:
    timezone_name = (
        os.getenv("NOTIFICATION_TIMEZONE", "").strip()
        or os.getenv("TZ", "").strip()
        or "America/Fortaleza"
    )
    try:
        return ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError:
        # Fortaleza has used UTC-03:00 continuously throughout the period
        # covered by MonitorNet. This also keeps slim images without tzdata safe.
        return timezone(timedelta(hours=-3))


def _format_notification_datetime(value: datetime) -> str:
    local_value = value.astimezone(_notification_timezone())
    raw_offset = local_value.strftime("%z")
    offset = (
        f"{raw_offset[:3]}:{raw_offset[3:]}"
        if len(raw_offset) == 5
        else raw_offset
    )
    return f"{local_value.strftime('%d/%m/%Y às %H:%M')} (UTC{offset})"


class SmtpEmailSender:
    """Send outage messages using SMTP settings supplied by the environment."""

    def __init__(self) -> None:
        self.host = os.getenv("SMTP_HOST", "").strip()
        self.port = _env_int("SMTP_PORT", 587)
        self.username = os.getenv("SMTP_USERNAME", "").strip()
        self.password = os.getenv("SMTP_PASSWORD", "")
        self.from_email = os.getenv("SMTP_FROM_EMAIL", "").strip() or self.username
        self.use_tls = _env_bool("SMTP_USE_TLS", True)
        self.use_ssl = _env_bool("SMTP_USE_SSL", False)
        self.timeout_seconds = _env_int("SMTP_TIMEOUT_SECONDS", 10)

    @property
    def is_configured(self) -> bool:
        return bool(self.host and self.from_email)

    def send_outage_alert(
        self,
        recipients: list[str],
        service: dict[str, Any],
        offline_since: datetime,
        outage_duration: timedelta,
    ) -> None:
        if not self.is_configured:
            raise RuntimeError("SMTP is not configured")

        service_name = str(service.get("name") or service.get("id") or "Serviço")
        host = str(service.get("host") or "-")
        duration_minutes = max(1, int(outage_duration.total_seconds() // 60))
        started_at = _format_notification_datetime(offline_since)

        message = EmailMessage()
        message["Subject"] = f"[MonitorNet] {service_name} está offline"
        message["From"] = self.from_email
        message["To"] = ", ".join(recipients)
        message.set_content(
            "\n".join(
                [
                    f'O serviço "{service_name}" não responde há {duration_minutes} minutos.',
                    f"Endereço monitorado: {host}",
                    f"Início da indisponibilidade: {started_at}",
                    "",
                    "Este alerta será enviado apenas uma vez durante esta indisponibilidade.",
                ]
            )
        )
        message.add_alternative(
            f"""
            <html><body style="font-family:Arial,sans-serif;color:#172033">
              <h2>Serviço indisponível</h2>
              <p>O serviço <strong>{escape(service_name)}</strong> não responde há
                 <strong>{duration_minutes} minutos</strong>.</p>
              <p><strong>Endereço:</strong> {escape(host)}<br>
                 <strong>Início:</strong> {escape(started_at)}</p>
              <p style="color:#667085">O MonitorNet enviará apenas um alerta durante esta indisponibilidade.</p>
            </body></html>
            """,
            subtype="html",
        )

        smtp_class = smtplib.SMTP_SSL if self.use_ssl else smtplib.SMTP
        with smtp_class(self.host, self.port, timeout=self.timeout_seconds) as smtp:
            if self.use_tls and not self.use_ssl:
                smtp.starttls()
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(message)


class NotificationService:
    """Track continuous outages and send one alert for each outage incident."""

    def __init__(
        self,
        storage: MariaDBStorage,
        sender: SmtpEmailSender | None = None,
        outage_threshold: timedelta | None = None,
    ) -> None:
        self.storage = storage
        self.sender = sender or SmtpEmailSender()
        self.outage_threshold = outage_threshold or timedelta(
            minutes=_env_int("NOTIFICATION_OUTAGE_MINUTES", 30)
        )

    @property
    def smtp_configured(self) -> bool:
        return self.sender.is_configured

    @property
    def outage_threshold_minutes(self) -> int:
        return max(1, int(self.outage_threshold.total_seconds() // 60))

    def process_entry(self, entry: dict[str, Any]) -> None:
        service = entry["service"]
        service_id = str(service["id"])

        if entry.get("online"):
            self.storage.clear_notification_incident(service_id)
            return

        checked_at = self._parse_timestamp(entry.get("timestamp"))
        incident = self.storage.get_or_create_notification_incident(service_id, checked_at)
        offline_since = self._parse_timestamp(incident["offlineSince"])

        if incident.get("notifiedAt") or checked_at - offline_since < self.outage_threshold:
            return

        settings = self.storage.load_notification_settings()
        if not settings["enabled"]:
            return

        subscriptions = settings.get("subscriptions")
        if subscriptions is not None:
            recipients = list(
                dict.fromkeys(
                    str(subscription.get("email") or "").strip()
                    for subscription in subscriptions
                    if service_id in subscription.get("serviceIds", [])
                    and str(subscription.get("email") or "").strip()
                )
            )
        else:
            recipients = settings.get("recipients")
            if recipients is None:
                legacy_recipient = str(settings.get("recipient") or "").strip()
                recipients = [legacy_recipient] if legacy_recipient else []
            selected_services = settings.get("serviceIds")
            if selected_services is not None and service_id not in selected_services:
                recipients = []

        if not recipients:
            return

        try:
            self.sender.send_outage_alert(
                [str(recipient) for recipient in recipients],
                service,
                offline_since,
                checked_at - offline_since,
            )
        except Exception:
            LOGGER.exception("Failed to send outage alert for service %s", service_id)
            return

        self.storage.mark_notification_sent(service_id, checked_at)

    @staticmethod
    def _parse_timestamp(value: object) -> datetime:
        try:
            parsed = datetime.fromisoformat(str(value))
        except (TypeError, ValueError):
            return datetime.now(timezone.utc)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)

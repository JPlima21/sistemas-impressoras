import os
HISTORICO_FECHAMENTO_DIARIO = os.getenv("HISTORICO_FECHAMENTO_DIARIO", "23:59")
CORS_ORIGINS = [
    origem.strip()
    for origem in os.getenv("CORS_ORIGINS", "").split(",")
    if origem.strip()
]

MONITOR_INTERVAL_SECONDS = 5
STATE_PERSIST_INTERVAL_SECONDS = int(os.getenv("STATE_PERSIST_INTERVAL_SECONDS", "60"))
PRINTER_CACHE_PERSIST_INTERVAL_SECONDS = int(
    os.getenv("PRINTER_CACHE_PERSIST_INTERVAL_SECONDS", "300")
)
SNMP_STABLE_REFRESH_INTERVAL_SECONDS = int(
    os.getenv("SNMP_STABLE_REFRESH_INTERVAL_SECONDS", "300")
)

MARIADB_HOST = os.getenv("MARIADB_HOST", "localhost")
MARIADB_PORT = int(os.getenv("MARIADB_PORT", "3306"))
MARIADB_USER = os.getenv("MARIADB_USER", "MonitorUser")
MARIADB_PASSWORD = os.getenv("MARIADB_PASSWORD", "")
MARIADB_DATABASE = os.getenv("MARIADB_DATABASE", "")
MARIADB_CONNECT_TIMEOUT = int(os.getenv("MARIADB_CONNECT_TIMEOUT", "5"))
MARIADB_SOCKET = os.getenv("MARIADB_SOCKET", "")

SNMP_OIDS = {
    "location": "1.3.6.1.2.1.1.6.0",
    "uptime": "1.3.6.1.2.1.1.3.0",
    "nome": "1.3.6.1.2.1.1.5.0",
    "serial": "1.3.6.1.2.1.43.5.1.1.17.1",
    "modelo": "1.3.6.1.2.1.25.3.2.1.3.1",
    "asset_number": "1.3.6.1.4.1.2001.1.1.1.1.11.1.10.40.2.0",
    "total_impressoes": "1.3.6.1.2.1.43.10.2.1.4.1.1",
    "impressoes": "1.3.6.1.4.1.2001.1.1.1.1.11.1.10.170.1.21.3",
    "copias": "1.3.6.1.4.1.2001.1.1.1.1.11.1.10.170.1.17.1",
    "toner_capacidade": "1.3.6.1.2.1.43.11.1.1.8.1.1",
    "toner": "1.3.6.1.2.1.43.11.1.1.9.1.1",
    "status": "1.3.6.1.2.1.43.16.5.1.2.1.1",
    "alertas": "1.3.6.1.2.1.43.18.1.1",
    "scanner": "1.3.6.1.4.1.2001.1.1.4.2.1.3.11.0",
    "mac": "1.3.6.1.2.1.2.2.1.6.1",
    "samsung_contador_tipo": "1.3.6.1.4.1.236.11.5.11.53.11.2.1.2.1",
    "samsung_contador_valor": "1.3.6.1.4.1.236.11.5.11.53.11.2.1.7.1",
}

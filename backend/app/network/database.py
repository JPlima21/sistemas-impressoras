from __future__ import annotations

import os

import pymysql
from pymysql.cursors import DictCursor


def connect_mariadb() -> pymysql.Connection:
    """Create a MariaDB connection from the shared application environment."""
    settings = {
        name: os.getenv(f"NETWORK_{name}") or os.getenv(name, "")
        for name in ("MARIADB_HOST", "MARIADB_USER", "MARIADB_PASSWORD", "MARIADB_DATABASE")
    }
    missing = [name for name, value in settings.items() if not value]
    if missing:
        raise RuntimeError(f"Configuração MariaDB ausente: {', '.join(missing)}")

    return pymysql.connect(
        host=settings["MARIADB_HOST"],
        port=int(os.getenv("NETWORK_MARIADB_PORT") or os.getenv("MARIADB_PORT", "3306")),
        user=settings["MARIADB_USER"],
        password=settings["MARIADB_PASSWORD"],
        database=settings["MARIADB_DATABASE"],
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
        connect_timeout=10,
        read_timeout=30,
        write_timeout=30,
    )

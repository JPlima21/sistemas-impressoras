from config import (
    MARIADB_CONNECT_TIMEOUT,
    MARIADB_DATABASE,
    MARIADB_HOST,
    MARIADB_PASSWORD,
    MARIADB_PORT,
    MARIADB_SOCKET,
    MARIADB_USER,
)
from services.mariadb_service import testar_conexao_mariadb


# Executa um teste manual de conexão com o MariaDB usando as variáveis de ambiente
def main():
    config = {
        "host": MARIADB_HOST,
        "port": MARIADB_PORT,
        "user": MARIADB_USER,
        "password": MARIADB_PASSWORD,
        "database": MARIADB_DATABASE,
        "connect_timeout": MARIADB_CONNECT_TIMEOUT,
        "socket": MARIADB_SOCKET,
    }

    try:
        versao = testar_conexao_mariadb(config)
    except Exception as exc:
        print(f"Falha ao conectar no MariaDB: {exc}")
        raise SystemExit(1) from exc

    database = MARIADB_DATABASE or "(sem database selecionado)"
    destino = MARIADB_SOCKET or f"{MARIADB_HOST}:{MARIADB_PORT}"
    print(f"Conexao MariaDB OK: {destino} / {database}")
    print(f"Versao do servidor: {versao}")


if __name__ == "__main__":
    main()

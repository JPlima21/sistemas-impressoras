import pymysql


# Abre uma conexão com o MariaDB usando host/porta ou socket Unix conforme a configuração
def obter_conexao_mariadb(config):
    database = config.get("database") or None
    socket = config.get("socket") or None

    parametros = {
        "user": config["user"],
        "password": config["password"],
        "database": database,
        "connect_timeout": config["connect_timeout"],
        "charset": "utf8mb4",
        "cursorclass": pymysql.cursors.DictCursor,
    }

    if socket:
        parametros["unix_socket"] = socket
    else:
        parametros["host"] = config["host"]
        parametros["port"] = config["port"]

    return pymysql.connect(**parametros)


# Executa uma consulta SELECT e devolve todas as linhas como dicionários
def executar_consulta_mariadb(config, sql, parametros=None):
    with obter_conexao_mariadb(config) as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(sql, parametros or ())
            return cursor.fetchall()


# Testa a conexão com o MariaDB retornando a versão do servidor
def testar_conexao_mariadb(config):
    with obter_conexao_mariadb(config) as conexao:
        with conexao.cursor() as cursor:
            cursor.execute("SELECT VERSION() AS versao")
            resultado = cursor.fetchone()

    return resultado["versao"]


# Lista as tabelas disponíveis no banco configurado
def listar_tabelas_mariadb(config):
    if not config.get("database"):
        return []

    return executar_consulta_mariadb(
        config,
        """
        SELECT table_name AS nome
        FROM information_schema.tables
        WHERE table_schema = %s
        ORDER BY table_name
        """,
        (config["database"],),
    )


# Lista as colunas de uma tabela para diagnóstico da estrutura do banco
def listar_colunas_tabela_mariadb(config, tabela):
    if not config.get("database"):
        return []

    return executar_consulta_mariadb(
        config,
        """
        SELECT
            column_name AS nome,
            data_type AS tipo,
            is_nullable AS permite_nulo,
            column_key AS chave,
            column_default AS valor_padrao,
            extra
        FROM information_schema.columns
        WHERE table_schema = %s AND table_name = %s
        ORDER BY ordinal_position
        """,
        (config["database"], tabela),
    )

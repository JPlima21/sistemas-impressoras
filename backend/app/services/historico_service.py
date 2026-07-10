from datetime import datetime
from config import (
    MARIADB_CONNECT_TIMEOUT,
    MARIADB_DATABASE,
    MARIADB_HOST,
    MARIADB_PASSWORD,
    MARIADB_PORT,
    MARIADB_SOCKET,
    MARIADB_USER,
)
from services.mariadb_service import obter_conexao_mariadb


CREATE_HISTORICO_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS historico_impressoes (
    id BIGINT NOT NULL AUTO_INCREMENT,
    chave VARCHAR(255) NOT NULL,
    impressora VARCHAR(255) NOT NULL,
    data VARCHAR(32) NOT NULL,
    hora_inicio VARCHAR(32) NULL,
    impressoes_total_dia INT NOT NULL,
    motivo VARCHAR(255) NOT NULL,
    timestamp_salvo VARCHAR(64) NOT NULL,
    PRIMARY KEY (id),
    UNIQUE KEY uq_historico_impressoes_chave (chave),
    KEY idx_historico_impressoes_data (data),
    KEY idx_historico_impressoes_impressora_data (impressora, data),
    KEY idx_historico_impressoes_timestamp (timestamp_salvo)
)
"""
CREATE_CACHE_RASTREAMENTO_DIARIO_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS cache_rastreamento_diario (
    impressora VARCHAR(255) NOT NULL,
    data_lista VARCHAR(32) NULL,
    hora_primeiro_registro VARCHAR(32) NULL,
    impressoes_inicio INT NULL,
    impressoes_acumuladas INT NOT NULL DEFAULT 0,
    impressoes_dia INT NOT NULL DEFAULT 0,
    registrado_hoje TINYINT(1) NOT NULL DEFAULT 0,
    PRIMARY KEY (impressora)
)
"""
CREATE_RASTREAMENTO_MENSAL_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS rastreamento_mensal (
    impressora VARCHAR(255) NOT NULL,
    mes_referencia VARCHAR(32) NULL,
    impressoes_inicio INT NULL,
    impressoes_acumuladas INT NOT NULL DEFAULT 0,
    impressoes_mes INT NOT NULL DEFAULT 0,
    registrado_mes TINYINT(1) NOT NULL DEFAULT 0,
    PRIMARY KEY (impressora)
)
"""
CREATE_CACHE_IMPRESSORA_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS cache_impressora (
    impressora VARCHAR(255) NOT NULL,
    ip VARCHAR(64) NULL,
    nome VARCHAR(255) NULL,
    num_serie VARCHAR(255) NULL,
    modelo VARCHAR(255) NULL,
    asset_number VARCHAR(255) NULL,
    location VARCHAR(255) NULL,
    uptime VARCHAR(255) NULL,
    mac VARCHAR(64) NULL,
    atualizado_em VARCHAR(64) NOT NULL,
    PRIMARY KEY (impressora)
)
"""
CREATE_PRINTER_CONFIG_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS printer_config (
    impressora VARCHAR(255) NOT NULL,
    ip VARCHAR(64) NOT NULL,
    community VARCHAR(255) NOT NULL,
    token_tipo VARCHAR(32) NOT NULL DEFAULT 'pb',
    criado_em VARCHAR(64) NOT NULL,
    PRIMARY KEY (impressora),
    UNIQUE KEY uq_printer_config_ip (ip)
)
"""
CREATE_IMPRESSOES_USUARIOS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS impressoes_usuarios (
    id BIGINT NOT NULL AUTO_INCREMENT,
    servidor VARCHAR(255) NOT NULL,
    record_id BIGINT NOT NULL,
    event_id INT NOT NULL,
    data_hora DATETIME NOT NULL,
    usuario VARCHAR(255) NOT NULL,
    impressora VARCHAR(255) NOT NULL,
    documento VARCHAR(500) NULL,
    paginas INT NOT NULL DEFAULT 0,
    computador VARCHAR(255) NULL,
    job_id BIGINT NULL,
    porta VARCHAR(255) NULL,
    tamanho_bytes BIGINT NULL,
    criado_em DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uq_impressoes_usuarios_evento (servidor, record_id),
    KEY idx_impressoes_usuarios_data_hora (data_hora),
    KEY idx_impressoes_usuarios_usuario_data (usuario, data_hora),
    KEY idx_impressoes_usuarios_impressora_data (impressora, data_hora)
)
"""
ALTER_PRINTER_CONFIG_TOKEN_SQL = """
ALTER TABLE printer_config
ADD COLUMN token_tipo VARCHAR(32) NOT NULL DEFAULT 'pb' AFTER community
"""


# Monta o dicionário de configuração usado para abrir conexões com o MariaDB
def _obter_config_mariadb():
    return {
        "host": MARIADB_HOST,
        "port": MARIADB_PORT,
        "user": MARIADB_USER,
        "password": MARIADB_PASSWORD,
        "database": MARIADB_DATABASE,
        "connect_timeout": MARIADB_CONNECT_TIMEOUT,
        "socket": MARIADB_SOCKET,
    }


# Abre uma conexão com o MariaDB usando a configuração atual do ambiente
def _obter_conexao(_caminho_banco=None):
    return obter_conexao_mariadb(_obter_config_mariadb())


# Cria as tabelas necessárias e aplica migrações simples na inicialização do sistema
def inicializar_banco(caminho_banco):
    with _obter_conexao(caminho_banco) as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(CREATE_HISTORICO_TABLE_SQL)
            cursor.execute(CREATE_CACHE_RASTREAMENTO_DIARIO_TABLE_SQL)
            cursor.execute(CREATE_RASTREAMENTO_MENSAL_TABLE_SQL)
            cursor.execute(CREATE_CACHE_IMPRESSORA_TABLE_SQL)
            cursor.execute(CREATE_PRINTER_CONFIG_TABLE_SQL)
            cursor.execute(CREATE_IMPRESSOES_USUARIOS_TABLE_SQL)
            _garantir_coluna_token_printer_config(cursor)
            if _printer_config_tem_coluna_token(cursor):
                _migrar_tokens_antigos_para_printer_config(cursor)
        conexao.commit()


# Verifica se a tabela de configuração já possui a coluna token_tipo
def _printer_config_tem_coluna_token(cursor):
    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = 'printer_config'
          AND COLUMN_NAME = 'token_tipo'
        """,
        (MARIADB_DATABASE,),
    )
    resultado = cursor.fetchone() or {}

    return int(resultado.get("total") or 0) > 0


# Garante a existência da coluna token_tipo em instalações antigas
def _garantir_coluna_token_printer_config(cursor):
    if _printer_config_tem_coluna_token(cursor):
        return

    try:
        cursor.execute(ALTER_PRINTER_CONFIG_TOKEN_SQL)
    except Exception as exc:
        print(
            "Nao foi possivel adicionar a coluna printer_config.token_tipo. "
            "Conceda permissao ALTER ao usuario MariaDB ou adicione a coluna manualmente. "
            f"Erro: {exc}"
        )


# Migra tokens salvos na tabela antiga printer_token para printer_config
def _migrar_tokens_antigos_para_printer_config(cursor):
    cursor.execute(
        """
        SELECT COUNT(*) AS total
        FROM INFORMATION_SCHEMA.TABLES
        WHERE TABLE_SCHEMA = %s
          AND TABLE_NAME = 'printer_token'
        """,
        (MARIADB_DATABASE,),
    )
    resultado = cursor.fetchone() or {}

    if int(resultado.get("total") or 0) == 0:
        return

    cursor.execute(
        """
        UPDATE printer_config pc
        INNER JOIN printer_token pt ON pt.impressora = pc.impressora
        SET pc.token_tipo = COALESCE(NULLIF(pt.token_tipo, ''), 'pb')
        """
    )


# Carrega o histórico consolidado de impressões salvo no banco
def carregar_historico(caminho_banco):
    with _obter_conexao(caminho_banco) as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    chave,
                    impressora,
                    data,
                    hora_inicio,
                    impressoes_total_dia,
                    motivo,
                    timestamp_salvo
                FROM historico_impressoes
                ORDER BY timestamp_salvo DESC, id DESC
                """
            )
            registros = cursor.fetchall()

    return {
        registro["chave"]: {
            "impressora": registro["impressora"],
            "data": registro["data"],
            "hora_inicio": registro["hora_inicio"],
            "impressoes_total_dia": registro["impressoes_total_dia"],
            "motivo": registro["motivo"],
            "timestamp_salvo": registro["timestamp_salvo"],
        }
        for registro in registros
    }


# Insere ou atualiza um registro consolidado de histórico diário
def salvar_registro_historico(caminho_banco, chave, registro):
    impressoes_total_dia = int(
        registro.get("impressoes_total_dia", registro.get("impressoes_total", 0)) or 0
    )

    with _obter_conexao(caminho_banco) as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO historico_impressoes (
                    chave,
                    impressora,
                    data,
                    hora_inicio,
                    impressoes_total_dia,
                    motivo,
                    timestamp_salvo
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    impressora = VALUES(impressora),
                    data = VALUES(data),
                    hora_inicio = VALUES(hora_inicio),
                    impressoes_total_dia = VALUES(impressoes_total_dia),
                    motivo = VALUES(motivo),
                    timestamp_salvo = VALUES(timestamp_salvo)
                """,
                (
                    chave,
                    registro["impressora"],
                    registro["data"],
                    registro["hora_inicio"],
                    impressoes_total_dia,
                    registro["motivo"],
                    registro["timestamp_salvo"],
                ),
            )
        conexao.commit()


# Carrega todo o cache de rastreamento diário persistido por impressora
def carregar_cache_rastreamento_diario(caminho_banco):
    with _obter_conexao(caminho_banco) as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    impressora,
                    data_lista,
                    hora_primeiro_registro,
                    impressoes_inicio,
                    impressoes_acumuladas,
                    impressoes_dia,
                    registrado_hoje
                FROM cache_rastreamento_diario
                """
            )
            registros = cursor.fetchall()

    return {
        registro["impressora"]: {
            "data_lista": registro["data_lista"],
            "hora_primeiro_registro": registro["hora_primeiro_registro"],
            "impressoes_inicio": registro["impressoes_inicio"],
            "impressoes_acumuladas": registro["impressoes_acumuladas"],
            "impressoes_dia": registro["impressoes_dia"],
            "registrado_hoje": bool(registro["registrado_hoje"]),
        }
        for registro in registros
    }


# Remove caches diários de datas antigas e carrega apenas o cache da data informada
def carregar_cache_rastreamento_diario_atual(caminho_banco, data_referencia):
    with _obter_conexao(caminho_banco) as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                DELETE FROM cache_rastreamento_diario
                WHERE data_lista IS NOT NULL AND data_lista <> %s
                """,
                (str(data_referencia),),
            )
            cursor.execute(
                """
                SELECT
                    impressora,
                    data_lista,
                    hora_primeiro_registro,
                    impressoes_inicio,
                    impressoes_acumuladas,
                    impressoes_dia,
                    registrado_hoje
                FROM cache_rastreamento_diario
                WHERE data_lista = %s
                """,
                (str(data_referencia),),
            )
            registros = cursor.fetchall()
        conexao.commit()

    return {
        registro["impressora"]: {
            "data_lista": registro["data_lista"],
            "hora_primeiro_registro": registro["hora_primeiro_registro"],
            "impressoes_inicio": registro["impressoes_inicio"],
            "impressoes_acumuladas": registro["impressoes_acumuladas"],
            "impressoes_dia": registro["impressoes_dia"],
            "registrado_hoje": bool(registro["registrado_hoje"]),
        }
        for registro in registros
    }


# Salva o estado atual do rastreamento diário de uma impressora
def salvar_cache_rastreamento_diario(caminho_banco, impressora, rastreamento):
    with _obter_conexao(caminho_banco) as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO cache_rastreamento_diario (
                    impressora,
                    data_lista,
                    hora_primeiro_registro,
                    impressoes_inicio,
                    impressoes_acumuladas,
                    impressoes_dia,
                    registrado_hoje
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    data_lista = VALUES(data_lista),
                    hora_primeiro_registro = VALUES(hora_primeiro_registro),
                    impressoes_inicio = VALUES(impressoes_inicio),
                    impressoes_acumuladas = VALUES(impressoes_acumuladas),
                    impressoes_dia = VALUES(impressoes_dia),
                    registrado_hoje = VALUES(registrado_hoje)
                """,
                (
                    impressora,
                    rastreamento["data_lista"],
                    rastreamento["hora_primeiro_registro"],
                    rastreamento["impressoes_inicio"],
                    int(rastreamento.get("impressoes_acumuladas", 0) or 0),
                    int(rastreamento.get("impressoes_dia", 0) or 0),
                    1 if rastreamento.get("registrado_hoje") else 0,
                ),
            )
        conexao.commit()


# Carrega o estado mensal de rastreamento de todas as impressoras
def carregar_rastreamento_mensal(caminho_banco):
    with _obter_conexao(caminho_banco) as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    impressora,
                    mes_referencia,
                    impressoes_inicio,
                    impressoes_acumuladas,
                    impressoes_mes,
                    registrado_mes
                FROM rastreamento_mensal
                """
            )
            registros = cursor.fetchall()

    return {
        registro["impressora"]: {
            "mes_referencia": registro["mes_referencia"],
            "impressoes_inicio": registro["impressoes_inicio"],
            "impressoes_acumuladas": registro["impressoes_acumuladas"],
            "impressoes_mes": registro["impressoes_mes"],
            "registrado_mes": bool(registro["registrado_mes"]),
        }
        for registro in registros
    }


# Salva o estado mensal de rastreamento de uma impressora
def salvar_rastreamento_mensal(caminho_banco, impressora, rastreamento):
    with _obter_conexao(caminho_banco) as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO rastreamento_mensal (
                    impressora,
                    mes_referencia,
                    impressoes_inicio,
                    impressoes_acumuladas,
                    impressoes_mes,
                    registrado_mes
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    mes_referencia = VALUES(mes_referencia),
                    impressoes_inicio = VALUES(impressoes_inicio),
                    impressoes_acumuladas = VALUES(impressoes_acumuladas),
                    impressoes_mes = VALUES(impressoes_mes),
                    registrado_mes = VALUES(registrado_mes)
                """,
                (
                    impressora,
                    rastreamento["mes_referencia"],
                    rastreamento["impressoes_inicio"],
                    int(rastreamento.get("impressoes_acumuladas", 0) or 0),
                    int(rastreamento.get("impressoes_mes", 0) or 0),
                    1 if rastreamento.get("registrado_mes") else 0,
                ),
            )
        conexao.commit()


# Carrega o cache de dados estáveis das impressoras, como nome, modelo e localização
def carregar_cache_impressoras(caminho_banco):
    with _obter_conexao(caminho_banco) as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    impressora,
                    ip,
                    nome,
                    num_serie,
                    modelo,
                    asset_number,
                    location,
                    uptime,
                    mac,
                    atualizado_em
                FROM cache_impressora
                """
            )
            registros = cursor.fetchall()

    return {
        registro["impressora"]: {
            "ip": registro["ip"],
            "nome": registro["nome"],
            "num_serie": registro["num_serie"],
            "modelo": registro["modelo"],
            "asset_number": registro["asset_number"],
            "location": registro["location"],
            "uptime": registro["uptime"],
            "mac": registro["mac"],
            "atualizado_em": registro["atualizado_em"],
        }
        for registro in registros
    }


# Salva os dados estáveis de uma impressora coletados via SNMP
def salvar_cache_impressora(caminho_banco, impressora, dados_cache):
    with _obter_conexao(caminho_banco) as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO cache_impressora (
                    impressora,
                    ip,
                    nome,
                    num_serie,
                    modelo,
                    asset_number,
                    location,
                    uptime,
                    mac,
                    atualizado_em
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    ip = VALUES(ip),
                    nome = VALUES(nome),
                    num_serie = VALUES(num_serie),
                    modelo = VALUES(modelo),
                    asset_number = VALUES(asset_number),
                    location = VALUES(location),
                    uptime = VALUES(uptime),
                    mac = VALUES(mac),
                    atualizado_em = VALUES(atualizado_em)
                """,
                (
                    impressora,
                    dados_cache.get("ip"),
                    dados_cache.get("nome"),
                    dados_cache.get("num_serie"),
                    dados_cache.get("modelo"),
                    dados_cache.get("asset_number"),
                    dados_cache.get("location"),
                    dados_cache.get("uptime"),
                    dados_cache.get("mac"),
                    dados_cache.get("atualizado_em"),
                ),
            )
        conexao.commit()


# Carrega as configurações de impressoras cadastradas para iniciar o monitoramento
def carregar_configs_impressoras(caminho_banco):
    with _obter_conexao(caminho_banco) as conexao:
        with conexao.cursor() as cursor:
            if _printer_config_tem_coluna_token(cursor):
                cursor.execute(
                    """
                    SELECT
                        impressora,
                        ip,
                        community,
                        COALESCE(token_tipo, 'pb') AS token_tipo
                    FROM printer_config
                    ORDER BY LOWER(impressora), impressora
                    """
                )
            else:
                cursor.execute(
                    """
                    SELECT
                        impressora,
                        ip,
                        community,
                        'pb' AS token_tipo
                    FROM printer_config
                    ORDER BY LOWER(impressora), impressora
                    """
                )
            registros = cursor.fetchall()

    return [
        {
            "id": registro["impressora"],
            "ip": registro["ip"],
            "community": registro["community"],
            "token_tipo": registro.get("token_tipo") or "pb",
        }
        for registro in registros
    ]


# Insere ou atualiza uma configuração de impressora no banco
def salvar_config_impressora(caminho_banco, config):
    with _obter_conexao(caminho_banco) as conexao:
        with conexao.cursor() as cursor:
            criado_em = config.get("criado_em") or datetime.now().isoformat(sep=" ", timespec="seconds")
            if _printer_config_tem_coluna_token(cursor):
                cursor.execute(
                    """
                    INSERT INTO printer_config (
                        impressora,
                        ip,
                        community,
                        token_tipo,
                        criado_em
                    )
                    VALUES (%s, %s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        ip = VALUES(ip),
                        community = VALUES(community),
                        token_tipo = VALUES(token_tipo)
                    """,
                    (
                        config["id"],
                        config["ip"],
                        config["community"],
                        config["token_tipo"],
                        criado_em,
                    ),
                )
            else:
                cursor.execute(
                    """
                    INSERT INTO printer_config (
                        impressora,
                        ip,
                        community,
                        criado_em
                    )
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        ip = VALUES(ip),
                        community = VALUES(community)
                    """,
                    (
                        config["id"],
                        config["ip"],
                        config["community"],
                        criado_em,
                    ),
                )
        conexao.commit()


# Exclui cadastro e caches de uma impressora, preservando o histórico consolidado
def excluir_config_impressora(caminho_banco, impressora):
    with _obter_conexao(caminho_banco) as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                "DELETE FROM printer_config WHERE impressora = %s",
                (impressora,),
            )
            cursor.execute(
                "DELETE FROM cache_rastreamento_diario WHERE impressora = %s",
                (impressora,),
            )
            cursor.execute(
                "DELETE FROM rastreamento_mensal WHERE impressora = %s",
                (impressora,),
            )
            cursor.execute(
                "DELETE FROM cache_impressora WHERE impressora = %s",
                (impressora,),
            )
        conexao.commit()


def _normalizar_data_hora_impressao(valor):
    if hasattr(valor, "strftime"):
        return valor.strftime("%Y-%m-%d %H:%M:%S")

    texto = str(valor or "").strip()
    if not texto:
        raise ValueError("Informe a data_hora da impressao.")

    formatos = (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%dT%H:%M:%S.%f",
    )

    for formato in formatos:
        try:
            return datetime.strptime(texto[:26], formato).strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            pass

    raise ValueError("data_hora deve estar no formato YYYY-MM-DD HH:MM:SS.")


def _inteiro_ou_zero(valor):
    if valor in (None, ""):
        return 0

    return int(valor)


def _inteiro_obrigatorio(dados, campo):
    valor = _inteiro_ou_zero(dados.get(campo))
    if valor <= 0:
        raise ValueError(f"Informe o campo {campo} com valor maior que zero.")

    return valor


def _inteiro_ou_nulo(valor):
    if valor in (None, ""):
        return None

    return int(valor)


def _texto_obrigatorio(dados, campo):
    valor = str(dados.get(campo) or "").strip()
    if not valor:
        raise ValueError(f"Informe o campo {campo}.")

    return valor


def _normalizar_evento_impressao_usuario(dados):
    return {
        "servidor": _texto_obrigatorio(dados, "servidor"),
        "record_id": _inteiro_obrigatorio(dados, "record_id"),
        "event_id": _inteiro_obrigatorio(dados, "event_id"),
        "data_hora": _normalizar_data_hora_impressao(dados.get("data_hora")),
        "usuario": _texto_obrigatorio(dados, "usuario"),
        "impressora": _texto_obrigatorio(dados, "impressora"),
        "documento": str(dados.get("documento") or "").strip() or None,
        "paginas": _inteiro_ou_zero(dados.get("paginas")),
        "computador": str(dados.get("computador") or "").strip() or None,
        "job_id": _inteiro_ou_nulo(dados.get("job_id")),
        "porta": str(dados.get("porta") or "").strip() or None,
        "tamanho_bytes": _inteiro_ou_nulo(dados.get("tamanho_bytes")),
    }


# Insere ou atualiza um evento de impressao recebido do servidor Windows
# usando servidor + record_id como chave contra duplicidade.
def salvar_impressao_usuario(caminho_banco, dados):
    evento = _normalizar_evento_impressao_usuario(dados)

    with _obter_conexao(caminho_banco) as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO impressoes_usuarios (
                    servidor,
                    record_id,
                    event_id,
                    data_hora,
                    usuario,
                    impressora,
                    documento,
                    paginas,
                    computador,
                    job_id,
                    porta,
                    tamanho_bytes
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    event_id = VALUES(event_id),
                    data_hora = VALUES(data_hora),
                    usuario = VALUES(usuario),
                    impressora = VALUES(impressora),
                    documento = VALUES(documento),
                    paginas = VALUES(paginas),
                    computador = VALUES(computador),
                    job_id = VALUES(job_id),
                    porta = VALUES(porta),
                    tamanho_bytes = VALUES(tamanho_bytes)
                """,
                (
                    evento["servidor"],
                    evento["record_id"],
                    evento["event_id"],
                    evento["data_hora"],
                    evento["usuario"],
                    evento["impressora"],
                    evento["documento"],
                    evento["paginas"],
                    evento["computador"],
                    evento["job_id"],
                    evento["porta"],
                    evento["tamanho_bytes"],
                ),
            )
            afetadas = cursor.rowcount
        conexao.commit()

    return {
        **evento,
        "criado": afetadas == 1,
        "atualizado": afetadas == 2,
    }


def _montar_filtros_impressoes_usuarios(filtros):
    filtros = filtros or {}
    where = []
    parametros = []

    if filtros.get("usuario"):
        where.append("usuario = %s")
        parametros.append(filtros["usuario"])
    if filtros.get("impressora"):
        where.append("impressora = %s")
        parametros.append(filtros["impressora"])
    if filtros.get("porta"):
        where.append("UPPER(TRIM(porta)) = UPPER(%s)")
        parametros.append(filtros["porta"])
    if filtros.get("data_inicio"):
        where.append("data_hora >= %s")
        parametros.append(filtros["data_inicio"])
    if filtros.get("data_fim"):
        where.append("data_hora < %s")
        parametros.append(filtros["data_fim"])

    sql_where = f"WHERE {' AND '.join(where)}" if where else ""
    return sql_where, parametros


# Lista os eventos detalhados de impressao por usuario, com filtros opcionais.
def listar_impressoes_usuarios(caminho_banco, filtros=None):
    sql_where, parametros = _montar_filtros_impressoes_usuarios(filtros)
    limite = min(max(int((filtros or {}).get("limite") or 200), 1), 1000)

    with _obter_conexao(caminho_banco) as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    servidor,
                    record_id,
                    event_id,
                    data_hora,
                    usuario,
                    impressora,
                    documento,
                    paginas,
                    computador,
                    job_id,
                    porta,
                    tamanho_bytes,
                    criado_em
                FROM impressoes_usuarios
                {sql_where}
                ORDER BY data_hora DESC, id DESC
                LIMIT %s
                """,
                (*parametros, limite),
            )
            return cursor.fetchall()


# Soma paginas e trabalhos por usuario, deixando o agrupamento para o MariaDB.
def resumir_impressoes_usuarios(caminho_banco, filtros=None):
    sql_where, parametros = _montar_filtros_impressoes_usuarios(filtros)

    with _obter_conexao(caminho_banco) as conexao:
        with conexao.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    usuario,
                    SUM(paginas) AS total_paginas,
                    COUNT(*) AS total_trabalhos,
                    MIN(data_hora) AS primeira_impressao,
                    MAX(data_hora) AS ultima_impressao
                FROM impressoes_usuarios
                {sql_where}
                GROUP BY usuario
                ORDER BY total_paginas DESC, usuario
                """,
                tuple(parametros),
            )
            return cursor.fetchall()


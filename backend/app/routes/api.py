from flask import Blueprint, current_app, jsonify, request

from config import (
    MARIADB_CONNECT_TIMEOUT,
    MARIADB_DATABASE,
    MARIADB_HOST,
    MARIADB_PASSWORD,
    MARIADB_PORT,
    MARIADB_USER,
)
from services.historico_service import (
    listar_impressoes_usuarios,
    resumir_impressoes_usuarios,
    salvar_impressao_usuario,
)
from services.mariadb_service import testar_conexao_mariadb
from services.printer_config_service import TOKEN_VALORES


# Cria e registra todas as rotas de API, recebendo os serviços usados pelos endpoints
def create_api_blueprint(monitor_service, printer_config_service):
    api_bp = Blueprint("api", __name__)

    # Formata timestamps para texto legível antes de enviar para a API
    def formatar_timestamp_api(valor):
        if not valor:
            return None

        if hasattr(valor, "isoformat"):
            return valor.isoformat(sep=" ")

        return str(valor)

    # Monta a lista de impressoras combinando cadastro salvo e resumo atual do monitor
    def montar_lista_impressoras():
        resumo_por_id = {
            impressora["id"]: impressora
            for impressora in monitor_service.get_impressoras_resumo()
        }
        linhas = []

        for config in printer_config_service.list_configs():
            resumo = resumo_por_id.get(config["id"], {})
            token_tipo = config["token_tipo"]
            linhas.append(
                {
                    "id": config["id"],
                    "ip": config["ip"],
                    "token_tipo": token_tipo,
                    "token_valor": TOKEN_VALORES.get(token_tipo, TOKEN_VALORES["pb"]),
                    "nome": resumo.get("nome") or config["id"],
                    "online": bool(resumo.get("online")),
                    "modelo": resumo.get("modelo"),
                    "location": resumo.get("location"),
                }
            )

        return linhas

    # Retorna o status atual de monitoramento das impressoras para o dashboard principal
    @api_bp.route("/api")
    @api_bp.route("/api/")
    def api():
        return jsonify(monitor_service.get_resultado())

    # Retorna a lista de impressoras cadastradas com dados de token e status resumido
    @api_bp.route("/api/impressoras")
    def api_impressoras():
        return jsonify(montar_lista_impressoras())

    # Cadastra uma nova impressora, inicia o monitoramento e salva a configuração no banco
    @api_bp.route("/api/impressoras", methods=["POST"])
    def api_adicionar_impressora():
        dados = request.get_json(silent=True) or {}

        try:
            nova_config = printer_config_service.preparar_nova_config(dados)
            monitor_service.add_printer(nova_config)
            printer_config_service.save_config(nova_config)
        except ValueError as exc:
            return jsonify({"erro": str(exc)}), 400
        except RuntimeError as exc:
            return jsonify({"erro": str(exc)}), 409

        return (
            jsonify(
                {
                    "mensagem": "Impressora adicionada com sucesso.",
                    "impressora": {
                        "id": nova_config["id"],
                        "ip": nova_config["ip"],
                        "token_tipo": nova_config["token_tipo"],
                        "nome": nova_config["id"],
                        "online": False,
                        "token_valor": TOKEN_VALORES.get(nova_config["token_tipo"], TOKEN_VALORES["pb"]),
                    },
                }
            ),
            201,
        )

    def excluir_impressora_cadastrada(impressora_id):
        try:
            printer_config_service.delete_config(impressora_id)
        except ValueError as exc:
            return jsonify({"erro": str(exc)}), 404

        try:
            monitor_service.remove_printer(impressora_id)
        except ValueError:
            pass

        return jsonify({"mensagem": "Impressora excluida com sucesso."})

    # Exclui uma impressora do monitoramento em memória e das tabelas de configuração/cache
    @api_bp.route("/api/impressoras/<impressora_id>", methods=["DELETE"])
    def api_excluir_impressora(impressora_id):
        return excluir_impressora_cadastrada(impressora_id)

    # Alternativa via POST para navegadores/proxies que bloqueiam DELETE
    @api_bp.route("/api/impressoras/<impressora_id>/excluir", methods=["POST"])
    def api_excluir_impressora_post(impressora_id):
        return excluir_impressora_cadastrada(impressora_id)

    # Retorna o histórico consolidado de impressões salvo pelo monitor
    @api_bp.route("/api/historico")
    def api_historico():
        return jsonify(monitor_service.get_historico())

    def obter_filtros_impressoes_usuarios():
        return {
            "usuario": request.args.get("usuario"),
            "impressora": request.args.get("impressora"),
            "porta": request.args.get("porta"),
            "data_inicio": request.args.get("data_inicio"),
            "data_fim": request.args.get("data_fim"),
            "limite": request.args.get("limite"),
        }

    def formatar_linha_impressao_usuario(registro):
        return {
            **registro,
            "data_hora": formatar_timestamp_api(registro.get("data_hora")),
            "criado_em": formatar_timestamp_api(registro.get("criado_em")),
        }

    def formatar_resumo_impressao_usuario(registro):
        return {
            "usuario": registro.get("usuario"),
            "total_paginas": int(registro.get("total_paginas") or 0),
            "total_trabalhos": int(registro.get("total_trabalhos") or 0),
            "primeira_impressao": formatar_timestamp_api(registro.get("primeira_impressao")),
            "ultima_impressao": formatar_timestamp_api(registro.get("ultima_impressao")),
        }

    # Recebe eventos de impressao coletados no servidor Windows pelo script PowerShell
    @api_bp.route("/api/impressoes-usuarios/importar", methods=["POST"])
    def api_importar_impressao_usuario():
        dados = request.get_json(silent=True)
        if not isinstance(dados, dict):
            return jsonify({"erro": "Envie um JSON de impressao valido."}), 400

        try:
            registro = salvar_impressao_usuario(None, dados)
        except ValueError as exc:
            return jsonify({"erro": str(exc)}), 400

        status = 201 if registro["criado"] else 200
        return jsonify({"mensagem": "Impressao registrada com sucesso.", "registro": registro}), status

    # Lista os eventos detalhados de impressao por usuario com filtros opcionais
    @api_bp.route("/api/impressoes-usuarios")
    def api_impressoes_usuarios():
        try:
            registros = listar_impressoes_usuarios(None, obter_filtros_impressoes_usuarios())
        except ValueError as exc:
            return jsonify({"erro": str(exc)}), 400

        return jsonify([formatar_linha_impressao_usuario(registro) for registro in registros])

    # Retorna a soma de paginas e trabalhos agrupada por usuario
    @api_bp.route("/api/impressoes-usuarios/resumo")
    def api_resumo_impressoes_usuarios():
        registros = resumir_impressoes_usuarios(None, obter_filtros_impressoes_usuarios())
        return jsonify([formatar_resumo_impressao_usuario(registro) for registro in registros])

    # Cruza o IP cadastrado com a porta PAPERCUT_<IP> e agrupa as impressoes por usuario
    @api_bp.route("/api/impressoras/<impressora_id>/usuarios")
    def api_usuarios_por_impressora(impressora_id):
        config = next(
            (item for item in printer_config_service.list_configs() if item["id"] == impressora_id),
            None,
        )
        if not config:
            return jsonify({"erro": "Impressora nao encontrada."}), 404

        filtros = {
            "porta": "PAPERCUT_" + config["ip"],
            "data_inicio": request.args.get("data_inicio"),
            "data_fim": request.args.get("data_fim"),
        }
        registros = resumir_impressoes_usuarios(None, filtros)

        return jsonify(
            {
                "impressora": {
                    "id": config["id"],
                    "ip": config["ip"],
                    "porta": filtros["porta"],
                },
                "usuarios": [
                    formatar_resumo_impressao_usuario(registro)
                    for registro in registros
                ],
            }
        )

    # Retorna informações internas para diagnosticar o estado do monitor e do histórico
    @api_bp.route("/api/debug/historico")
    def api_debug_historico():
        if not current_app.debug:
            return jsonify({"erro": "Endpoint de debug desabilitado."}), 404

        return jsonify(monitor_service.get_debug_info())

    # Força manualmente o salvamento do histórico diário atual para fins de teste
    @api_bp.route("/api/debug/forcar-historico")
    def api_debug_forcar_historico():
        if not current_app.debug:
            return jsonify({"erro": "Endpoint de debug desabilitado."}), 404

        salvos = monitor_service.forcar_salvamento_historico()
        return jsonify(
            {
                "salvos": salvos,
                "quantidade": len(salvos),
            }
        )

    # Testa a conexão com o MariaDB e retorna dados básicos do banco configurado
    @api_bp.route("/api/debug/mariadb")
    def api_debug_mariadb():
        if not current_app.debug:
            return jsonify({"erro": "Endpoint de debug desabilitado."}), 404

        config = {
            "host": MARIADB_HOST,
            "port": MARIADB_PORT,
            "user": MARIADB_USER,
            "password": MARIADB_PASSWORD,
            "database": MARIADB_DATABASE,
            "connect_timeout": MARIADB_CONNECT_TIMEOUT,
        }

        try:
            versao = testar_conexao_mariadb(config)
        except Exception as exc:
            return (
                jsonify(
                    {
                        "ok": False,
                        "erro": str(exc),
                        "host": MARIADB_HOST,
                        "porta": MARIADB_PORT,
                        "database": MARIADB_DATABASE or None,
                    }
                ),
                503,
            )

        return jsonify(
            {
                "ok": True,
                "host": MARIADB_HOST,
                "porta": MARIADB_PORT,
                "database": MARIADB_DATABASE or None,
                "versao": versao,
            }
        )

    return api_bp

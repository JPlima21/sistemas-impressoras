import hmac
import os
from pathlib import Path

from flask import Flask, Response, request

from config import (
    CORS_ORIGINS,
    HISTORICO_FECHAMENTO_DIARIO,
    MONITOR_INTERVAL_SECONDS,
)
from routes.api import create_api_blueprint
from routes.web import create_web_blueprint
from services.historico_service import inicializar_banco
from services.monitor_service import PrinterMonitorService
from services.printer_config_service import PrinterConfigService


PROJECT_ROOT = Path(__file__).resolve().parents[2]
FRONTEND_DIR = PROJECT_ROOT / "frontend"


def _auth_configurada():
    return bool(os.getenv("APP_AUTH_USER") and os.getenv("APP_AUTH_PASSWORD"))


def _resposta_auth_requerida():
    return Response(
        "Autenticacao requerida.",
        401,
        {"WWW-Authenticate": 'Basic realm="Monitor de Impressoras"'},
    )


def _origem_cors_permitida(origem):
    if not origem or not CORS_ORIGINS:
        return None

    if "*" in CORS_ORIGINS or origem in CORS_ORIGINS:
        return origem

    return None


def _registrar_cors(app):
    @app.before_request
    def responder_preflight_cors():
        if request.method != "OPTIONS":
            return None

        origem_permitida = _origem_cors_permitida(request.headers.get("Origin"))
        if not origem_permitida:
            return None

        return Response(status=204)

    @app.after_request
    def adicionar_cabecalhos_cors(response):
        origem_permitida = _origem_cors_permitida(request.headers.get("Origin"))
        if not origem_permitida:
            return response

        response.headers["Access-Control-Allow-Origin"] = origem_permitida
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
        response.headers.add("Vary", "Origin")
        return response


def _registrar_autenticacao_basica(app):
    @app.before_request
    def exigir_autenticacao_basica():
        if request.method == "OPTIONS":
            return None

        if request.endpoint == "static" or not _auth_configurada():
            return None

        auth = request.authorization
        if not auth:
            return _resposta_auth_requerida()

        usuario = os.getenv("APP_AUTH_USER") or ""
        senha = os.getenv("APP_AUTH_PASSWORD") or ""

        usuario_ok = hmac.compare_digest(auth.username or "", usuario)
        senha_ok = hmac.compare_digest(auth.password or "", senha)

        if not usuario_ok or not senha_ok:
            return _resposta_auth_requerida()

        return None


# Monta a aplicação Flask, inicializa o banco, carrega impressoras e inicia o monitoramento
def create_app():
    app = Flask(
        __name__,
        template_folder=str(FRONTEND_DIR / "templates"),
        static_folder=str(FRONTEND_DIR / "static"),
        static_url_path="/static",
    )
    _registrar_cors(app)
    _registrar_autenticacao_basica(app)
    armazenamento_mariadb = None
    inicializar_banco(armazenamento_mariadb)
    printer_config_service = PrinterConfigService(armazenamento_mariadb)
    printer_configs = printer_config_service.list_configs()

    monitor_service = PrinterMonitorService(
        printer_configs=printer_configs,
        historico_storage=armazenamento_mariadb,
        monitor_interval=MONITOR_INTERVAL_SECONDS,
        daily_close_time=HISTORICO_FECHAMENTO_DIARIO,
    )
    monitor_service.start()

    app.register_blueprint(create_api_blueprint(monitor_service, printer_config_service))
    app.register_blueprint(create_web_blueprint())

    return app


app = create_app()


if __name__ == "__main__":
    debug_mode = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(debug=debug_mode)

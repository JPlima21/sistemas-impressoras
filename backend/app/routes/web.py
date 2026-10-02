from flask import Blueprint, current_app, render_template, send_from_directory


# Cria e registra as rotas que renderizam as páginas HTML do sistema
def create_web_blueprint():
    web_bp = Blueprint("web", __name__)

    # Renderiza o dashboard principal de monitoramento
    @web_bp.route("/")
    def home():
        return render_template("index.html")

    # Renderiza a página de gráficos e relatórios
    @web_bp.route("/graficos")
    def graficos():
        return render_template("graficos.html")

    @web_bp.route("/rede")
    def rede():
        return render_template("rede.html")

    # Redireciona a rota antiga de configurações para a URL atual
    @web_bp.route("/impressoras")
    def impressoras():
        return render_template("impressoras.html")

    # Renderiza a página de cadastro e configuração das impressoras
    @web_bp.route("/configurações")
    @web_bp.route("/configuracoes")
    def configuracoes():
        return render_template("impressoras.html")

    # Entrega a imagem padrão das impressoras OKI por uma rota que não depende de /static/*.jpeg
    @web_bp.route("/assets/printers/oki")
    def imagem_impressora_oki():
        return send_from_directory(current_app.static_folder, "OKI_CALLCENTER.jpeg")

    # Entrega a imagem padrão das impressoras Epson por uma rota que não depende de /static/*.JPG
    @web_bp.route("/assets/printers/epson")
    def imagem_impressora_epson():
        return send_from_directory(current_app.static_folder, "Epson.JPG")

    return web_bp

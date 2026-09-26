"""Preview do sistema com dados ficticios e sem dependencias externas."""
from datetime import datetime, timedelta
from pathlib import Path
import os
import re

from flask import Flask, jsonify, render_template, request, send_from_directory

ROOT = Path(__file__).resolve().parent
FRONTEND = ROOT / "frontend"
TOKEN_VALUES = {"pb": 0.08, "colorida": 0.42, "nenhum": 0.0}
app = Flask(__name__, template_folder=str(FRONTEND / "templates"),
            static_folder=str(FRONTEND / "static"), static_url_path="/static")


def printer(printer_id, **values):
    item = {"id": printer_id, "nome": printer_id.replace("-", " ").title(),
            "online": True, "token_tipo": "pb", "token_valor": 0.08,
            "problemas": [], "scanner": "Disponivel"}
    item.update(values)
    return item


PRINTERS = {item["id"]: item for item in [
    printer("recepcao", ip="192.168.10.21", mac="00:25:36:A1:20:11", num_serie="AK7201843",
            modelo="OKI ES5473 MFP", asset_number="PAT-1042", location="Recepcao",
            uptime="38 dias, 12:40", total_impressoes=184320, impressoes=172480,
            copias=11840, impressoes_dia=286, impressoes_mes=4932,
            copias_dia=21, copias_mes=418, toner="68%"),
    printer("financeiro", ip="192.168.10.34", mac="00:26:AB:17:82:90", num_serie="EP9341502",
            modelo="Epson WorkForce Pro WF-C579R", asset_number="PAT-1078", location="Financeiro",
            uptime="16 dias, 07:18", total_impressoes=96218, impressoes=91360,
            copias=4858, impressoes_dia=174, impressoes_mes=3215, copias_dia=12,
            copias_mes=206, toner="22%", token_tipo="colorida", token_valor=0.42),
    printer("rh", ip="192.168.10.45", mac="00:25:36:C3:11:48", num_serie="AK7202711",
            modelo="OKI ES5112", asset_number="PAT-1091", location="Recursos Humanos",
            uptime="27 dias, 03:54", total_impressoes=72104, impressoes=70112,
            copias=1992, impressoes_dia=93, impressoes_mes=1867, copias_dia=4,
            copias_mes=88, toner="9%", problemas=[{"id": "toner", "mensagem":
            "Toner proximo do fim", "severidade": "aviso"}]),
    printer("expedicao", ip="192.168.10.58", mac="00:26:AB:51:99:03", num_serie="EP9348820",
            modelo="Epson WorkForce Pro WF-M5799", asset_number="PAT-1115", location="Expedicao",
            uptime="Indisponivel", total_impressoes=128902, impressoes=122411,
            copias=6491, impressoes_dia=0, impressoes_mes=2740, copias_dia=0,
            copias_mes=171, toner="41%", online=False, problemas=[{"id": "offline",
            "mensagem": "Equipamento sem comunicacao", "severidade": "critica"}]),
]}
USERS = ["ana.souza", "carlos.lima", "marina.alves", "joao.santos", "beatriz.rocha"]
DOCUMENTS = ["Relatorio mensal.pdf", "Pedido de compra.pdf", "Folha de pagamento.xlsx",
             "Contrato cliente.docx", "Romaneio 2026.pdf"]


def build_demo_data():
    history, events = [], []
    today = datetime.now().date()
    for offset in range(34, -1, -1):
        day = today - timedelta(days=offset)
        if day.weekday() >= 5:
            continue
        for index, printer_id in enumerate(PRINTERS):
            pages = 68 + ((offset * 37 + index * 83) % 260)
            if printer_id == "expedicao" and offset == 0:
                pages = 0
            timestamp = f"{day.isoformat()} 23:59:00"
            common = {"data": day.isoformat(), "data_salvamento": day.isoformat(),
                      "motivo": "fechamento_diario", "timestamp_salvo": timestamp}
            history.append({**common, "impressora": printer_id,
                            "impressora_nome": PRINTERS[printer_id]["nome"],
                            "impressoes_total_dia": pages})
            history.append({**common, "impressora": f"{printer_id}__copias",
                            "impressoes_total_dia": pages // 12})
            for event_index in range(2):
                user = USERS[(offset + index + event_index) % len(USERS)]
                event_pages = max(1, pages // (9 + event_index * 4))
                events.append({"servidor": "PRINT-SRV01", "event_id": 307,
                    "record_id": f"{day:%Y%m%d}{index}{event_index}",
                    "data_hora": f"{day.isoformat()} {9 + event_index * 5:02d}:{12 + index:02d}:00",
                    "usuario": user, "impressora": PRINTERS[printer_id]["nome"],
                    "impressora_id": printer_id,
                    "documento": DOCUMENTS[(offset + index + event_index) % len(DOCUMENTS)],
                    "paginas": event_pages, "computador": f"PC-{100 + index * 7 + event_index}",
                    "job_id": f"JOB-{offset:02d}{index}{event_index}",
                    "porta": f"PAPERCUT_{PRINTERS[printer_id]['ip']}",
                    "tamanho_bytes": event_pages * 184320})
    return history, events


HISTORY, EVENTS = build_demo_data()


@app.context_processor
def preview_context():
    return {"system_version": "1.1.0-preview"}


@app.route("/")
def home(): return render_template("index.html")


@app.route("/graficos")
def charts(): return render_template("graficos.html")


@app.route("/impressoras")
@app.route("/configuracoes")
@app.route("/configurações")
def printers_page(): return render_template("impressoras.html")


@app.route("/assets/printers/<kind>")
def printer_image(kind):
    return send_from_directory(str(FRONTEND / "static" / "images"),
                               "Epson.JPG" if kind.lower() == "epson" else "OKI_CALLCENTER.jpeg")


@app.route("/api")
@app.route("/api/")
def api_dashboard(): return jsonify({"impressoras": PRINTERS})


@app.route("/api/impressoras", methods=["GET", "POST"])
def api_printers():
    if request.method == "GET":
        return jsonify(list(PRINTERS.values()))
    payload = request.get_json(silent=True) or {}
    printer_id = str(payload.get("id") or "").strip().lower()
    ip = str(payload.get("ip") or "").strip()
    if not re.fullmatch(r"[a-z0-9_-]{2,40}", printer_id):
        return jsonify({"erro": "Use um identificador com letras, numeros, _ ou -."}), 400
    if printer_id in PRINTERS:
        return jsonify({"erro": "Ja existe uma impressora com esse identificador."}), 409
    octets = ip.split(".")
    if len(octets) != 4 or not all(p.isdigit() and 0 <= int(p) <= 255 for p in octets):
        return jsonify({"erro": "Informe um endereco IPv4 valido."}), 400
    token_type = str(payload.get("token_tipo") or "pb")
    item = printer(printer_id, ip=ip, modelo="Equipamento de demonstracao",
        location="Novo cadastro", online=False, token_tipo=token_type,
        token_valor=TOKEN_VALUES.get(token_type, 0.08), total_impressoes=0,
        impressoes=0, copias=0, impressoes_dia=0, impressoes_mes=0, toner="N/A")
    PRINTERS[printer_id] = item
    return jsonify({"mensagem": "Impressora adicionada ao preview.", "impressora": item}), 201


@app.route("/api/impressoras/<printer_id>", methods=["DELETE"])
@app.route("/api/impressoras/<printer_id>/excluir", methods=["POST"])
def api_delete_printer(printer_id):
    if PRINTERS.pop(printer_id, None) is None:
        return jsonify({"erro": "Impressora nao encontrada."}), 404
    return jsonify({"mensagem": "Impressora removida do preview."})


@app.route("/api/historico")
def api_history(): return jsonify(HISTORY)


def filtered_events():
    result = EVENTS
    printer_id, user = request.args.get("impressora"), request.args.get("usuario")
    start, end = request.args.get("data_inicio"), request.args.get("data_fim")
    if printer_id: result = [x for x in result if printer_id in (x["impressora_id"], x["impressora"])]
    if user: result = [x for x in result if x["usuario"] == user]
    if start: result = [x for x in result if x["data_hora"][:10] >= start]
    if end: result = [x for x in result if x["data_hora"][:10] <= end]
    limit = request.args.get("limite", type=int)
    return result[-limit:] if limit and limit > 0 else result


def summarize(events):
    summary = {}
    for event in events:
        row = summary.setdefault(event["usuario"], {"usuario": event["usuario"],
            "total_paginas": 0, "total_trabalhos": 0,
            "primeira_impressao": event["data_hora"], "ultima_impressao": event["data_hora"]})
        row["total_paginas"] += event["paginas"]
        row["total_trabalhos"] += 1
        row["primeira_impressao"] = min(row["primeira_impressao"], event["data_hora"])
        row["ultima_impressao"] = max(row["ultima_impressao"], event["data_hora"])
    return sorted(summary.values(), key=lambda x: x["total_paginas"], reverse=True)


@app.route("/api/impressoes-usuarios")
def api_user_prints(): return jsonify(filtered_events())


@app.route("/api/impressoes-usuarios/resumo")
def api_user_summary(): return jsonify(summarize(filtered_events()))


@app.route("/api/impressoras/<printer_id>/usuarios")
def api_printer_users(printer_id):
    return jsonify(summarize([x for x in filtered_events() if x["impressora_id"] == printer_id]))


@app.route("/api/relatorios/mensal/usuarios")
def api_monthly_users():
    month = request.args.get("mes") or datetime.now().strftime("%Y-%m")
    return jsonify(summarize([x for x in EVENTS if x["data_hora"].startswith(month)]))


@app.route("/api/relatorios/mensal/impressoras")
def api_monthly_printers():
    totals = {}
    for item in HISTORY:
        month, printer_id = item["data"][:7], item["impressora"].removesuffix("__copias")
        row = totals.setdefault((month, printer_id), {"competencia": month,
            "impressora": printer_id, "total_paginas": 0, "total_copias": 0,
            "intervalos_especiais": 0})
        key = "total_copias" if item["impressora"].endswith("__copias") else "total_paginas"
        row[key] += item["impressoes_total_dia"]
    month = request.args.get("mes")
    return jsonify([x for x in totals.values() if not month or x["competencia"] == month])


@app.route("/api/impressoes-usuarios/status")
def api_script_status():
    latest = EVENTS[-1]
    return jsonify({"ok": True, "total_eventos": len(EVENTS),
        "ultimo_recebimento_em": latest["data_hora"], "ultimo_evento_em": latest["data_hora"],
        "ultimo_evento": latest})


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.getenv("PREVIEW_PORT", "8081")), debug=False)

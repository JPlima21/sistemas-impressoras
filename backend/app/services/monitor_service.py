import threading
import time
import traceback
from datetime import date, datetime, time as time_type, timedelta

from config import (
    PRINTER_CACHE_PERSIST_INTERVAL_SECONDS,
    SNMP_OIDS,
    SNMP_STABLE_REFRESH_INTERVAL_SECONDS,
    STATE_PERSIST_INTERVAL_SECONDS,
)
from services.historico_service import (
    carregar_cache_impressoras,
    carregar_cache_rastreamento_diario,
    carregar_historico,
    carregar_rastreamento_mensal,
    registrar_leitura_contador,
    salvar_cache_impressora,
    salvar_cache_rastreamento_diario,
    salvar_registro_historico,
    salvar_rastreamento_mensal,
)
from services.snmp_service import (
    criar_snmp_engine,
    formatar_mac,
    snmp_get,
    snmp_walk_pares,
    snmp_walk_tabela,
)


# Traducoes dos codigos de problema definidos por PrtAlertCodeTC (RFC 3805).
# A descricao original do fabricante continua sendo enviada na API.
ALERTAS_PRINTER_MIB_TRADUZIDOS = {
    3: ("tampa_aberta", "Tampa aberta"),
    5: ("trava_aberta", "Trava de segurança aberta"),
    8: ("atolamento_papel", "Atolamento de papel"),
    9: ("componente_ausente", "Componente ou bandeja ausente"),
    10: ("vida_util", "Componente da impressora próximo do fim da vida útil"),
    11: ("vida_util", "Vida útil do componente da impressora encerrada"),
    12: ("unidade_quase_vazia", "Unidade ou suprimento quase vazio"),
    13: ("unidade_vazia", "Unidade ou suprimento vazio"),
    14: ("unidade_quase_cheia", "Unidade quase cheia"),
    15: ("unidade_cheia", "Unidade cheia"),
    16: ("limite_unidade", "Unidade proxima do limite"),
    17: ("limite_unidade", "Limite da unidade atingido"),
    18: ("unidade_aberta", "Unidade aberta"),
    21: ("unidade_desligada", "Unidade desligada"),
    22: ("unidade_offline", "Unidade fora de servico"),
    26: ("unidade_removida", "Unidade removida"),
    28: ("recurso_removido", "Recurso removido"),
    29: ("falha_recuperavel", "Falha recuperável na unidade"),
    30: ("falha_irrecuperavel", "Falha irrecuperável na unidade"),
    31: ("erro_armazenamento", "Erro recuperável de armazenamento"),
    32: ("erro_armazenamento", "Erro irrecuperável de armazenamento"),
    33: ("falha_motor", "Falha no motor"),
    34: ("memoria_insuficiente", "Memória insuficiente"),
    35: ("temperatura", "Temperatura da unidade abaixo do normal"),
    36: ("temperatura", "Temperatura da unidade acima do normal"),
    37: ("falha_sincronismo", "Falha de sincronização da unidade"),
    38: ("falha_termistor", "Falha no termistor da unidade"),
    501: ("tampa_aberta", "Porta ou tampa aberta"),
    504: ("impressora_desligada", "Impressora desligada"),
    801: ("bandeja_ausente", "Bandeja de entrada ausente"),
    807: ("papel_baixo", "Pouco papel na bandeja"),
    808: ("sem_papel", "Bandeja sem papel"),
    809: ("troca_papel", "Troca de papel solicitada"),
    810: ("alimentacao_manual", "Alimentação manual de papel solicitada"),
    811: ("falha_bandeja", "Falha no posicionamento da bandeja"),
    812: ("falha_bandeja", "Falha na elevação da bandeja"),
    813: ("papel_incompativel", "Não foi possível alimentar o tamanho de papel selecionado"),
    901: ("bandeja_saida_ausente", "Bandeja de saída ausente"),
    902: ("bandeja_saida_quase_cheia", "Bandeja de saída quase cheia"),
    903: ("bandeja_saida_cheia", "Bandeja de saída cheia"),
    904: ("falha_caixa_saida", "Falha ao selecionar a caixa de saída"),
    1001: ("temperatura_fusor", "Temperatura do fusor abaixo do normal"),
    1002: ("temperatura_fusor", "Temperatura do fusor acima do normal"),
    1003: ("falha_fusor", "Falha de sincronização do fusor"),
    1004: ("falha_fusor", "Falha no termistor do fusor"),
    1005: ("ajuste_impressao", "Ajustando a qualidade de impressão"),
    1101: ("toner_vazio", "Toner vazio"),
    1102: ("tinta_vazia", "Tinta vazia"),
    1103: ("fita_vazia", "Fita de impressão vazia"),
    1104: ("toner_baixo", "Toner quase vazio"),
    1105: ("tinta_baixa", "Tinta quase vazia"),
    1106: ("fita_baixa", "Fita de impressão quase vazia"),
    1107: ("residuo_quase_cheio", "Reservatório de toner residual quase cheio"),
    1108: ("residuo_quase_cheio", "Reservatório de tinta residual quase cheio"),
    1109: ("residuo_cheio", "Reservatório de toner residual cheio"),
    1110: ("residuo_cheio", "Reservatório de tinta residual cheio"),
    1111: ("vida_util_cilindro", "Cilindro próximo do fim da vida útil"),
    1112: ("vida_util_cilindro", "Vida útil do cilindro encerrada"),
    1113: ("revelador_baixo", "Revelador quase vazio"),
    1114: ("revelador_vazio", "Revelador vazio"),
    1115: ("cartucho_ausente", "Cartucho de toner ausente"),
    1301: ("bandeja_percurso_ausente", "Bandeja do percurso do papel ausente"),
    1302: ("bandeja_percurso_quase_cheia", "Bandeja do percurso do papel quase cheia"),
    1303: ("bandeja_percurso_cheia", "Bandeja do percurso do papel cheia"),
    1304: ("duplex_indisponivel", "Papel selecionado incompatível com impressão frente e verso"),
    1502: ("memoria_reduzida", "Memória do interpretador reduzida"),
    1504: ("cartucho_interpretador_removido", "Cartucho do interpretador removido"),
    1506: ("recurso_interpretador_removido", "Recurso do interpretador removido"),
    1507: ("recurso_indisponivel", "Recurso do interpretador indisponível"),
    1509: ("pagina_complexa", "Página complexa demais para os recursos disponíveis"),
}

# Eventos normais ou de recuperacao que nao devem ocupar o card de problemas.
CODIGOS_ALERTA_SEM_PROBLEMA = frozenset(
    {
        4, 6, 7, 19, 20, 23, 24, 25, 27,
        502, 503, 505, 506, 507,
        802, 803, 804, 805, 806,
        1501, 1503, 1505, 1801,
    }
)

''' serviço principal de monitoramento das impressoras, 
responsável por coletar os dados via SNMP, 
calcular as impressões diárias e manter o histórico atualizado'''
class PrinterMonitorService:
    # Configura o monitor, carrega caches persistidos e prepara o estado inicial das impressoras
    def __init__(
        self,
        printer_configs,
        historico_storage,
        monitor_interval=5,
        daily_close_time="23:59",
        state_persist_interval=STATE_PERSIST_INTERVAL_SECONDS,
        printer_cache_persist_interval=PRINTER_CACHE_PERSIST_INTERVAL_SECONDS,
        snmp_stable_refresh_interval=SNMP_STABLE_REFRESH_INTERVAL_SECONDS,
    ):
        self.printer_configs = printer_configs # lista de dicionários com id, ip e community
        self.historico_storage = historico_storage # contexto mantido para chamadas de persistencia MariaDB
        self.monitor_interval = monitor_interval # intervalo em segundos entre cada coleta de dados
        self.daily_close_time = self._parse_daily_close_time(daily_close_time)
        self.state_persist_interval = max(int(state_persist_interval), 1)
        self.printer_cache_persist_interval = max(int(printer_cache_persist_interval), 1)
        self.snmp_stable_refresh_interval = max(int(snmp_stable_refresh_interval), 1)

        self._lock = threading.Lock()
        self._threads_started = False
        self._threads_por_impressora = {}
        self._impressoras_removidas = set()
        self.resultado_global = {"impressoras": {}}
        self.cache_rastreamento_dia = {}
        self.rastreamento_mes = {}
        self._ultimo_payload_cache_rastreamento = {}
        self._ultimo_payload_rastreamento_mes = {}
        self._ultimo_payload_cache_impressora = {}
        self._ultima_persistencia_cache_rastreamento = {}
        self._ultima_persistencia_rastreamento_mes = {}
        self._ultima_persistencia_cache_impressora = {}
        self._ultima_atualizacao_snmp_estavel = {}
        self.data_cache_diario = self._obter_data_ciclo_atual(datetime.now())
        self.cache_impressoras = carregar_cache_impressoras(self.historico_storage)
        self.historico_impressoes = carregar_historico(self.historico_storage)
        self.cache_rastreamento_dia_persistido = carregar_cache_rastreamento_diario(self.historico_storage)
        self.rastreamento_mes_persistido = carregar_rastreamento_mensal(self.historico_storage)

        self._inicializar_estado()

    # inicializa o estado para cada impressora, garantindo que a estrutura de rastreamento diário esteja pronta
    def _inicializar_estado(self):
        for config in self.printer_configs:
            impressora_id = config["id"]
            self.resultado_global["impressoras"][impressora_id] = {"online": False}

            for chave_rastreamento in (impressora_id, f"{impressora_id}__copias"):
                cache_rastreamento = self._criar_cache_rastreamento_dia_inicial()
                cache_rastreamento_persistido = self.cache_rastreamento_dia_persistido.get(
                    chave_rastreamento
                )
                rastreamento_mensal = self._criar_rastreamento_mensal_inicial()
                rastreamento_mensal_persistido = self.rastreamento_mes_persistido.get(
                    chave_rastreamento
                )

                if cache_rastreamento_persistido:
                    cache_rastreamento.update(
                        self._normalizar_cache_rastreamento_dia_persistido(
                            cache_rastreamento_persistido
                        )
                    )
                if rastreamento_mensal_persistido:
                    rastreamento_mensal.update(
                        self._normalizar_rastreamento_mensal_persistido(
                            rastreamento_mensal_persistido
                        )
                    )

                self.cache_rastreamento_dia[chave_rastreamento] = cache_rastreamento
                self.rastreamento_mes[chave_rastreamento] = rastreamento_mensal
 
    # cria o estado inicial para o cache do rastreamento diário
    def _criar_cache_rastreamento_dia_inicial(self):
        return {
            "data_lista": None,
            "hora_primeiro_registro": None,
            "impressoes_inicio": None,
            "impressoes_acumuladas": 0,
            "impressoes_dia": 0,
            "registrado_hoje": False,
        }

    # Cria o estado inicial para o rastreamento mensal
    def _criar_rastreamento_mensal_inicial(self):
        return {
            "mes_referencia": None,
            "impressoes_inicio": None,
            "impressoes_acumuladas": 0,
            "impressoes_mes": 0,
            "registrado_mes": False,
        }

    # Converte o cache diário carregado do banco para os tipos usados em memória
    def _normalizar_cache_rastreamento_dia_persistido(self, rastreamento):
        return {
            "data_lista": self._parse_data(rastreamento.get("data_lista")),
            "hora_primeiro_registro": self._parse_hora(rastreamento.get("hora_primeiro_registro")),
            "impressoes_inicio": rastreamento.get("impressoes_inicio"),
            "impressoes_acumuladas": int(rastreamento.get("impressoes_acumuladas", 0) or 0),
            "impressoes_dia": int(rastreamento.get("impressoes_dia", 0) or 0),
            "registrado_hoje": bool(rastreamento.get("registrado_hoje")),
        }

    # Converte o rastreamento mensal carregado do banco para os tipos usados em memória
    def _normalizar_rastreamento_mensal_persistido(self, rastreamento):
        return {
            "mes_referencia": rastreamento.get("mes_referencia"),
            "impressoes_inicio": rastreamento.get("impressoes_inicio"),
            "impressoes_acumuladas": int(rastreamento.get("impressoes_acumuladas", 0) or 0),
            "impressoes_mes": int(rastreamento.get("impressoes_mes", 0) or 0),
            "registrado_mes": bool(rastreamento.get("registrado_mes")),
        }

    # Interpreta uma data vinda do banco e retorna None quando o valor é inválido
    def _parse_data(self, valor):
        if not valor:
            return None

        try:
            return date.fromisoformat(str(valor))
        except ValueError:
            return None

    # Interpreta uma hora vinda do banco e retorna None quando o valor é inválido
    def _parse_hora(self, valor):
        if not valor:
            return None

        try:
            return time_type.fromisoformat(str(valor))
        except ValueError:
            return None

    # Interpreta o horário configurado para fechamento diário
    def _parse_daily_close_time(self, valor):
        if not valor:
            return time_type(0, 0)

        try:
            return time_type.fromisoformat(str(valor))
        except ValueError:
            return time_type(0, 0)

    # Calcula a data do ciclo diário considerando o horário de fechamento configurado
    def _obter_data_ciclo_atual(self, instante):
        data_ciclo = instante.date()

        if self.daily_close_time != time_type(0, 0) and instante.time() >= self.daily_close_time:
            data_ciclo += timedelta(days=1)

        return data_ciclo

    # Reinicia o rastreamento diário usando a leitura atual como ponto inicial do novo ciclo
    def _reiniciar_rastreamento_dia(self, rastreamento, data_lista, instante, impressoes_atuais):
        rastreamento["data_lista"] = data_lista
        rastreamento["hora_primeiro_registro"] = instante.time()
        rastreamento["impressoes_inicio"] = impressoes_atuais
        rastreamento["impressoes_acumuladas"] = 0
        rastreamento["impressoes_dia"] = 0
        rastreamento["registrado_hoje"] = False

    # Decide se um payload deve ser persistido agora, evitando escritas repetidas no banco
    def _deve_persistir(self, nome_impressora, payload, ultimo_payloads, ultimas_persistencias, intervalo, force=False):
        if force:
            return True

        ultimo_payload = ultimo_payloads.get(nome_impressora)
        if ultimo_payload is None:
            return True

        if payload == ultimo_payload:
            return False

        ultimo_instante = ultimas_persistencias.get(nome_impressora, 0.0)
        return (time.monotonic() - ultimo_instante) >= intervalo

    # Registra o último payload persistido e o instante da persistência
    def _registrar_persistencia(self, nome_impressora, payload, ultimo_payloads, ultimas_persistencias):
        ultimo_payloads[nome_impressora] = payload
        ultimas_persistencias[nome_impressora] = time.monotonic()

    # Controla quando os dados estáveis de SNMP devem ser buscados novamente
    def _deve_atualizar_dados_estaveis_snmp(self, nome_impressora):
        ultimo_instante = self._ultima_atualizacao_snmp_estavel.get(nome_impressora)
        if ultimo_instante is None:
            return True

        return (time.monotonic() - ultimo_instante) >= self.snmp_stable_refresh_interval

    # Busca ou reaproveita dados estáveis da impressora, como nome, modelo e MAC
    def _obter_dados_estaveis_impressora(self, engine, ip, community, nome_impressora):
        cache_atual = dict(self.cache_impressoras.get(nome_impressora, {}))

        if self._deve_atualizar_dados_estaveis_snmp(nome_impressora):
            cache_atual.update(
                {
                    "nome": str(snmp_get(engine, ip, community, SNMP_OIDS["nome"])),
                    "modelo": str(snmp_get(engine, ip, community, SNMP_OIDS["modelo"])),
                    "num_serie": str(snmp_get(engine, ip, community, SNMP_OIDS["serial"])),
                    "asset_number": str(snmp_get(engine, ip, community, SNMP_OIDS["asset_number"])),
                    "location": str(snmp_get(engine, ip, community, SNMP_OIDS["location"])),
                    "mac": formatar_mac(snmp_get(engine, ip, community, SNMP_OIDS["mac"])),
                }
            )
            self._ultima_atualizacao_snmp_estavel[nome_impressora] = time.monotonic()

        return {
            "nome": cache_atual.get("nome") or nome_impressora,
            "modelo": cache_atual.get("modelo") or "N/A",
            "num_serie": cache_atual.get("num_serie") or "N/A",
            "asset_number": cache_atual.get("asset_number") or "N/A",
            "location": cache_atual.get("location") or "N/A",
            "mac": cache_atual.get("mac") or "N/A",
        }

    # Persiste o cache de rastreamento diário quando houve mudança relevante
    def _salvar_cache_rastreamento_dia(self, nome_impressora, force=False):
        rastreamento = self.cache_rastreamento_dia[nome_impressora]
        payload = (
            rastreamento["data_lista"].isoformat() if rastreamento["data_lista"] else None,
            rastreamento["hora_primeiro_registro"].isoformat()
            if rastreamento["hora_primeiro_registro"]
            else None,
            rastreamento["impressoes_inicio"],
            int(rastreamento["impressoes_acumuladas"]),
            int(rastreamento["impressoes_dia"]),
            bool(rastreamento["registrado_hoje"]),
        )

        if not self._deve_persistir(
            nome_impressora,
            payload,
            self._ultimo_payload_cache_rastreamento,
            self._ultima_persistencia_cache_rastreamento,
            self.state_persist_interval,
            force=force,
        ):
            return

        salvar_cache_rastreamento_diario(
            self.historico_storage,
            nome_impressora,
            {
                "data_lista": payload[0],
                "hora_primeiro_registro": payload[1],
                "impressoes_inicio": payload[2],
                "impressoes_acumuladas": payload[3],
                "impressoes_dia": payload[4],
                "registrado_hoje": payload[5],
            },
        )
        self._registrar_persistencia(
            nome_impressora,
            payload,
            self._ultimo_payload_cache_rastreamento,
            self._ultima_persistencia_cache_rastreamento,
        )

    # Persiste o rastreamento mensal quando houve mudança relevante
    def _persistir_rastreamento_mes(self, nome_impressora, force=False):
        rastreamento = self.rastreamento_mes[nome_impressora]
        payload = (
            rastreamento["mes_referencia"],
            rastreamento["impressoes_inicio"],
            int(rastreamento["impressoes_acumuladas"]),
            int(rastreamento["impressoes_mes"]),
            bool(rastreamento["registrado_mes"]),
        )

        if not self._deve_persistir(
            nome_impressora,
            payload,
            self._ultimo_payload_rastreamento_mes,
            self._ultima_persistencia_rastreamento_mes,
            self.state_persist_interval,
            force=force,
        ):
            return

        salvar_rastreamento_mensal(
            self.historico_storage,
            nome_impressora,
            {
                "mes_referencia": payload[0],
                "impressoes_inicio": payload[1],
                "impressoes_acumuladas": payload[2],
                "impressoes_mes": payload[3],
                "registrado_mes": payload[4],
            },
        )
        self._registrar_persistencia(
            nome_impressora,
            payload,
            self._ultimo_payload_rastreamento_mes,
            self._ultima_persistencia_rastreamento_mes,
        )

    # Persiste dados estáveis da impressora quando houve mudança relevante
    def _persistir_cache_impressora(self, nome_impressora, dados_cache, force=False):
        self.cache_impressoras[nome_impressora] = dados_cache
        payload = (
            dados_cache.get("ip"),
            dados_cache.get("nome"),
            dados_cache.get("num_serie"),
            dados_cache.get("modelo"),
            dados_cache.get("asset_number"),
            dados_cache.get("location"),
            dados_cache.get("uptime"),
            dados_cache.get("mac"),
        )

        if not self._deve_persistir(
            nome_impressora,
            payload,
            self._ultimo_payload_cache_impressora,
            self._ultima_persistencia_cache_impressora,
            self.printer_cache_persist_interval,
            force=force,
        ):
            return

        salvar_cache_impressora(self.historico_storage, nome_impressora, dados_cache)
        self._registrar_persistencia(
            nome_impressora,
            payload,
            self._ultimo_payload_cache_impressora,
            self._ultima_persistencia_cache_impressora,
        )

    # inicia as threads de monitoramento
    def start(self):
        with self._lock:
            if self._threads_started:
                return

            for config in self.printer_configs:
                thread = threading.Thread(
                    target=self._monitor_loop,
                    args=(config["ip"], config["community"], config["id"]),
                    daemon=True,
                    name=f"Monitor-{config['id']}",
                )
                thread.start()
                self._threads_por_impressora[config["id"]] = thread
                print(f"Thread iniciada para: {config['id']} ({config['ip']})")

            self._threads_started = True

    # Adiciona uma nova impressora ao monitoramento em memória e inicia sua thread
    def add_printer(self, config):
        with self._lock:
            impressora_id = str(config.get("id") or "").strip()
            ip = str(config.get("ip") or "").strip()
            community = str(config.get("community") or "").strip()

            if not impressora_id:
                raise ValueError("A nova impressora precisa de um identificador.")
            if not ip:
                raise ValueError("A nova impressora precisa de um IP.")
            if not community:
                raise ValueError("A nova impressora precisa de uma community SNMP.")

            if any(
                str(impressora.get("id") or "").lower() == impressora_id.lower()
                for impressora in self.printer_configs
            ):
                raise RuntimeError(f"A impressora '{impressora_id}' ja esta cadastrada.")

            if any(str(impressora.get("ip") or "").strip() == ip for impressora in self.printer_configs):
                raise RuntimeError(f"Ja existe uma impressora cadastrada com o IP {ip}.")

            self.printer_configs.append(
                {
                    "id": impressora_id,
                    "ip": ip,
                    "community": community,
                }
            )
            self._impressoras_removidas.discard(impressora_id)
            self.resultado_global["impressoras"][impressora_id] = {"online": False, "ip": ip, "nome": impressora_id}
            self.cache_rastreamento_dia[impressora_id] = self._criar_cache_rastreamento_dia_inicial()
            self.rastreamento_mes[impressora_id] = self._criar_rastreamento_mensal_inicial()

            if self._threads_started:
                thread = threading.Thread(
                    target=self._monitor_loop,
                    args=(ip, community, impressora_id),
                    daemon=True,
                    name=f"Monitor-{impressora_id}",
                )
                thread.start()
                self._threads_por_impressora[impressora_id] = thread
                print(f"Thread iniciada para: {impressora_id} ({ip})")

    # Remove uma impressora do monitoramento em memória e sinaliza a thread para encerrar
    def remove_printer(self, impressora_id):
        with self._lock:
            impressora_id = str(impressora_id or "").strip()
            if not impressora_id:
                raise ValueError("Informe a impressora que deseja excluir.")

            indice_config = next(
                (
                    indice
                    for indice, config in enumerate(self.printer_configs)
                    if str(config.get("id") or "") == impressora_id
                ),
                None,
            )

            if indice_config is None:
                raise ValueError("Impressora nao encontrada.")

            self.printer_configs.pop(indice_config)
            self._impressoras_removidas.add(impressora_id)
            self.resultado_global["impressoras"].pop(impressora_id, None)
            self.cache_rastreamento_dia.pop(impressora_id, None)
            self.rastreamento_mes.pop(impressora_id, None)
            self.cache_impressoras.pop(impressora_id, None)
            self.cache_rastreamento_dia_persistido.pop(impressora_id, None)
            self.rastreamento_mes_persistido.pop(impressora_id, None)
            self._ultimo_payload_cache_rastreamento.pop(impressora_id, None)
            self._ultimo_payload_rastreamento_mes.pop(impressora_id, None)
            self._ultimo_payload_cache_impressora.pop(impressora_id, None)
            self._ultima_persistencia_cache_rastreamento.pop(impressora_id, None)
            self._ultima_persistencia_rastreamento_mes.pop(impressora_id, None)
            self._ultima_persistencia_cache_impressora.pop(impressora_id, None)
            self._ultima_atualizacao_snmp_estavel.pop(impressora_id, None)
            self._threads_por_impressora.pop(impressora_id, None)
    
    # devolve os dados atuais para /api
    def get_resultado(self):
        with self._lock:
            tokens_por_impressora = {
                config["id"]: config.get("token_tipo", "pb")
                for config in self.printer_configs
            }
            return {
                "impressoras": {
                    nome: {
                        **dados,
                        "token_tipo": tokens_por_impressora.get(nome, "pb"),
                    }
                    for nome, dados in self.resultado_global["impressoras"].items()
                }
            }

    # Retorna a lista resumida de impressoras usada pela tela de configurações e relatórios
    def get_impressoras_resumo(self):
        with self._lock:
            linhas = []

            for config in self.printer_configs:
                impressora_id = config["id"]
                dados_atuais = self.resultado_global["impressoras"].get(impressora_id, {})
                dados_cache = self.cache_impressoras.get(impressora_id, {})
                rastreamento_dia = self.cache_rastreamento_dia.get(impressora_id, {})
                rastreamento_mes = self.rastreamento_mes.get(impressora_id, {})
                chave_contador_copias = f"{impressora_id}__copias"
                rastreamento_copias_dia = self.cache_rastreamento_dia.get(chave_contador_copias, {})
                rastreamento_copias_mes = self.rastreamento_mes.get(chave_contador_copias, {})
                impressoes_dia = int(
                    dados_atuais.get("impressoes_dia")
                    if dados_atuais.get("impressoes_dia") is not None
                    else self._obter_total_cache_rastreamento_dia(rastreamento_dia)
                )
                impressoes_mes = int(
                    dados_atuais.get("impressoes_mes")
                    if dados_atuais.get("impressoes_mes") is not None
                    else self._obter_total_rastreamento_mensal(rastreamento_mes)
                )
                copias_dia = int(
                    dados_atuais.get("copias_dia")
                    if dados_atuais.get("copias_dia") is not None
                    else self._obter_total_cache_rastreamento_dia(rastreamento_copias_dia)
                )
                copias_mes = int(
                    dados_atuais.get("copias_mes")
                    if dados_atuais.get("copias_mes") is not None
                    else self._obter_total_rastreamento_mensal(rastreamento_copias_mes)
                )

                linhas.append(
                    {
                        "id": impressora_id,
                        "token_tipo": config.get("token_tipo", "pb"),
                        "nome": dados_atuais.get("nome") or dados_cache.get("nome") or impressora_id,
                        "online": bool(dados_atuais.get("online")),
                        "ip": dados_atuais.get("ip") or dados_cache.get("ip") or config.get("ip"),
                        "modelo": dados_atuais.get("modelo") or dados_cache.get("modelo"),
                        "total_impressoes": int(dados_atuais.get("total_impressoes") or 0),
                        "impressoes_dia": impressoes_dia,
                        "impressoes_mes": impressoes_mes,
                        "copias": int(dados_atuais.get("copias") or 0),
                        "copias_dia": copias_dia,
                        "copias_mes": copias_mes,
                        "scanner": dados_atuais.get("scanner"),
                        "toner": dados_atuais.get("toner"),
                        "location": dados_atuais.get("location") or dados_cache.get("location"),
                    }
                )

            return linhas

    # Monta um mapa de id para nome amigável da impressora
    def get_mapa_nomes_impressoras(self):
        with self._lock:
            return {
                config["id"]: (
                    self.resultado_global["impressoras"].get(config["id"], {}).get("nome")
                    or self.cache_impressoras.get(config["id"], {}).get("nome")
                    or config["id"]
                )
                for config in self.printer_configs
            }
    
    # devolve histórico de impressões para /api/historico
    def get_historico(self):
        with self._lock:
            self.historico_impressoes = carregar_historico(self.historico_storage)
            return dict(self.historico_impressoes)

    # Retorna informações de diagnóstico sobre ciclos, caches e intervalos do monitor
    def get_debug_info(self):
        agora = datetime.now()

        with self._lock:
            return {
                "agora": agora.isoformat(sep=" "),
                "daily_close_time": self.daily_close_time.isoformat(timespec="minutes"),
                "data_ciclo_atual": self._obter_data_ciclo_atual(agora).isoformat(),
                "armazenamento_historico": "MariaDB",
                "state_persist_interval": self.state_persist_interval,
                "printer_cache_persist_interval": self.printer_cache_persist_interval,
                "snmp_stable_refresh_interval": self.snmp_stable_refresh_interval,
                "cache_rastreamento_count": len(self.cache_rastreamento_dia),
                "historico_count_memoria": len(self.historico_impressoes),
            }

    # Força o salvamento do histórico diário atual para cada impressora rastreada
    def forcar_salvamento_historico(self, motivo="teste_manual"):
        salvos = []

        with self._lock:
            for nome_impressora, rastreamento in self.cache_rastreamento_dia.items():
                if rastreamento.get("data_lista") is None or rastreamento.get("impressoes_dia") is None:
                    continue

                total_consolidado = self._obter_total_cache_rastreamento_dia(rastreamento)
                self._salvar_impressoes_dia(nome_impressora, rastreamento, motivo=motivo)
                salvos.append(
                    {
                        "impressora": nome_impressora,
                        "data": str(rastreamento["data_lista"]),
                        "impressoes_total_dia": total_consolidado,
                    }
                )

        return salvos

    # Soma as impressões acumuladas e as impressões do ciclo diário atual
    def _obter_total_cache_rastreamento_dia(self, rastreamento):
        acumuladas = int(rastreamento.get("impressoes_acumuladas", 0) or 0)
        atual = int(rastreamento.get("impressoes_dia", 0) or 0)
        return acumuladas + atual

    # Soma as impressões acumuladas e as impressões do ciclo mensal atual
    def _obter_total_rastreamento_mensal(self, rastreamento):
        acumuladas = int(rastreamento.get("impressoes_acumuladas", 0) or 0)
        atual = int(rastreamento.get("impressoes_mes", 0) or 0)
        return acumuladas + atual

    # Garante que a impressora tenha uma estrutura de rastreamento diário em memória
    def _garantir_rastreamento_dia(self, nome_impressora):
        if nome_impressora not in self.cache_rastreamento_dia:
            self.cache_rastreamento_dia[nome_impressora] = self._criar_cache_rastreamento_dia_inicial()

        return self.cache_rastreamento_dia[nome_impressora]

    # Garante que a impressora tenha uma estrutura de rastreamento mensal em memória
    def _garantir_rastreamento_mes(self, nome_impressora):
        if nome_impressora not in self.rastreamento_mes:
            self.rastreamento_mes[nome_impressora] = self._criar_rastreamento_mensal_inicial()

        return self.rastreamento_mes[nome_impressora]
    
    # método atualizado, que considera o caso de impressões diárias acumuladas
    def _salvar_impressoes_dia(self, nome_impressora, rastreamento, motivo="fechamento_dia"):
        if not rastreamento["data_lista"] or rastreamento["impressoes_dia"] is None:
            return

        data_str = str(rastreamento["data_lista"])
        timestamp = datetime.now().strftime("%H%M%S")
        chave = f"{nome_impressora}_{data_str}_{motivo}_{timestamp}"
        total_consolidado = self._obter_total_cache_rastreamento_dia(rastreamento)

        registro = {
            "impressora": nome_impressora,
            "data": data_str,
            "hora_inicio": (
                str(rastreamento["hora_primeiro_registro"])
                if rastreamento["hora_primeiro_registro"]
                else "N/A"
            ),
            "impressoes_total": total_consolidado,
            "motivo": motivo,
            "timestamp_salvo": str(datetime.now()),
        }
        self.historico_impressoes[chave] = registro

        salvar_registro_historico(self.historico_storage, chave, registro)

    # Atualiza o rastreamento diário com a leitura atual e trata reset do contador físico
    def _atualizar_rastreamento_dia_com_impressoes(self, nome_impressora, rastreamento, impressoes_atuais):
        if rastreamento["impressoes_inicio"] is None:
            rastreamento["impressoes_inicio"] = impressoes_atuais
            return self._obter_total_cache_rastreamento_dia(rastreamento)

        total = impressoes_atuais - rastreamento["impressoes_inicio"]

        if total < 0:
            total_anterior = int(rastreamento.get("impressoes_dia", 0) or 0)

            if total_anterior > 0:
                rastreamento["impressoes_acumuladas"] += total_anterior
                self._salvar_impressoes_dia(
                    nome_impressora,
                    rastreamento,
                    motivo="reset_contador",
                )

            rastreamento["impressoes_inicio"] = impressoes_atuais
            rastreamento["impressoes_dia"] = 0
            total = 0

        rastreamento["impressoes_dia"] = total

        return self._obter_total_cache_rastreamento_dia(rastreamento)

    # calcula impressões do dia, considerando reinício do contador e acumulados
    def _calcular_impressoes_dia(self, nome_impressora, impressoes_atuais):
        if impressoes_atuais is None:
            return 0

        rastreamento = self._garantir_rastreamento_dia(nome_impressora)
        agora = datetime.now()
        data_ciclo = self._obter_data_ciclo_atual(agora)

        if rastreamento["data_lista"] is None:
            self._reiniciar_rastreamento_dia(rastreamento, data_ciclo, agora, impressoes_atuais)
            self._salvar_cache_rastreamento_dia(nome_impressora, force=True)
            return 0

        if rastreamento["data_lista"] < data_ciclo:
            self._atualizar_rastreamento_dia_com_impressoes(
                nome_impressora,
                rastreamento,
                impressoes_atuais,
            )
            self._salvar_impressoes_dia(nome_impressora, rastreamento)
            self._reiniciar_rastreamento_dia(rastreamento, data_ciclo, agora, impressoes_atuais)
            self._salvar_cache_rastreamento_dia(nome_impressora, force=True)
            return 0

        if rastreamento["data_lista"] > data_ciclo:
            self._reiniciar_rastreamento_dia(rastreamento, data_ciclo, agora, impressoes_atuais)
            self._salvar_cache_rastreamento_dia(nome_impressora, force=True)
            return 0

        if rastreamento["impressoes_inicio"] is None:
            rastreamento["impressoes_inicio"] = impressoes_atuais
            rastreamento["hora_primeiro_registro"] = (
                rastreamento["hora_primeiro_registro"] or agora.time()
            )
            rastreamento["registrado_hoje"] = False
            self._salvar_cache_rastreamento_dia(nome_impressora, force=True)
            return self._obter_total_cache_rastreamento_dia(rastreamento)

        total_dia = self._atualizar_rastreamento_dia_com_impressoes(
            nome_impressora,
            rastreamento,
            impressoes_atuais,
        )

        self._salvar_cache_rastreamento_dia(nome_impressora)

        return total_dia

    # Calcula as impressões do mês, reiniciando o ciclo quando muda o mês ou o contador físico reseta
    def _calcular_impressoes_mes(self, nome_impressora, impressoes_atuais):
        if impressoes_atuais is None:
            return 0

        rastreamento = self._garantir_rastreamento_mes(nome_impressora)
        mes_atual = datetime.now().strftime("%Y-%m")

        if rastreamento["mes_referencia"] is None:
            rastreamento["mes_referencia"] = mes_atual
            rastreamento["impressoes_inicio"] = impressoes_atuais
            rastreamento["registrado_mes"] = True
            self._persistir_rastreamento_mes(nome_impressora, force=True)
            return 0

        if rastreamento["mes_referencia"] != mes_atual:
            rastreamento["mes_referencia"] = mes_atual
            rastreamento["impressoes_inicio"] = impressoes_atuais
            rastreamento["impressoes_acumuladas"] = 0
            rastreamento["impressoes_mes"] = 0
            rastreamento["registrado_mes"] = True
            self._persistir_rastreamento_mes(nome_impressora, force=True)
            return 0

        if rastreamento["impressoes_inicio"] is None:
            rastreamento["impressoes_inicio"] = impressoes_atuais
            rastreamento["registrado_mes"] = True
            self._persistir_rastreamento_mes(nome_impressora, force=True)
            return self._obter_total_rastreamento_mensal(rastreamento)

        total = impressoes_atuais - rastreamento["impressoes_inicio"]

        if total < 0:
            total_anterior = int(rastreamento.get("impressoes_mes", 0) or 0)

            if total_anterior > 0:
                rastreamento["impressoes_acumuladas"] += total_anterior

            rastreamento["impressoes_inicio"] = impressoes_atuais
            rastreamento["impressoes_mes"] = 0
            total = 0

        rastreamento["impressoes_mes"] = total
        rastreamento["registrado_mes"] = True
        self._persistir_rastreamento_mes(nome_impressora)

        return self._obter_total_rastreamento_mensal(rastreamento)

    # método que monta o status offline, para evitar repetição de código
    def _montar_status_offline(self, nome_impressora, ip):
        dados_cache = self.cache_impressoras.get(nome_impressora, {})
        dados_anteriores = self.resultado_global["impressoras"].get(nome_impressora, {})
        contadores = {}
        for prefixo, chave in (("impressoes", nome_impressora), ("copias", f"{nome_impressora}__copias")):
            for periodo, rastreamentos, obter_total in (
                ("dia", self.cache_rastreamento_dia, self._obter_total_cache_rastreamento_dia),
                ("mes", self.rastreamento_mes, self._obter_total_rastreamento_mensal),
            ):
                campo = f"{prefixo}_{periodo}"
                valor = dados_anteriores.get(campo)
                contadores[campo] = valor if valor is not None else obter_total(rastreamentos.get(chave, {}))

        return {
            **contadores,
            "online": False,
            "ip": dados_cache.get("ip") or ip,
            "nome": dados_cache.get("nome") or nome_impressora,
            "num_serie": dados_cache.get("num_serie") or "N/A",
            "modelo": dados_cache.get("modelo") or "N/A",
            "asset_number": dados_cache.get("asset_number") or "N/A",
            "location": dados_cache.get("location") or "N/A",
            "uptime": dados_cache.get("uptime") or "N/A",
            "mac": dados_cache.get("mac") or "N/A",
            "problemas": [],
            "erro": "Sem resposta SNMP",
        }

    # Converte a leitura do suprimento para percentual, inclusive quando o equipamento retorna unidades
    @staticmethod
    def _calcular_percentual_toner(nivel, capacidade):
        try:
            nivel = int(nivel)
        except (TypeError, ValueError):
            return None

        if nivel < 0:
            return None

        try:
            capacidade = int(capacidade)
        except (TypeError, ValueError):
            capacidade = None

        if capacidade is not None and capacidade > 0:
            return max(0, min(100, round((nivel / capacidade) * 100)))

        # Alguns modelos já fornecem diretamente o percentual neste OID.
        return nivel if nivel <= 100 else None

    # Soma os contadores da tabela Samsung por tipo de trabalho: 1=impressao e 2=copia.
    @staticmethod
    def _somar_contadores_samsung(linhas):
        totais = {1: 0, 2: 0}
        for tipo_trabalho, valor in linhas:
            if tipo_trabalho in totais and int(valor) >= 0:
                totais[tipo_trabalho] += int(valor)

        return totais[1], totais[2]

    # Lê a tabela proprietária usada pelas multifuncionais Samsung para impressão e cópia.
    def _obter_contadores_samsung(self, engine, ip, community):
        linhas = snmp_walk_pares(
            engine,
            ip,
            community,
            SNMP_OIDS["samsung_contador_tipo"],
            SNMP_OIDS["samsung_contador_valor"],
        )
        return self._somar_contadores_samsung(linhas) if linhas else (None, None)

    @staticmethod
    def _formatar_timeticks_alerta(valor):
        try:
            centesimos = max(int(valor), 0)
        except (TypeError, ValueError):
            return None

        segundos = centesimos // 100
        dias, segundos = divmod(segundos, 86400)
        horas, segundos = divmod(segundos, 3600)
        minutos, segundos = divmod(segundos, 60)
        return f"{dias}d {horas:02d}:{minutos:02d}:{segundos:02d}"

    @staticmethod
    def _classificar_alerta_impressora(codigo, descricao):
        texto = str(descricao or "").strip()
        normalizado = texto.casefold()

        if any(
            termo in normalizado
            for termo in ("document jam", "original jam", "adf jam")
        ):
            return "atolamento_documento", "Atolamento de documento no alimentador"
        if codigo == 8 or any(
            termo in normalizado
            for termo in ("paper jam", "media jam", "jammed", "atolamento")
        ):
            return "atolamento_papel", "Atolamento de papel"
        if codigo in (3, 501) or any(
            termo in normalizado
            for termo in ("cover open", "door open", "tampa aberta", "porta aberta")
        ):
            return "tampa_aberta", "Tampa aberta"
        if any(
            termo in normalizado
            for termo in ("no paper", "paper empty", "out of paper", "paper out", "sem papel")
        ):
            return "sem_papel", "Sem papel"
        if "toner" in normalizado and any(
            termo in normalizado for termo in ("low", "almost empty", "baixo")
        ):
            return "toner_baixo", "Toner baixo"
        if "toner" in normalizado and any(
            termo in normalizado for termo in ("empty", "vazio")
        ):
            return "toner_vazio", "Toner vazio"
        if "ink" in normalizado and any(
            termo in normalizado for termo in ("low", "almost empty")
        ):
            return "tinta_baixa", "Tinta quase vazia"
        if "ink" in normalizado and "empty" in normalizado:
            return "tinta_vazia", "Tinta vazia"
        if "output" in normalizado and "tray" in normalizado and "full" in normalizado:
            return "bandeja_saida_cheia", "Bandeja de saída cheia"
        if "waste toner" in normalizado and "full" in normalizado:
            return "residuo_cheio", "Reservatório de toner residual cheio"
        if any(
            termo in normalizado
            for termo in ("service call", "service required", "maintenance required")
        ):
            return "manutencao", "Manutenção técnica necessária"

        traducao = ALERTAS_PRINTER_MIB_TRADUZIDOS.get(codigo)
        if traducao:
            return traducao

        return "outro", texto or "Alerta da impressora"

    @classmethod
    def _normalizar_alertas_printer_mib(cls, linhas):
        raiz = tuple(int(parte) for parte in SNMP_OIDS["alertas"].split("."))
        colunas = {
            1: "indice",
            2: "severidade_codigo",
            3: "treinamento_codigo",
            4: "grupo_codigo",
            5: "grupo_indice",
            6: "localizacao",
            7: "codigo",
            8: "descricao_original",
            9: "uptime_evento_ticks",
        }
        alertas_por_indice = {}

        for oid, valor in linhas:
            oid = tuple(int(parte) for parte in oid)
            if oid[: len(raiz)] != raiz:
                continue

            sufixo = oid[len(raiz) :]
            if len(sufixo) < 3 or sufixo[0] not in colunas:
                continue

            coluna, dispositivo, indice_alerta = sufixo[:3]
            alerta = alertas_por_indice.setdefault(
                (dispositivo, indice_alerta),
                {
                    "id": f"{dispositivo}-{indice_alerta}",
                    "dispositivo_indice": dispositivo,
                    "indice": indice_alerta,
                },
            )
            chave = colunas[coluna]

            if coluna == 8:
                alerta[chave] = str(valor).strip()
            else:
                try:
                    alerta[chave] = int(valor)
                except (TypeError, ValueError):
                    alerta[chave] = None

        alertas = []
        for alerta in alertas_por_indice.values():
            codigo = alerta.get("codigo")
            if codigo in CODIGOS_ALERTA_SEM_PROBLEMA:
                continue

            descricao = alerta.get("descricao_original") or ""
            tipo, mensagem = cls._classificar_alerta_impressora(codigo, descricao)
            severidade_codigo = alerta.get("severidade_codigo")
            severidade = (
                "critica"
                if severidade_codigo == 3
                else "aviso"
                if severidade_codigo in (4, 5)
                else "informativa"
            )

            alerta.update(
                {
                    "codigo": codigo,
                    "tipo": tipo,
                    "mensagem": mensagem,
                    "severidade": severidade,
                    "uptime_evento": cls._formatar_timeticks_alerta(
                        alerta.get("uptime_evento_ticks")
                    ),
                }
            )
            alertas.append(alerta)

        prioridade = {"critica": 0, "aviso": 1, "informativa": 2}
        return sorted(
            alertas,
            key=lambda alerta: (
                prioridade.get(alerta["severidade"], 3),
                alerta["mensagem"].casefold(),
                alerta["indice"],
            ),
        )

    def _obter_alertas_impressora(self, engine, ip, community):
        linhas = snmp_walk_tabela(
            engine,
            ip,
            community,
            SNMP_OIDS["alertas"],
        )
        return self._normalizar_alertas_printer_mib(linhas)

    # Usa o contador total padrão nas Epson, que não respondem aos OIDs proprietários da OKI.
    @staticmethod
    def _aplicar_fallback_contadores_epson(modelo, nome, total_impressoes, impressoes, copias):
        identificacao = f"{modelo or ''} {nome or ''}".upper()
        if "EPSON" not in identificacao:
            return impressoes, copias

        if impressoes is None:
            impressoes = total_impressoes
        if copias is None:
            copias = 0

        return impressoes, copias

    # método que monitora a impressora e coleta os dados via SNMP
    def _monitorar_impressora(self, engine, ip, community, nome_impressora):
        uptime = snmp_get(engine, ip, community, SNMP_OIDS["uptime"])

        if uptime is None:
            return self._montar_status_offline(nome_impressora, ip)

        uptime_ticks = int(uptime)
        seconds = int(uptime_ticks // 100)
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60

        dados_estaveis = self._obter_dados_estaveis_impressora(engine, ip, community, nome_impressora)
        total_impressoes = snmp_get(engine, ip, community, SNMP_OIDS["total_impressoes"])
        impressoes = snmp_get(engine, ip, community, SNMP_OIDS["impressoes"])
        copias = snmp_get(engine, ip, community, SNMP_OIDS["copias"])
        toner_capacidade = snmp_get(engine, ip, community, SNMP_OIDS["toner_capacidade"])
        toner = snmp_get(engine, ip, community, SNMP_OIDS["toner"])
        status = snmp_get(engine, ip, community, SNMP_OIDS["status"])
        scanner = snmp_get(engine, ip, community, SNMP_OIDS["scanner"])
        problemas = self._obter_alertas_impressora(engine, ip, community)

        if "SAMSUNG" in dados_estaveis["modelo"].upper() and (impressoes is None or copias is None):
            impressoes_samsung, copias_samsung = self._obter_contadores_samsung(
                engine,
                ip,
                community,
            )
            impressoes = impressoes if impressoes is not None else impressoes_samsung
            copias = copias if copias is not None else copias_samsung

        impressoes, copias = self._aplicar_fallback_contadores_epson(
            dados_estaveis["modelo"],
            dados_estaveis["nome"],
            total_impressoes,
            impressoes,
            copias,
        )

        toner = self._calcular_percentual_toner(toner, toner_capacidade)
        total_impressoes = int(total_impressoes) if total_impressoes is not None else None
        impressoes = int(impressoes) if impressoes is not None else None
        copias = int(copias) if copias is not None else None

        with self._lock:
            impressoes_dia = self._calcular_impressoes_dia(nome_impressora, total_impressoes)
            impressoes_mes_legado = self._calcular_impressoes_mes(nome_impressora, total_impressoes)
            impressoes_mes = (
                registrar_leitura_contador(
                    self.historico_storage,
                    nome_impressora,
                    total_impressoes,
                    saldo_inicial=impressoes_mes_legado,
                    mac=dados_estaveis["mac"],
                )
                if total_impressoes is not None
                else impressoes_mes_legado
            )
            chave_contador_copias = f"{nome_impressora}__copias"
            copias_dia = self._calcular_impressoes_dia(chave_contador_copias, copias)
            copias_mes_legado = self._calcular_impressoes_mes(chave_contador_copias, copias)
            copias_mes = (
                registrar_leitura_contador(
                    self.historico_storage,
                    chave_contador_copias,
                    copias,
                    saldo_inicial=copias_mes_legado,
                    mac=dados_estaveis["mac"],
                )
                if copias is not None
                else copias_mes_legado
            )

            self._persistir_cache_impressora(
                nome_impressora,
                {
                    "ip": ip,
                    "nome": dados_estaveis["nome"],
                    "num_serie": dados_estaveis["num_serie"],
                    "modelo": dados_estaveis["modelo"],
                    "asset_number": dados_estaveis["asset_number"],
                    "location": dados_estaveis["location"],
                    "uptime": f"{days} Dias / {hours} Horas / {minutes} Minutos",
                    "mac": dados_estaveis["mac"],
                    "atualizado_em": str(datetime.now()),
                },
            )

        return {
            "online": True,
            "ip": ip,
            "nome": dados_estaveis["nome"],
            "num_serie": dados_estaveis["num_serie"],
            "modelo": dados_estaveis["modelo"],
            "asset_number": dados_estaveis["asset_number"],
            "location": dados_estaveis["location"],
            "total_impressoes": total_impressoes,
            "impressoes": impressoes,
            "copias": copias,
            "copias_dia": copias_dia,
            "copias_mes": copias_mes,
            "impressoes_dia": impressoes_dia,
            "impressoes_mes": impressoes_mes,
            "toner": f"{toner}%" if toner is not None else "N/A",
            "status": str(status),
            "problemas": problemas,
            "uptime": f"{days} Dias / {hours} Horas / {minutes} Minutos",
            "scanner": str(scanner),
            "mac": dados_estaveis["mac"],
        }

    # loop principal de monitoramento, que chama o método de coleta e atualiza o resultado global
    def _monitor_loop(self, ip, community, nome_impressora):
        # Uma única engine SNMP por thread/impressora, reaproveitada em todos os
        # ciclos: criar uma nova a cada leitura força o pysnmp a recarregar e
        # recompilar as MIBs (pysmi/ply) repetidamente, o que é pesado de CPU e
        # prende a GIL, deixando até as rotas HTTP simples lentas.
        engine = criar_snmp_engine()

        while True:
            with self._lock:
                if nome_impressora in self._impressoras_removidas:
                    return
            try:
                dados = self._monitorar_impressora(engine, ip, community, nome_impressora)
            except Exception as exc:
                print(f"Erro no monitoramento de {nome_impressora}: {exc}")
                print(traceback.format_exc())
                dados = {
                    **self._montar_status_offline(nome_impressora, ip),
                    "erro": f"Falha interna: {exc}",
                }

            with self._lock:
                if nome_impressora in self._impressoras_removidas:
                    return
                self.resultado_global["impressoras"][nome_impressora] = dados

            time.sleep(self.monitor_interval)

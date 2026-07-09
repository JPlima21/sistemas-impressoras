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
    salvar_cache_impressora,
    salvar_cache_rastreamento_diario,
    salvar_registro_historico,
    salvar_rastreamento_mensal,
)
from services.snmp_service import formatar_mac, snmp_get

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
            cache_rastreamento = self._criar_cache_rastreamento_dia_inicial()
            cache_rastreamento_persistido = self.cache_rastreamento_dia_persistido.get(impressora_id)
            rastreamento_mensal = self._criar_rastreamento_mensal_inicial()
            rastreamento_mensal_persistido = self.rastreamento_mes_persistido.get(impressora_id)

            if cache_rastreamento_persistido:
                cache_rastreamento.update(
                    self._normalizar_cache_rastreamento_dia_persistido(cache_rastreamento_persistido)
                )
            if rastreamento_mensal_persistido:
                rastreamento_mensal.update(
                    self._normalizar_rastreamento_mensal_persistido(rastreamento_mensal_persistido)
                )

            self.cache_rastreamento_dia[impressora_id] = cache_rastreamento
            self.rastreamento_mes[impressora_id] = rastreamento_mensal
 
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
    def _obter_dados_estaveis_impressora(self, ip, community, nome_impressora):
        cache_atual = dict(self.cache_impressoras.get(nome_impressora, {}))

        if self._deve_atualizar_dados_estaveis_snmp(nome_impressora):
            cache_atual.update(
                {
                    "nome": str(snmp_get(ip, community, SNMP_OIDS["nome"])),
                    "modelo": str(snmp_get(ip, community, SNMP_OIDS["modelo"])),
                    "num_serie": str(snmp_get(ip, community, SNMP_OIDS["serial"])),
                    "asset_number": str(snmp_get(ip, community, SNMP_OIDS["asset_number"])),
                    "location": str(snmp_get(ip, community, SNMP_OIDS["location"])),
                    "mac": formatar_mac(snmp_get(ip, community, SNMP_OIDS["mac"])),
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
            return {
                "impressoras": {
                    nome: dados.copy()
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
            total = impressoes_atuais

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
            total = impressoes_atuais

        rastreamento["impressoes_mes"] = total
        rastreamento["registrado_mes"] = True
        self._persistir_rastreamento_mes(nome_impressora)

        return self._obter_total_rastreamento_mensal(rastreamento)

    # método que monta o status offline, para evitar repetição de código
    def _montar_status_offline(self, nome_impressora, ip):
        dados_cache = self.cache_impressoras.get(nome_impressora, {})

        return {
            "online": False,
            "ip": dados_cache.get("ip") or ip,
            "nome": dados_cache.get("nome") or nome_impressora,
            "num_serie": dados_cache.get("num_serie") or "N/A",
            "modelo": dados_cache.get("modelo") or "N/A",
            "asset_number": dados_cache.get("asset_number") or "N/A",
            "location": dados_cache.get("location") or "N/A",
            "uptime": dados_cache.get("uptime") or "N/A",
            "mac": dados_cache.get("mac") or "N/A",
            "erro": "Sem resposta SNMP",
        }

    # método que monitora a impressora e coleta os dados via SNMP
    def _monitorar_impressora(self, ip, community, nome_impressora):
        uptime = snmp_get(ip, community, SNMP_OIDS["uptime"])

        if uptime is None:
            return self._montar_status_offline(nome_impressora, ip)

        uptime_ticks = int(uptime)
        seconds = int(uptime_ticks // 100)
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        minutes = (seconds % 3600) // 60

        dados_estaveis = self._obter_dados_estaveis_impressora(ip, community, nome_impressora)
        total_impressoes = snmp_get(ip, community, SNMP_OIDS["total_impressoes"])
        impressoes = snmp_get(ip, community, SNMP_OIDS["impressoes"])
        copias = snmp_get(ip, community, SNMP_OIDS["copias"])
        toner = snmp_get(ip, community, SNMP_OIDS["toner"])
        status = snmp_get(ip, community, SNMP_OIDS["status"])
        scanner = snmp_get(ip, community, SNMP_OIDS["scanner"])

        toner = int(toner) if toner and int(toner) >= 0 else None
        total_impressoes = int(total_impressoes) if total_impressoes else None
        impressoes = int(impressoes) if impressoes else None
        copias = int(copias) if copias else None

        with self._lock:
            impressoes_dia = self._calcular_impressoes_dia(nome_impressora, total_impressoes)
            impressoes_mes = self._calcular_impressoes_mes(nome_impressora, total_impressoes)

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
            "impressoes_dia": impressoes_dia,
            "impressoes_mes": impressoes_mes,
            "toner": f"{toner}%" if toner is not None else "N/A",
            "status": str(status),
            "uptime": f"{days} Dias / {hours} Horas / {minutes} Minutos",
            "scanner": str(scanner),
            "mac": dados_estaveis["mac"],
        }

    # loop principal de monitoramento, que chama o método de coleta e atualiza o resultado global
    def _monitor_loop(self, ip, community, nome_impressora):
        while True:
            with self._lock:
                if nome_impressora in self._impressoras_removidas:
                    return
            try:
                dados = self._monitorar_impressora(ip, community, nome_impressora)
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

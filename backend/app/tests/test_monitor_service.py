import unittest
import threading
from datetime import date, time

from services.monitor_service import PrinterMonitorService


class CalcularPercentualTonerTest(unittest.TestCase):
    def test_converte_unidades_usando_capacidade_maxima(self):
        self.assertEqual(50, PrinterMonitorService._calcular_percentual_toner(2500, 5000))

    def test_mantem_percentual_quando_capacidade_nao_esta_disponivel(self):
        self.assertEqual(75, PrinterMonitorService._calcular_percentual_toner(75, None))

    def test_rejeita_valor_exagerado_sem_capacidade(self):
        self.assertIsNone(PrinterMonitorService._calcular_percentual_toner(5000, None))

    def test_limita_resultado_a_cem_por_cento(self):
        self.assertEqual(100, PrinterMonitorService._calcular_percentual_toner(6000, 5000))

    def test_rejeita_valores_especiais_do_snmp(self):
        self.assertIsNone(PrinterMonitorService._calcular_percentual_toner(-2, 5000))


class GetResultadoTest(unittest.TestCase):
    def test_inclui_token_colorido_cadastrado_na_resposta(self):
        service = PrinterMonitorService.__new__(PrinterMonitorService)
        service._lock = threading.Lock()
        service.printer_configs = [
            {"id": "impressora11", "token_tipo": "colorida"},
        ]
        service.resultado_global = {
            "impressoras": {
                "impressora11": {"nome": "OKIPRESIDENCIA_COLOR", "online": True},
            },
        }

        resultado = service.get_resultado()

        self.assertEqual(
            "colorida",
            resultado["impressoras"]["impressora11"]["token_tipo"],
        )


class SomarContadoresSamsungTest(unittest.TestCase):
    def test_soma_impressoes_e_copias_por_tipo_de_trabalho(self):
        linhas = [
            (1, 14296),
            (1, 17714),
            (2, 1785),
            (2, 924),
            (6, 37),
        ]

        impressoes, copias = PrinterMonitorService._somar_contadores_samsung(linhas)

        self.assertEqual(32010, impressoes)
        self.assertEqual(2709, copias)


class FallbackContadoresEpsonTest(unittest.TestCase):
    def test_usa_total_como_impressoes_e_zero_como_copias_quando_oids_nao_respondem(self):
        impressoes, copias = PrinterMonitorService._aplicar_fallback_contadores_epson(
            "EPSON WorkForce",
            "EPSONIMPRENSA.OABCE",
            3961,
            None,
            None,
        )

        self.assertEqual(3961, impressoes)
        self.assertEqual(0, copias)

    def test_preserva_contadores_especificos_quando_disponiveis(self):
        impressoes, copias = PrinterMonitorService._aplicar_fallback_contadores_epson(
            "EPSON WorkForce",
            "EPSONIMPRENSA.OABCE",
            3961,
            3000,
            961,
        )

        self.assertEqual(3000, impressoes)
        self.assertEqual(961, copias)

    def test_nao_altera_contadores_de_outros_fabricantes(self):
        impressoes, copias = PrinterMonitorService._aplicar_fallback_contadores_epson(
            "OKI MC873",
            "OKI-CALLCENTER",
            3961,
            None,
            None,
        )

        self.assertIsNone(impressoes)
        self.assertIsNone(copias)


class AlertasPrinterMibTest(unittest.TestCase):
    RAIZ = (1, 3, 6, 1, 2, 1, 43, 18, 1, 1)

    def test_normaliza_tampa_aberta_reportada_pela_oki(self):
        indice = (1, 36)
        ticks = ((2 * 86400) + (18 * 3600) + (26 * 60) + 20) * 100 + 56
        linhas = [
            (self.RAIZ + (1,) + indice, 36),
            (self.RAIZ + (2,) + indice, 3),
            (self.RAIZ + (3,) + indice, 3),
            (self.RAIZ + (4,) + indice, 1),
            (self.RAIZ + (5,) + indice, -1),
            (self.RAIZ + (6,) + indice, 40788),
            (self.RAIZ + (7,) + indice, 1),
            (self.RAIZ + (8,) + indice, "Cover Open"),
            (self.RAIZ + (9,) + indice, ticks),
        ]

        alertas = PrinterMonitorService._normalizar_alertas_printer_mib(linhas)

        self.assertEqual(1, len(alertas))
        self.assertEqual("1-36", alertas[0]["id"])
        self.assertEqual("critica", alertas[0]["severidade"])
        self.assertEqual("tampa_aberta", alertas[0]["tipo"])
        self.assertEqual("Tampa aberta", alertas[0]["mensagem"])
        self.assertEqual("Cover Open", alertas[0]["descricao_original"])
        self.assertEqual("2d 18:26:20", alertas[0]["uptime_evento"])

    def test_identifica_atolamento_pelo_codigo_padrao(self):
        indice = (1, 40)
        linhas = [
            (self.RAIZ + (1,) + indice, 40),
            (self.RAIZ + (2,) + indice, 3),
            (self.RAIZ + (7,) + indice, 8),
            (self.RAIZ + (8,) + indice, ""),
        ]

        alertas = PrinterMonitorService._normalizar_alertas_printer_mib(linhas)

        self.assertEqual("atolamento_papel", alertas[0]["tipo"])
        self.assertEqual("Atolamento de papel", alertas[0]["mensagem"])

    def test_traduz_codigos_padrao_de_diferentes_grupos(self):
        casos = {
            808: ("sem_papel", "Bandeja sem papel"),
            903: ("bandeja_saida_cheia", "Bandeja de saída cheia"),
            1002: ("temperatura_fusor", "Temperatura do fusor acima do normal"),
            1109: ("residuo_cheio", "Reservatório de toner residual cheio"),
            1509: ("pagina_complexa", "Página complexa demais para os recursos disponíveis"),
        }

        for codigo, esperado in casos.items():
            with self.subTest(codigo=codigo):
                self.assertEqual(
                    esperado,
                    PrinterMonitorService._classificar_alerta_impressora(codigo, ""),
                )

    def test_traduz_descricao_do_fabricante_com_codigo_generico(self):
        self.assertEqual(
            ("manutencao", "Manutenção técnica necessária"),
            PrinterMonitorService._classificar_alerta_impressora(1, "Service Call 980"),
        )

    def test_traduz_atolamento_de_documento_reportado_pelo_adf(self):
        self.assertEqual(
            ("atolamento_documento", "Atolamento de documento no alimentador"),
            PrinterMonitorService._classificar_alerta_impressora(1, "Document Jam"),
        )

    def test_descarta_evento_de_tampa_fechada(self):
        indice = (1, 41)
        linhas = [
            (self.RAIZ + (1,) + indice, 41),
            (self.RAIZ + (2,) + indice, 4),
            (self.RAIZ + (7,) + indice, 4),
            (self.RAIZ + (8,) + indice, "Cover Closed"),
        ]

        self.assertEqual([], PrinterMonitorService._normalizar_alertas_printer_mib(linhas))

    def test_descarta_outros_eventos_que_nao_representam_problema(self):
        for codigo in (507, 802, 1503, 1801):
            with self.subTest(codigo=codigo):
                indice = (1, codigo)
                linhas = [
                    (self.RAIZ + (1,) + indice, codigo),
                    (self.RAIZ + (2,) + indice, 4),
                    (self.RAIZ + (7,) + indice, codigo),
                    (self.RAIZ + (8,) + indice, "Evento normal"),
                ]

                self.assertEqual(
                    [],
                    PrinterMonitorService._normalizar_alertas_printer_mib(linhas),
                )


class InicializarEstadoTest(unittest.TestCase):
    def test_restaura_rastreamento_persistido_do_contador_de_copias(self):
        service = PrinterMonitorService.__new__(PrinterMonitorService)
        service.printer_configs = [{"id": "impressora11"}]
        service.resultado_global = {"impressoras": {}}
        service.cache_rastreamento_dia = {}
        service.rastreamento_mes = {}
        service.cache_rastreamento_dia_persistido = {
            "impressora11__copias": {
                "data_lista": "2026-08-10",
                "hora_primeiro_registro": "08:30:00",
                "impressoes_inicio": 100,
                "impressoes_acumuladas": 5,
                "impressoes_dia": 20,
                "registrado_hoje": True,
            }
        }
        service.rastreamento_mes_persistido = {
            "impressora11__copias": {
                "mes_referencia": "2026-08",
                "impressoes_inicio": 80,
                "impressoes_acumuladas": 10,
                "impressoes_mes": 40,
                "registrado_mes": True,
            }
        }

        service._inicializar_estado()

        rastreamento_diario = service.cache_rastreamento_dia["impressora11__copias"]
        rastreamento_mensal = service.rastreamento_mes["impressora11__copias"]
        self.assertEqual(date(2026, 8, 10), rastreamento_diario["data_lista"])
        self.assertEqual(time(8, 30), rastreamento_diario["hora_primeiro_registro"])
        self.assertEqual(100, rastreamento_diario["impressoes_inicio"])
        self.assertEqual(20, rastreamento_diario["impressoes_dia"])
        self.assertEqual("2026-08", rastreamento_mensal["mes_referencia"])
        self.assertEqual(40, rastreamento_mensal["impressoes_mes"])


if __name__ == "__main__":
    unittest.main()


class StatusOfflineTest(unittest.TestCase):
    def test_preserva_contadores_ao_desligar_e_recupera_rastreamento(self):
        service = PrinterMonitorService.__new__(PrinterMonitorService)
        service.cache_impressoras = {}
        service.resultado_global = {"impressoras": {}}
        service.cache_rastreamento_dia = {
            "p1": {"impressoes_dia": 20, "impressoes_acumuladas": 5},
            "p1__copias": {"impressoes_dia": 3, "impressoes_acumuladas": 2},
        }
        service.rastreamento_mes = {
            "p1": {"impressoes_mes": 140, "impressoes_acumuladas": 10},
            "p1__copias": {"impressoes_mes": 25, "impressoes_acumuladas": 5},
        }
        status = service._montar_status_offline("p1", "192.0.2.1")
        for campo, valor in {"impressoes_dia": 25, "impressoes_mes": 150,
                             "copias_dia": 5, "copias_mes": 30}.items():
            self.assertEqual(valor, status[campo])

        contadores = {"impressoes_dia": 0, "impressoes_mes": 160,
                      "copias_dia": 7, "copias_mes": 35}
        service.resultado_global["impressoras"]["p1"] = {"online": True, **contadores}
        for _ in range(2):
            status = service._montar_status_offline("p1", "192.0.2.1")
            self.assertFalse(status["online"])
            for campo, valor in contadores.items():
                self.assertEqual(valor, status[campo])
            service.resultado_global["impressoras"]["p1"] = status

        status = service._montar_status_offline("nova", "192.0.2.2")
        self.assertEqual(0, status["impressoes_dia"])
        self.assertEqual(0, status["impressoes_mes"])

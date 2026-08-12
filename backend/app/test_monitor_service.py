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

import unittest

from services.contador_service import calcular_delta_contador


class CalcularDeltaContadorTest(unittest.TestCase):
    def test_crescimento_normal(self):
        self.assertEqual(calcular_delta_contador(1000, 1025), (25, "normal"))

    def test_contador_sem_alteracao(self):
        self.assertEqual(calcular_delta_contador(1000, 1000), (0, "normal"))

    def test_reset_preserva_paginas_do_novo_contador(self):
        self.assertEqual(calcular_delta_contador(1100, 5), (5, "reset"))

    def test_intervalo_que_cruza_mes(self):
        self.assertEqual(calcular_delta_contador(1000, 1020, True), (20, "virada_mes"))

    def test_troca_equipamento_nao_contabiliza_contador_da_nova_impressora(self):
        self.assertEqual(
            calcular_delta_contador(221472, 34695, mudou_equipamento=True),
            (0, "troca_equipamento"),
        )

    def test_mesmo_equipamento_com_contador_menor_continua_sendo_reset(self):
        self.assertEqual(
            calcular_delta_contador(221472, 34695, mudou_equipamento=False),
            (34695, "reset"),
        )

    def test_valor_negativo_e_rejeitado(self):
        with self.assertRaises(ValueError):
            calcular_delta_contador(-1, 10)


if __name__ == "__main__":
    unittest.main()

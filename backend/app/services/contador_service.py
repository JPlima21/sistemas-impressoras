# Calcula um delta auditavel entre duas leituras cumulativas do equipamento.
def calcular_delta_contador(
    contador_anterior,
    contador_atual,
    mudou_competencia=False,
    mudou_equipamento=False,
):
    anterior = int(contador_anterior)
    atual = int(contador_atual)

    if anterior < 0 or atual < 0:
        raise ValueError("O contador da impressora nao pode ser negativo.")

    if mudou_equipamento:
        return 0, "troca_equipamento"

    if atual < anterior:
        return atual, "reset"

    classificacao = "virada_mes" if mudou_competencia else "normal"
    return atual - anterior, classificacao

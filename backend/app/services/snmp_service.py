from pysnmp.hlapi import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    getCmd,
    nextCmd,
)


# Cria um SnmpEngine dedicado a uma thread de monitoramento. Reaproveitar a
# mesma instância entre chamadas evita que o pysnmp recarregue/recompile as
# MIBs (via pysmi/ply) a cada leitura, o que é custoso e prende a GIL.
def criar_snmp_engine():
    return SnmpEngine()


# Faz uma leitura SNMP simples para um OID específico de uma impressora
def snmp_get(engine, ip, community, oid, version=0, timeout=2):
    try:
        iterator = getCmd(
            engine,
            CommunityData(community, mpModel=version),
            UdpTransportTarget((ip, 161), timeout=timeout, retries=3),
            ContextData(),
            ObjectType(ObjectIdentity(oid)),
        )

        error_indication, error_status, _, var_binds = next(iterator)

        if error_indication or error_status:
            return None

        for var_bind in var_binds:
            return var_bind[1]
    except Exception:
        return None


# Percorre duas colunas de uma mesma tabela SNMP e devolve seus valores pareados.
def snmp_walk_pares(engine, ip, community, oid_chave, oid_valor, version=0, timeout=2):
    linhas = []
    try:
        iterator = nextCmd(
            engine,
            CommunityData(community, mpModel=version),
            UdpTransportTarget((ip, 161), timeout=timeout, retries=2),
            ContextData(),
            ObjectType(ObjectIdentity(oid_chave)),
            ObjectType(ObjectIdentity(oid_valor)),
            lexicographicMode=False,
        )

        for error_indication, error_status, _, var_binds in iterator:
            if error_indication or error_status or len(var_binds) < 2:
                break
            linhas.append((int(var_binds[0][1]), int(var_binds[1][1])))
    except Exception:
        return []

    return linhas


# Percorre uma tabela SNMP completa e preserva o OID e o tipo bruto de cada valor.
# Isso permite reconstruir tabelas com varias colunas, como a prtAlertTable.
def snmp_walk_tabela(engine, ip, community, oid_raiz, version=0, timeout=2):
    linhas = []
    raiz = tuple(int(parte) for parte in str(oid_raiz).strip(".").split("."))

    try:
        iterator = nextCmd(
            engine,
            CommunityData(community, mpModel=version),
            UdpTransportTarget((ip, 161), timeout=timeout, retries=1),
            ContextData(),
            ObjectType(ObjectIdentity(oid_raiz)),
            lexicographicMode=False,
        )

        for error_indication, error_status, _, var_binds in iterator:
            if error_indication or error_status:
                break

            for var_bind in var_binds:
                oid = tuple(int(parte) for parte in var_bind[0])
                if oid[: len(raiz)] != raiz:
                    return linhas
                linhas.append((oid, var_bind[1]))
    except Exception:
        return []

    return linhas


# Converte o retorno bruto do MAC address SNMP para o formato XX:XX:XX:XX:XX:XX
def formatar_mac(mac_raw):
    if mac_raw is None:
        return None

    try:
        mac_bytes = bytes(mac_raw)
        return ":".join(f"{byte:02X}" for byte in mac_bytes)
    except Exception:
        return str(mac_raw)

from pysnmp.hlapi import (
    CommunityData,
    ContextData,
    ObjectIdentity,
    ObjectType,
    SnmpEngine,
    UdpTransportTarget,
    getCmd,
)


# Faz uma leitura SNMP simples para um OID específico de uma impressora
def snmp_get(ip, community, oid, version=0, timeout=2):
    try:
        iterator = getCmd(
            SnmpEngine(),
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


# Converte o retorno bruto do MAC address SNMP para o formato XX:XX:XX:XX:XX:XX
def formatar_mac(mac_raw):
    if mac_raw is None:
        return None

    try:
        mac_bytes = bytes(mac_raw)
        return ":".join(f"{byte:02X}" for byte in mac_bytes)
    except Exception:
        return str(mac_raw)

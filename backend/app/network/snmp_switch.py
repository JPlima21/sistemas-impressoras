"""Read vendor-neutral switch information through SNMPv2c."""

from __future__ import annotations

from datetime import datetime, timezone

from pysnmp.hlapi import (
    CommunityData, ContextData, ObjectIdentity, ObjectType, SnmpEngine,
    UdpTransportTarget, bulkCmd, getCmd,
)


SYSTEM_OIDS = {
    "description": "1.3.6.1.2.1.1.1.0",
    "uptimeTicks": "1.3.6.1.2.1.1.3.0",
    "name": "1.3.6.1.2.1.1.5.0",
    "location": "1.3.6.1.2.1.1.6.0",
}
INTERFACE_OIDS = {
    "description": "1.3.6.1.2.1.2.2.1.2",
    "adminStatus": "1.3.6.1.2.1.2.2.1.7",
    "operStatus": "1.3.6.1.2.1.2.2.1.8",
    "inErrors": "1.3.6.1.2.1.2.2.1.14",
    "outErrors": "1.3.6.1.2.1.2.2.1.20",
    "name": "1.3.6.1.2.1.31.1.1.1.1",
    "inOctets": "1.3.6.1.2.1.31.1.1.1.6",
    "outOctets": "1.3.6.1.2.1.31.1.1.1.10",
    "inOctets32": "1.3.6.1.2.1.2.2.1.10",
    "outOctets32": "1.3.6.1.2.1.2.2.1.16",
}
MAX_INTERFACES = 128


def _number(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _walk_column(engine, target, community, oid):
    prefix = tuple(int(part) for part in oid.split("."))
    values = {}
    iterator = bulkCmd(
        engine, CommunityData(community, mpModel=1), target, ContextData(),
        0, 20, ObjectType(ObjectIdentity(oid)), lexicographicMode=False,
    )
    rows_seen = 0
    for error, status, _, bindings in iterator:
        rows_seen += 1
        if rows_seen > MAX_INTERFACES * 2:
            break
        if error or status:
            break
        for name, value in bindings:
            path = tuple(int(part) for part in name)
            if path[:len(prefix)] != prefix:
                return values
            if len(path) == len(prefix) + 1:
                values[path[-1]] = value
            if len(values) >= MAX_INTERFACES:
                return values
    return values


def collect_switch(host: str, community: str, port: int = 161) -> dict:
    """Return a bounded snapshot; raise when the switch does not answer SNMP."""
    target = UdpTransportTarget((host, port), timeout=1.5, retries=1)
    engine = SnmpEngine()
    iterator = getCmd(
        engine, CommunityData(community, mpModel=1), target, ContextData(),
        *(ObjectType(ObjectIdentity(oid)) for oid in SYSTEM_OIDS.values()),
    )
    error, status, _, bindings = next(iterator)
    if error or status:
        raise RuntimeError(str(error or status))

    system = {}
    for key, (_, value) in zip(SYSTEM_OIDS, bindings):
        system[key] = _number(value) if key == "uptimeTicks" else str(value)

    columns = {
        key: _walk_column(engine, target, community, oid)
        for key, oid in INTERFACE_OIDS.items()
    }
    indexes = set().union(*(values.keys() for values in columns.values()))
    interfaces = []
    for index in sorted(indexes)[:MAX_INTERFACES]:
        row = {"index": index}
        for key, values in columns.items():
            value = values.get(index)
            row[key] = (str(value) if value is not None else "") if key in {"name", "description"} else _number(value)
        row["inOctets"] = row["inOctets"] if row["inOctets"] is not None else row.pop("inOctets32")
        row["outOctets"] = row["outOctets"] if row["outOctets"] is not None else row.pop("outOctets32")
        row.pop("inOctets32", None)
        row.pop("outOctets32", None)
        row["name"] = row["name"] or row["description"] or f"Interface {index}"
        interfaces.append(row)

    return {
        "collectedAt": datetime.now(timezone.utc).isoformat(),
        "system": system,
        "interfaces": interfaces,
        "error": None,
    }

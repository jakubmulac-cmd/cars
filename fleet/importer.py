import argparse
import hashlib
import json
import uuid
from decimal import Decimal
from pathlib import Path

from jsonschema import Draft202012Validator

from fleet.db import ROOT, audit, collection, connect, encode, migrate, now

KEYS = {
    "insurance": "asset_id", "premium_lines": "premium_id", "acquisitions": "asset_id",
    "operations": "asset_id", "odometer_readings": "reading_id", "rides": "ride_id",
    "issues": "issue_id", "source_observations": "observation_id",
}
EXPECTED_COUNTS = {
    "vehicles": 31, "insurance": 31, "premium_lines": 14, "acquisitions": 31,
    "operations": 31, "odometer_readings": 105, "rides": 63, "issues": 38,
    "source_observations": 2885, "sources": 21,
}


def decimal(value):
    return Decimal(str(value))


def validate(payload):
    schema = json.loads((ROOT / "schemas/fleet_context.schema.json").read_text())
    Draft202012Validator.check_schema(schema)
    errors = sorted(Draft202012Validator(schema).iter_errors(payload), key=lambda e: str(e.path))
    if errors:
        raise ValueError("JSON neodpovídá schématu: " + "/".join(map(str, errors[0].path)))
    assets = {x["asset_id"] for x in payload["vehicles"]}
    sources = {x["source_id"] for x in payload["sources"]}
    uuids = [x["uuid"] for x in payload["vehicles"]]
    if len(set(uuids)) != len(uuids):
        raise ValueError("Duplicitní UUID vozidla")
    for name, key in {"vehicles": "asset_id", "sources": "source_id", **KEYS}.items():
        ids = [x[key] for x in payload[name]]
        if len(set(ids)) != len(ids):
            raise ValueError(f"Duplicitní ID v kolekci {name}")
        for item in payload[name]:
            asset = item.get("asset_id")
            if asset is not None and asset not in assets:
                raise ValueError(f"Neznámé vozidlo v {name}")
            refs = item.get("source_ids", []) + ([item["source_id"]] if item.get("source_id") else [])
            if any(ref not in sources for ref in refs):
                raise ValueError(f"Neznámý zdroj v {name}")
    q4 = sum((decimal(x["amount"]) for x in payload["premium_lines"] if x["kind"] == "Pojistné Q4"), Decimal(0))
    retro = sum((decimal(x["amount"]) for x in payload["premium_lines"] if x["kind"] == "Zpětný předpis"), Decimal(0))
    triumph = sum((decimal(x["amount"]) for x in payload["premium_lines"] if x["kind"] in {"POV roční", "HAV a ostatní roční"}), Decimal(0))
    if any(x["currency"] != "CZK" for x in payload["premium_lines"]):
        raise ValueError("Pojistný snímek vyžaduje doloženou měnu CZK")
    b = payload["billing_reconciliation"]
    checks = [(q4, b["cpp_q4"]), (retro, b["cpp_retro"]), (q4 + retro, b["cpp_new_premium"]),
              (decimal(b["cpp_new_premium"]) + decimal(b["cpp_old_prescriptions"]) - decimal(b["cpp_credit"]), b["cpp_payment_requested"]),
              (triumph, b["triumph_total"])]
    if any(actual != decimal(expected) for actual, expected in checks):
        raise ValueError("Nesouhlasí kontrolní součty pojištění")
    if payload["as_of"] == "2026-10-11":
        if any(len(payload[k]) != count for k, count in EXPECTED_COUNTS.items()):
            raise ValueError("Nesouhlasí počty záznamů vstupního snímku")
        if [q4, retro, q4 + retro, decimal(b["cpp_payment_requested"]), triumph] != list(map(Decimal, [53847, 9475, 63322, 106230, 19818])):
            raise ValueError("Nesouhlasí částky výchozího snímku")
    return {"as_of": payload["as_of"], "counts": {k: len(payload[k]) for k in EXPECTED_COUNTS},
            "totals": {"q4": str(q4), "retro": str(retro), "new": str(q4 + retro), "historical": str(b["cpp_payment_requested"]), "triumph": str(triumph)}}


def stage(payload):
    report = validate(payload)
    serialized = encode(payload)
    digest = hashlib.sha256(serialized.encode()).hexdigest()
    import_id = str(uuid.uuid4())
    with connect() as con, con:
        old = {x["asset_id"]: x for x in collection(con, "vehicles")}
        report["new_vehicles"] = sum(x["asset_id"] not in old for x in payload["vehicles"])
        report["changed_vehicles"] = sum(x["asset_id"] in old and x != old[x["asset_id"]] for x in payload["vehicles"])
        report["already_imported"] = bool(con.execute("SELECT 1 FROM snapshots WHERE sha256=?", (digest,)).fetchone())
        report["conflicts"] = [{"asset_id": x["asset_id"], "name": x["name"], "verification": x["verification"]}
                              for x in payload["vehicles"] if x["verification"] == "Rozpor"]
        con.execute("INSERT INTO imports(id,sha256,payload,report,created_at) VALUES(?,?,?,?,?)", (import_id, digest, serialized, encode(report), now()))
    return {"id": import_id, **report}


def commit(import_id):
    with connect() as con:
        con.execute("BEGIN IMMEDIATE")
        row = con.execute("SELECT * FROM imports WHERE id=?", (import_id,)).fetchone()
        if row is None:
            raise ValueError("Import nenalezen")
        payload = json.loads(row["payload"])
        report = validate(payload)
        if con.execute("SELECT 1 FROM snapshots WHERE sha256=?", (row["sha256"],)).fetchone():
            con.execute("UPDATE imports SET state='imported' WHERE id=?", (import_id,))
            con.commit()
            return {"duplicate": True, **report}
        # No destructive reset: retain imported revisions and manual updates.
        for item in payload["vehicles"]:
            existing = con.execute("SELECT uuid FROM vehicles WHERE asset_id=?", (item["asset_id"],)).fetchone()
            if existing and existing[0] != item["uuid"]:
                raise ValueError("UUID existujícího vozidla nelze změnit importem")
            con.execute("INSERT INTO vehicles VALUES(?,?,?,?,?) ON CONFLICT(asset_id) DO UPDATE SET name=excluded.name,state=excluded.state,payload=excluded.payload",
                        (item["asset_id"], item["uuid"], item["name"], item["asset_state"], encode(item)))
        for item in payload["sources"]:
            con.execute("INSERT INTO sources VALUES(?,?) ON CONFLICT(source_id) DO UPDATE SET payload=excluded.payload", (item["source_id"], encode(item)))
        for name, key in KEYS.items():
            for item in payload[name]:
                con.execute("INSERT INTO records VALUES(?,?,?,?,?) ON CONFLICT(collection,record_id) DO UPDATE SET asset_id=excluded.asset_id,source_id=excluded.source_id,payload=excluded.payload",
                            (name, item[key], item.get("asset_id"), item.get("source_id"), encode(item)))
        for key, value in payload.items():
            if key not in EXPECTED_COUNTS:
                con.execute("INSERT INTO metadata VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, encode(value)))
        con.execute("INSERT INTO snapshots VALUES(?,?,?,?)", (row["sha256"], payload["as_of"], row["payload"], now()))
        con.execute("UPDATE imports SET state='imported' WHERE id=?", (import_id,))
        audit(con, "import", import_id, report)
        con.commit()
    return {"duplicate": False, **report}


def main():
    parser = argparse.ArgumentParser(description="Ověřený, transakční import soukromého snímku")
    parser.add_argument("path", type=Path)
    parser.add_argument("--commit", action="store_true", help="Po validaci potvrdit import; bez této volby jen náhled")
    args = parser.parse_args()
    migrate()
    result = stage(json.loads(args.path.read_text()))
    if args.commit:
        result = commit(result["id"])
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

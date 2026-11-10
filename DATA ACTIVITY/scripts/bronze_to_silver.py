"""Bronze -> Silver: limpia y normaliza clientes, ventas y logs.

Uso:
    python bronze_to_silver.py <dir_bronze> <dir_silver>

Genera en <dir_silver>:
    clean_customers.csv, clean_sales.csv, clean_logs.csv, rejected_records.csv

Criterios: ver ../PROPUESTA_SILVER.md. Solo usa la biblioteca estándar.
"""

import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median

TEST_NAMES = {"testuser", "debug"}
COUNTRY_FIX = {"UK": "GB"}
INVALID_COUNTRY = {"??", ""}
VALID_PRODUCTS = {"teclado", "raton", "monitor"}
VALID_ACTIONS = {"login", "logout", "compra", "timeout"}
VALID_LEVELS = {"INFO", "WARN", "ERROR"}
OUTLIER_FACTOR = 5  # importe > 5x la mediana de su producto => atípico
LOG_PATTERN = re.compile(r"^\[(?P<level>\w+)\](?: user=(?P<user>\S*))? action=(?P<action>\S*)$")

LOAD_TS = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def to_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


class Rejects:
    def __init__(self):
        self.rows = []

    def add(self, source, line, reason, raw):
        self.rows.append(
            {"_source_file": source, "_source_line": line, "reason": reason, "raw_record": raw}
        )


def lineage(source, line):
    return {"_source_file": source, "_source_line": line, "_load_ts": LOAD_TS}


def clean_customers(path, rejects):
    source = path.name
    out, test_ids = [], set()
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = line.strip().rstrip(",")
        if not text.startswith("{"):
            continue  # '[', ']' y líneas en blanco
        record = json.loads(text)
        customer_id = to_int(record.get("id_cliente"))
        name = (record.get("nombre") or "").strip()
        country = (record.get("pais") or "").strip().upper()

        if customer_id is None:
            rejects.add(source, line_no, "id_cliente inválido", text)
            continue
        if name.lower() in TEST_NAMES:
            test_ids.add(customer_id)
            rejects.add(source, line_no, "cliente de test/debug", text)
            continue

        country = COUNTRY_FIX.get(country, country)
        out.append(
            {
                "customer_id": customer_id,
                "customer_name": name or None,
                "country_code": None if country in INVALID_COUNTRY else country,
                **lineage(source, line_no),
            }
        )

    ids = [c["customer_id"] for c in out]
    if len(ids) != len(set(ids)):
        raise ValueError("customer_id duplicado en clientes")
    return out, test_ids


def clean_sales(path, customer_ids, test_ids, rejects):
    source = path.name
    with path.open(encoding="utf-8", newline="") as fh:
        rows = [(n, r) for n, r in enumerate(csv.reader(fh), 1)]
    header, body = rows[0][1], [(n, r) for n, r in rows[1:] if any(c.strip() for c in r)]
    if header != ["id_pedido", "id_cliente", "producto", "importe"]:
        raise ValueError(f"cabecera inesperada en ventas: {header}")

    parsed = []
    for line_no, r in body:
        raw = ",".join(r)
        order_id, customer_id = to_int(r[0]), to_int(r[1])
        product = r[2].strip().lower()
        try:
            amount = Decimal(r[3].strip())
        except InvalidOperation:
            amount = None

        reason = None
        if order_id is None:
            reason = "id_pedido inválido"
        elif customer_id is None:
            reason = "id_cliente vacío o inválido"
        elif customer_id in test_ids:
            reason = "cliente de test/debug"
        elif customer_id not in customer_ids:
            reason = "cliente inexistente"
        elif product not in VALID_PRODUCTS:
            reason = f"producto no válido ({product})"
        elif amount is None:
            reason = "importe no numérico"
        elif amount <= 0:
            reason = "importe negativo o cero"
        if reason:
            rejects.add(source, line_no, reason, raw)
        else:
            parsed.append((line_no, raw, order_id, customer_id, product, amount))

    medians = defaultdict(list)
    for *_, product, amount in parsed:
        medians[product].append(amount)
    medians = {p: median(v) for p, v in medians.items()}

    out, seen_ids, prev = [], set(), None
    for line_no, raw, order_id, customer_id, product, amount in sorted(parsed, key=lambda x: x[2]):
        key = (customer_id, product, amount)
        reason = None
        if order_id in seen_ids:
            reason = "id_pedido duplicado"
        elif amount > medians[product] * OUTLIER_FACTOR:
            reason = f"importe atípico (> {OUTLIER_FACTOR}x mediana de {product})"
        elif prev and prev[1] == key and order_id == prev[0] + 1:
            reason = f"posible duplicado del pedido {prev[0]}"
        prev = (order_id, key)
        if reason:
            rejects.add(source, line_no, reason, raw)
            continue
        seen_ids.add(order_id)
        out.append(
            {
                "order_id": order_id,
                "customer_id": customer_id,
                "product": product,
                "amount": f"{amount:.2f}",
                **lineage(source, line_no),
            }
        )
    return out


def clean_logs(path, customer_ids, test_ids, rejects):
    source = path.name
    out = []
    for line_no, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        text = line.strip()
        match = LOG_PATTERN.match(text)
        reason = None
        if not text:
            reason = "línea vacía"
        elif not match:
            reason = "formato no reconocido"
        else:
            level, user, action = match["level"], match["user"], match["action"]
            customer_id = to_int(user)
            if user is None:
                reason = "sin user"
            elif not action:
                reason = "action vacía"
            elif level == "DEBUG" or action == "test":
                reason = "evento de test/debug"
            elif customer_id is None:
                reason = "user no numérico"
            elif customer_id in test_ids:
                reason = "cliente de test/debug"
            elif customer_id not in customer_ids:
                reason = "cliente inexistente"
            elif level not in VALID_LEVELS or action not in VALID_ACTIONS:
                reason = "nivel o acción no permitidos"
        if reason:
            rejects.add(source, line_no, reason, text)
            continue
        out.append(
            {
                "log_level": level,
                "customer_id": customer_id,
                "action": action,
                **lineage(source, line_no),
            }
        )
    return out


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for row in rows:
            writer.writerow({k: ("" if row[k] is None else row[k]) for k in fields})


def main(bronze, silver):
    bronze, silver = Path(bronze), Path(silver)
    silver.mkdir(parents=True, exist_ok=True)
    rejects = Rejects()

    customers, test_ids = clean_customers(bronze / "clientes.json", rejects)
    customer_ids = {c["customer_id"] for c in customers}

    sales = clean_sales(bronze / "ventas.csv", customer_ids, test_ids, rejects)
    logs = clean_logs(bronze / "logs.txt", customer_ids, test_ids, rejects)

    lin = ["_source_file", "_source_line", "_load_ts"]
    write_csv(silver / "clean_customers.csv", customers, ["customer_id", "customer_name", "country_code", *lin])
    write_csv(silver / "clean_sales.csv", sales, ["order_id", "customer_id", "product", "amount", *lin])
    write_csv(silver / "clean_logs.csv", logs, ["log_level", "customer_id", "action", *lin])
    write_csv(silver / "rejected_records.csv", rejects.rows, ["_source_file", "_source_line", "reason", "raw_record"])

    print(f"customers={len(customers)} sales={len(sales)} logs={len(logs)} rejected={len(rejects.rows)}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])

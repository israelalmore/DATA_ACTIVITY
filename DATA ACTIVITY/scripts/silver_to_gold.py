"""Silver -> Gold: construye las tablas de negocio y las publica en Markdown.

Uso:
    python silver_to_gold.py <dir_silver> <dir_gold>

Genera un único fichero, <dir_gold>/GOLD.md, con estas tablas:
    KPIs, ventas por cliente, por producto y por país, y respuestas de negocio.

Lee solo Silver (clean_customers.csv, clean_sales.csv). Los cálculos se hacen en una
base SQLite en memoria que no se guarda. Criterios: ver ../PROPUESTA_GOLD.md.
Idempotente: cada ejecución reescribe GOLD.md entero. Solo usa la biblioteca estándar.
"""

import csv
import os
import sqlite3
import sys
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

NO_COUNTRY = "N/D"
LOAD_TS = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

# Los importes se cargan en céntimos (INTEGER) para que las sumas sean exactas;
# solo se pasan a unidades con 2 decimales en las tablas Gold.
STAGING = """
CREATE TABLE silver_customers (
    customer_id   INTEGER PRIMARY KEY,
    customer_name TEXT,
    country_code  TEXT
);
CREATE TABLE silver_sales (
    order_id     INTEGER PRIMARY KEY,
    customer_id  INTEGER NOT NULL REFERENCES silver_customers(customer_id),
    product      TEXT    NOT NULL,
    amount_cents INTEGER NOT NULL CHECK (amount_cents > 0)
);
"""

GOLD = """
CREATE TABLE gold_sales_by_customer AS
WITH t AS (SELECT SUM(amount_cents) AS total FROM silver_sales),
agg AS (
    SELECT c.customer_id, c.customer_name,
           COALESCE(c.country_code, :no_country) AS country_code,
           COUNT(s.order_id) AS orders,
           COALESCE(SUM(s.amount_cents), 0) AS cents
    FROM silver_customers c
    LEFT JOIN silver_sales s ON s.customer_id = c.customer_id
    GROUP BY c.customer_id
)
SELECT customer_id, customer_name, country_code, orders,
       ROUND(cents / 100.0, 2) AS total_sales,
       ROUND(cents * 1.0 / t.total, 4) AS revenue_share,
       RANK() OVER (ORDER BY cents DESC) AS sales_rank
FROM agg, t;

CREATE TABLE gold_sales_by_product AS
WITH t AS (SELECT SUM(amount_cents) AS total FROM silver_sales)
SELECT product, COUNT(*) AS orders,
       ROUND(SUM(amount_cents) / 100.0, 2) AS revenue,
       ROUND(SUM(amount_cents) / 100.0 / COUNT(*), 2) AS avg_price,
       ROUND(SUM(amount_cents) * 1.0 / t.total, 4) AS revenue_share,
       RANK() OVER (ORDER BY SUM(amount_cents) DESC) AS revenue_rank
FROM silver_sales, t
GROUP BY product;

CREATE TABLE gold_sales_by_country AS
WITH t AS (SELECT SUM(amount_cents) AS total FROM silver_sales),
agg AS (
    SELECT COALESCE(c.country_code, :no_country) AS country_code,
           COUNT(DISTINCT c.customer_id) AS customers,
           COUNT(DISTINCT s.customer_id) AS buying_customers,
           COUNT(s.order_id) AS orders,
           COALESCE(SUM(s.amount_cents), 0) AS cents
    FROM silver_customers c
    LEFT JOIN silver_sales s ON s.customer_id = c.customer_id
    GROUP BY 1
)
SELECT country_code, customers, buying_customers, orders,
       ROUND(cents / 100.0, 2) AS revenue,
       CASE WHEN orders > 0 THEN ROUND(cents / 100.0 / orders, 2) END AS avg_order_value,
       ROUND(cents * 1.0 / t.total, 4) AS revenue_share,
       RANK() OVER (ORDER BY cents DESC) AS revenue_rank
FROM agg, t;

CREATE TABLE gold_kpis AS
SELECT ROUND((SELECT SUM(amount_cents) FROM silver_sales) / 100.0, 2) AS total_revenue,
       (SELECT COUNT(*) FROM silver_sales) AS total_orders,
       ROUND((SELECT SUM(amount_cents) FROM silver_sales) / 100.0
             / (SELECT COUNT(*) FROM silver_sales), 2) AS avg_order_value,
       (SELECT COUNT(*) FROM silver_customers) AS total_customers,
       (SELECT COUNT(DISTINCT customer_id) FROM silver_sales) AS buying_customers,
       ROUND((SELECT COUNT(DISTINCT customer_id) FROM silver_sales) * 1.0
             / (SELECT COUNT(*) FROM silver_customers), 4) AS buyer_rate;

-- Una fila por ganador: si hay empate en el primer puesto, aparecen todos.
CREATE TABLE gold_business_answers AS
SELECT 'Q1' AS question_id, 'Who is the largest buyer?' AS question,
       CAST(customer_id AS TEXT) || ' - ' || COALESCE(customer_name, '(sin nombre)') AS answer,
       total_sales AS value,
       orders || ' pedido(s), ' || country_code AS detail,
       revenue_share AS share
FROM gold_sales_by_customer WHERE sales_rank = 1
UNION ALL
SELECT 'Q2', 'Which product generates the most revenue?', product, revenue,
       orders || ' pedidos', revenue_share
FROM gold_sales_by_product WHERE revenue_rank = 1
UNION ALL
SELECT 'Q3', 'Which country generates the most revenue?', country_code, revenue,
       orders || ' pedidos', revenue_share
FROM gold_sales_by_country WHERE revenue_rank = 1;
"""

# Cada consulta debe devolver 0 filas; si no, Gold no cuadra con Silver.
CHECKS = {
    "Σ total_sales por cliente ≠ total_revenue": """
        SELECT 1 FROM gold_kpis
        WHERE ABS((SELECT SUM(total_sales) FROM gold_sales_by_customer) - total_revenue) > 0.005""",
    "Σ revenue por producto ≠ total_revenue": """
        SELECT 1 FROM gold_kpis
        WHERE ABS((SELECT SUM(revenue) FROM gold_sales_by_product) - total_revenue) > 0.005""",
    "Σ revenue por país ≠ total_revenue": """
        SELECT 1 FROM gold_kpis
        WHERE ABS((SELECT SUM(revenue) FROM gold_sales_by_country) - total_revenue) > 0.005""",
    "Σ pedidos por cliente ≠ total_orders": """
        SELECT 1 FROM gold_kpis
        WHERE (SELECT SUM(orders) FROM gold_sales_by_customer) <> total_orders""",
    "Σ clientes por país ≠ total_customers": """
        SELECT 1 FROM gold_kpis
        WHERE (SELECT SUM(customers) FROM gold_sales_by_country) <> total_customers""",
    "falta una respuesta Q1–Q3": """
        SELECT q FROM (SELECT 'Q1' AS q UNION SELECT 'Q2' UNION SELECT 'Q3')
        WHERE q NOT IN (SELECT question_id FROM gold_business_answers)""",
}


# --- Carga y cálculo -------------------------------------------------------

def read_csv(path):
    with path.open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def to_cents(value):
    return int(Decimal(value) * 100)


def build(silver):
    """Carga Silver en una base en memoria, calcula Gold y valida. Devuelve la conexión."""
    con = sqlite3.connect(":memory:")
    con.execute("PRAGMA foreign_keys = ON")
    con.executescript(STAGING)
    con.executemany(
        "INSERT INTO silver_customers VALUES (?, ?, ?)",
        [
            (int(r["customer_id"]), r["customer_name"] or None, r["country_code"] or None)
            for r in read_csv(silver / "clean_customers.csv")
        ],
    )
    con.executemany(
        "INSERT INTO silver_sales VALUES (?, ?, ?, ?)",
        [
            (int(r["order_id"]), int(r["customer_id"]), r["product"], to_cents(r["amount"]))
            for r in read_csv(silver / "clean_sales.csv")
        ],
    )
    for statement in GOLD.split(";\n"):
        if statement.strip():
            params = {"no_country": NO_COUNTRY} if ":no_country" in statement else {}
            con.execute(statement, params)

    failed = [name for name, sql in CHECKS.items() if con.execute(sql).fetchall()]
    if failed:
        con.close()
        raise ValueError("Gold no cuadra con Silver: " + "; ".join(failed))
    return con


# --- Publicación en Markdown -----------------------------------------------

def money(v):
    """16385.0 -> '16.385,00' (formato español, sin símbolo: moneda sin confirmar)."""
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(v):
    return f"{v * 100:.1f} %".replace(".", ",")


def table(headers, rows, numeric=()):
    """Tabla Markdown; las columnas cuyo índice está en `numeric` se alinean a la derecha."""
    align = ["---:" if i in numeric else "---" for i in range(len(headers))]
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(align) + "|"]
    lines += ["| " + " | ".join(str(c) for c in row) + " |" for row in rows]
    return "\n".join(lines)


def render(con):
    q = con.execute
    k = q("SELECT * FROM gold_kpis").fetchone()

    answers = table(
        ["#", "Pregunta", "Respuesta", "Importe", "% del total", "Detalle"],
        [
            (qid, question, f"**{answer}**", money(value), pct(share), detail)
            for qid, question, answer, value, detail, share in q(
                "SELECT * FROM gold_business_answers ORDER BY question_id, answer"
            )
        ],
        numeric=(3, 4),
    )
    kpis = table(
        ["Indicador", "Valor"],
        [
            ("Total revenue", money(k[0])),
            ("Pedidos", k[1]),
            ("Ticket medio", money(k[2])),
            ("Clientes", k[3]),
            ("Clientes con compra", k[4]),
            ("% clientes con compra", pct(k[5])),
        ],
        numeric=(1,),
    )
    by_customer = table(
        ["Puesto", "Cliente", "País", "Pedidos", "Total Sales", "% del total"],
        [
            (rank, f"{cid} - {name or '(sin nombre)'}", country, orders, money(sales), pct(share))
            for cid, name, country, orders, sales, share, rank in q(
                "SELECT * FROM gold_sales_by_customer ORDER BY sales_rank, customer_id"
            )
        ],
        numeric=(0, 3, 4, 5),
    )
    by_product = table(
        ["Puesto", "Producto", "Pedidos", "Revenue", "Precio medio", "% del total"],
        [
            (rank, product, orders, money(rev), money(avg), pct(share))
            for product, orders, rev, avg, share, rank in q(
                "SELECT * FROM gold_sales_by_product ORDER BY revenue_rank, product"
            )
        ],
        numeric=(0, 2, 3, 4, 5),
    )
    by_country = table(
        ["Puesto", "País", "Clientes", "Clientes con compra", "Pedidos", "Revenue",
         "Ticket medio", "% del total"],
        [
            (rank, country, cust, buyers, orders, money(rev),
             money(avg) if avg is not None else "—", pct(share))
            for country, cust, buyers, orders, rev, avg, share, rank in q(
                "SELECT * FROM gold_sales_by_country ORDER BY revenue_rank, country_code"
            )
        ],
        numeric=(0, 2, 3, 4, 5, 6, 7),
    )
    no_buyers = q("SELECT COUNT(*) FROM gold_sales_by_customer WHERE orders = 0").fetchone()[0]

    return f"""# Capa Gold

> Generado automáticamente por `scripts/silver_to_gold.py` a partir de `Silver/` el {LOAD_TS} (UTC). **No editar a mano.**
> Importes sin símbolo: moneda sin confirmar. Datos sin validar como datos de negocio (ver `ANALISIS_SILVER.md`, S7).
> Criterios y decisiones: [`PROPUESTA_GOLD.md`](../PROPUESTA_GOLD.md).

## 1. Respuestas

{answers}

"Mayor comprador" se mide por importe (decisión GD7 en `PROPUESTA_GOLD.md`).

## 2. KPIs globales

{kpis}

## 3. Ventas por producto

{by_product}

## 4. Ventas por país

Los clientes sin país se agrupan como `{NO_COUNTRY}`.

{by_country}

## 5. Ventas por cliente

Todos los clientes del maestro, incluidos los {no_buyers} sin compra (importe 0). Los empates comparten puesto.

{by_customer}
"""


def main(silver, gold):
    silver, gold = Path(silver), Path(gold)
    con = build(silver)
    try:
        content = render(con)
    finally:
        con.close()
    gold.mkdir(parents=True, exist_ok=True)
    target, tmp = gold / "GOLD.md", gold / "GOLD.md.tmp"
    tmp.write_text(content, encoding="utf-8", newline="\n")
    os.replace(tmp, target)  # sustitución atómica: nunca queda un GOLD.md a medias
    print(f"{target}: generado")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(*sys.argv[1:])

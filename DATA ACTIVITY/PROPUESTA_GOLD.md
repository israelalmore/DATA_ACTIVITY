# Capa Gold

Tablas de negocio construidas a partir de `Silver/`. Parte de [`ANALISIS_SILVER.md`](ANALISIS_SILVER.md).

> **Estado: implementada (G1–G5).** Las cifras salen de la Silver actual y **no son datos de negocio validados** (ver S7 en el análisis de Silver). Moneda sin confirmar (GD2).

---

## 1. Principio y formato

- Gold = **tablas listas para consumir**, agregadas y con nombres de negocio.
- **Solo tablas para leer, ningún CSV ni base de datos.** Gold es un único fichero Markdown: [`Gold/GOLD.md`](Gold/GOLD.md). Cada tabla G1–G5 es una sección.
- **Solo lee Silver** (`clean_customers.csv`, `clean_sales.csv`). Gold no limpia: si algo está mal, se corrige en Silver y se regenera Gold.
- `GOLD.md` **se genera, no se edita a mano**. Los cálculos se hacen en SQL sobre una base SQLite **en memoria**, que se descarta al terminar.
- Importes en céntimos enteros durante el cálculo (sumas exactas) y con 2 decimales y formato español en la tabla (`16.385,00`).
- Linaje: la cabecera de `GOLD.md` indica el origen y la fecha de generación (UTC).

## 2. Cómo se genera

```bash
cd "DATA ACTIVITY"
python scripts/bronze_to_silver.py Bronze Silver   # si ha cambiado Bronze
python scripts/silver_to_gold.py Silver Gold
```

- Script: [`scripts/silver_to_gold.py`](scripts/silver_to_gold.py). Solo biblioteca estándar.
- **Idempotente**: reescribe `GOLD.md` entero. Se escribe en un fichero temporal y se sustituye al final, así nunca queda a medias.
- **Controles de conciliación**: si alguno falla, el script aborta y no toca el `GOLD.md` anterior.
  - Σ ventas por cliente, por producto y por país = `total_revenue`.
  - Σ pedidos por cliente = `total_orders`.
  - Σ clientes por país = `total_customers`.
  - Existen las respuestas Q1–Q3.

---

## 3. Tablas

Los nombres `gold_*` son los de las tablas en el cálculo; en `GOLD.md` aparecen como secciones con encabezados en español.

### G1 · `gold_sales_by_customer` — ventas por cliente (tabla pedida)

Una fila por cliente del maestro, **incluidos los 59 que no han comprado** (con 0).

| Columna | Definición |
|---|---|
| `customer_id` (PK), `customer_name`, `country_code` | Del maestro; país nulo → `N/D` |
| `orders` | Nº de pedidos |
| `total_sales` | Σ `amount` |
| `revenue_share` | `total_sales / total_revenue` |
| `sales_rank` | Puesto por `total_sales` (los empates comparten puesto) |

Top actual: 106 Pedro 300,00 · 101 Ana 260,00 (3 pedidos) · 109 Elena 220,00.

### G2 · `gold_kpis` — indicadores globales (1 fila)

| Columna | Definición | Valor actual |
|---|---|---|
| `total_revenue` | Σ `amount` | 16.385,00 |
| `total_orders` | Nº de pedidos | 191 |
| `avg_order_value` | `total_revenue / total_orders` | 85,79 |
| `total_customers` | Nº de clientes | 248 |
| `buying_customers` | Clientes con ≥ 1 pedido | 189 |
| `buyer_rate` | `buying_customers / total_customers` | 76,2 % |

### G3 · `gold_sales_by_product`

| Columna | Definición |
|---|---|
| `product` (PK) | Producto |
| `orders` | Nº de pedidos |
| `revenue` | Σ `amount` |
| `avg_price` | `revenue / orders` |
| `revenue_share` | `revenue / total_revenue` |
| `revenue_rank` | Puesto por `revenue` |

Actual: monitor 64 pedidos, 13.190,00 (80,5 %) · teclado 65, 1.950,00 · ratón 62, 1.245,00.

### G4 · `gold_sales_by_country`

| Columna | Definición |
|---|---|
| `country_code` (PK) | ISO; los nulos se agrupan como `N/D` |
| `customers` | Nº de clientes del país |
| `buying_customers` | Clientes del país con ≥ 1 pedido |
| `orders` | Nº de pedidos |
| `revenue` | Σ `amount` |
| `avg_order_value` | `revenue / orders` |
| `revenue_share` | `revenue / total_revenue` |
| `revenue_rank` | Puesto por `revenue` |

Actual: ES 14.235,00 (86,9 %) · PT 730,00 · IT 500,00 · FR 420,00 · DE 250,00 · N/D 220,00 · GB 30,00.

### G5 · `gold_business_answers` — respuestas a las preguntas de negocio

Una fila por ganador; **si hay empate en el primer puesto, salen todos**.

| `question_id` | `question` | `answer` actual | `value` |
|---|---|---|---|
| Q1 | Who is the largest buyer? | 106 - Pedro (PT, 1 pedido) | 300,00 |
| Q2 | Which product generates the most revenue? | monitor (80,5 %) | 13.190,00 |
| Q3 | Which country generates the most revenue? | ES (86,9 %) | 14.235,00 |

Columnas: `question_id`, `question`, `answer`, `value`, `share`, `detail`.

> **Q1 depende de qué es "mayor comprador" (GD7).** Por importe es el **106 Pedro** (300,00 en 1 pedido). Por nº de pedidos es la **101 Ana** (3 pedidos, 260,00), la única clienta recurrente. Se usa importe por defecto.

---

## 4. Qué ha salido de la propuesta anterior y por qué

Los logs se movieron de `Silver/` a `Analisis/`, así que **ya no pueden alimentar Gold** sin romper el principio de §1.

| Antes | Ahora |
|---|---|
| `gold_activity_summary` (eventos y errores por acción) | Fuera de Gold |
| `last_log_action`, `last_log_level` y `has_failed_purchase_log` en el resumen por cliente | Fuera de Gold |
| GD1: marcar las 7 ventas con `ERROR compra` | No se pueden marcar desde Gold: **cuentan como facturación** (520,00, 3,2 %) |

Si se quieren recuperar, los logs tienen que volver a Silver como dataset oficial (decisión GD8).

---

## 5. Más tablas posibles con la Silver actual

Todas se pueden calcular solo con clientes y ventas.

| Tabla propuesta | Qué responde | Valor para negocio |
|---|---|---|
| `gold_sales_by_country_product` | ¿Qué producto vende más en cada país? Matriz país × producto con pedidos e importe | Alto: ver si el monitor domina igual fuera de ES |
| `gold_customer_segments` | ¿Cuántos clientes y cuánto importe hay en cada tramo? Por ejemplo: sin compra, < 50, 50–200, > 200 | Alto: base para campañas y priorizar cuentas |
| `gold_customer_pareto` | ¿Cuántos clientes generan el 80 % del importe? Ranking con % acumulado | Medio: con 1 pedido por cliente casi todo depende de quién compró monitor |
| `gold_product_mix` | ¿Qué clientes compran solo accesorios (teclado o ratón) y cuáles monitor? | Medio: detectar oportunidades de venta cruzada |
| `gold_product_price_stats` | Precio mínimo, máximo y mediana por producto | Bajo: los precios parecen fijos (S7), pero sirve de control |

Clientes sin compra (59): no hace falta otra tabla, es `gold_sales_by_customer WHERE orders = 0`.

## 6. Lo que NO se puede construir (y por qué)

| Análisis | Bloqueo | Qué haría falta |
|---|---|---|
| Ventas por día, mes o año, y tendencias | No hay fechas (S3) | Fecha del pedido en el origen |
| Actividad, errores, embudo login → compra | Logs fuera de Silver y 1 evento por cliente (S2) | Logs en Silver, con sesión y timestamp |
| Cohortes, retención, recurrencia | Sin fechas y 188 de 189 compradores con un solo pedido | Fechas e histórico |
| Conciliación ventas ↔ logs | Sin `order_id` en el log (S1, S4) | Identificador de pedido en el evento `compra` |
| Importes en una moneda de reporte | Moneda desconocida (S5) | Moneda por pedido |
| Margen o rentabilidad | Sin coste ni precio de lista | Catálogo de productos |

---

## 7. Decisiones

| # | Decisión | Aplicado | Impacto |
|---|---|---|---|
| GD1 | Ventas de clientes con `ERROR compra` en el log | **Cuentan**; no se pueden marcar (ver §4) | 520,00 (3,2 %) del importe |
| GD2 | Moneda de `amount` | Pendiente: importes **sin símbolo** | Todas las tablas con importes |
| GD3 | Clientes sin país | Agrupados como `N/D` | 2 clientes, 220,00 |
| GD4 | Formato de Gold | **Markdown** (`Gold/GOLD.md`), solo tablas para leer | Si llega una herramienta de BI o un data warehouse, las mismas consultas SQL sirven para crear tablas reales |
| GD5 | Generación | `scripts/silver_to_gold.py`, idempotente y con controles | — |
| GD6 | Decisiones D1–D8 de Silver | Se heredan tal cual | Si cambian, se regenera Silver y después Gold |
| GD7 | Definición de "mayor comprador" | **Por importe** (`total_sales`) | Por pedidos la respuesta cambia (101 Ana) |
| GD8 | ¿Los logs vuelven a Silver? | No: quedan en `Analisis/` | Sin tablas de actividad en Gold |

## 8. Siguientes pasos

1. Validar GD2, GD7, GD8 y las D1–D8 pendientes con el propietario de los datos.
2. Elegir cuáles de las tablas de §5 se construyen.
3. Antes de publicar cifras fuera del equipo, confirmar el origen de los datos (S7).

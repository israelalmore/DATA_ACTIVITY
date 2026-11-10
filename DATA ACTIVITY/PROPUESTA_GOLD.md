# Propuesta de la capa Gold

Qué tablas de negocio se pueden construir a partir de `Silver/` y cuáles no. Parte de [`ANALISIS_SILVER.md`](ANALISIS_SILVER.md).

> **Estado: propuesta.** No se ha escrito nada en `Gold/`. Las cifras de ejemplo salen de la Silver actual y **no son datos de negocio validados** (ver S7 en el análisis de Silver).

---

## 1. Principio

Gold = **tablas listas para consumir** (informes, dashboards), agregadas y con nombres de negocio. Gold no limpia: **todo lo que entra viene de Silver**. Si algo está mal, se corrige en Silver y se regenera Gold.

---

## 2. Tablas propuestas (viables hoy)

### G1 · `gold_kpis` — indicadores globales (1 fila)

| Columna | Definición | Valor actual |
|---|---|---|
| `total_revenue` | Σ `amount` | 16.385,00 |
| `total_orders` | Nº de pedidos | 191 |
| `avg_order_value` | `total_revenue / total_orders` | 85,79 |
| `total_customers` | Nº de clientes | 248 |
| `buying_customers` | Clientes con ≥ 1 pedido | 189 |
| `buyer_rate` | `buying_customers / total_customers` | 76,2 % |

### G2 · `gold_sales_by_product`

| Columna | Definición |
|---|---|
| `product` | Producto |
| `orders` | Nº de pedidos |
| `revenue` | Σ `amount` |
| `avg_price` | `revenue / orders` |
| `revenue_share` | `revenue / total_revenue` |

Ejemplo: monitor 64 pedidos, 13.190,00 (80,5 %) · teclado 65, 1.950,00 · ratón 62, 1.245,00.

### G3 · `gold_sales_by_country`

| Columna | Definición |
|---|---|
| `country_code` | ISO; los nulos se agrupan como `N/D` |
| `customers` | Nº de clientes del país |
| `orders` | Nº de pedidos |
| `revenue` | Σ `amount` |
| `revenue_share` | % sobre el total |

Ejemplo: ES 14.235,00 (86,9 %) · PT 730,00 · IT 500,00 · FR 420,00 · DE 250,00 · N/D 220,00 · GB 30,00.

### G4 · `gold_customer_summary` — una fila por cliente

| Columna | Definición |
|---|---|
| `customer_id`, `customer_name`, `country_code` | Del maestro |
| `orders` | Nº de pedidos (0 si no ha comprado) |
| `revenue` | Σ `amount` (0 si no ha comprado) |
| `is_buyer` | `orders > 0` |
| `last_log_action`, `last_log_level` | Su único evento de log, si lo tiene |
| `has_failed_purchase_log` | `true` si su log es `ERROR compra` (ver decisión GD1) |

Sirve como base para segmentar clientes: compradores, no compradores y clientes con incidencias.

### G5 · `gold_activity_summary`

| Columna | Definición |
|---|---|
| `action` | `login`, `logout`, `compra` o `timeout` |
| `events` | Nº de eventos |
| `errors` | Eventos con `log_level = ERROR` |
| `warnings` | Eventos con `log_level = WARN` |
| `error_rate` | `errors / events` |

Ejemplo: login 80 eventos, 24 ERROR (30 %) · compra 51, 7 ERROR (13,7 %) · timeout 30, todos WARN.

---

## 3. Lo que NO se puede construir (y por qué)

| Análisis | Bloqueo | Qué haría falta |
|---|---|---|
| Ventas por día, mes o año, y tendencias | No hay fechas (S3) | Fecha del pedido en el origen |
| Embudo login → compra y conversión | 1 evento por cliente (S2) | Logs completos con sesión y timestamp |
| Cohortes, retención, recurrencia | Sin fechas y 188 de 189 compradores con un solo pedido | Fechas e histórico |
| Conciliación ventas ↔ logs | Sin `order_id` en el log (S1, S4) | Identificador de pedido en el evento `compra` |
| Importes en una moneda de reporte | Moneda desconocida (S5) | Moneda por pedido |
| Margen o rentabilidad | Sin coste ni precio de lista | Catálogo de productos |

---

## 4. Decisiones antes de construir Gold

| # | Decisión | Propuesta | Impacto |
|---|---|---|---|
| GD1 | ¿Las 7 ventas de clientes con `ERROR compra` cuentan como facturación? | **Contarlas**, pero marcarlas con `has_failed_purchase_log` para poder filtrarlas | 520,00 (3,2 %) del importe |
| GD2 | Moneda de `amount` | Pendiente: mostrar importes **sin símbolo** hasta confirmarla | Todas las tablas con importes |
| GD3 | Clientes sin país | Agruparlos como `N/D` | 2 clientes, 220,00 |
| GD4 | Formato de Gold | CSV, igual que Silver | Si hay herramienta de BI, valorar Parquet o una tabla en BD |
| GD5 | Generación | Script `scripts/silver_to_gold.py`, idempotente como el de Silver | — |
| GD6 | Decisiones D1–D8 de Silver | Se heredan tal cual | Si cambian, se regenera Silver y después Gold |

---

## 5. Siguientes pasos

1. Validar GD1–GD6 y las D1–D8 pendientes con el propietario de los datos.
2. Implementar `silver_to_gold.py` con G1–G5.
3. Antes de publicar cifras fuera del equipo, confirmar el origen de los datos (S7).

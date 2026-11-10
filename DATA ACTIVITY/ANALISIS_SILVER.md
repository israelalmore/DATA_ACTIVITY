# Análisis de la capa Silver

Estado de `DATA ACTIVITY/Silver/` después de la carga desde Bronze y si está lista para pasar a Gold. Parte de [`ANALISIS_BRONZE.md`](ANALISIS_BRONZE.md) y [`PROPUESTA_SILVER.md`](PROPUESTA_SILVER.md).

> Los criterios aplicados son los **por defecto** de `PROPUESTA_SILVER.md`. Las decisiones D1–D8 siguen abiertas y se han tratado como supuestos (ver §5).

---

## 1. Cómo se genera

```bash
cd "DATA ACTIVITY"
python scripts/bronze_to_silver.py Bronze Silver
```

- Script: [`scripts/bronze_to_silver.py`](scripts/bronze_to_silver.py). Solo usa la biblioteca estándar de Python.
- **Idempotente**: cada ejecución sobrescribe Silver entera a partir de Bronze. Bronze no se modifica.
- Las reglas son **genéricas**, no listas de ids a mano: dominios permitidos, integridad referencial, atípicos (> 5× la mediana del producto) y duplicados consecutivos.

---

## 2. Ficheros generados

| Fichero | Contenido | Filas | Origen |
|---|---|---|---|
| `clean_customers.csv` | Maestro de clientes | **248** | `clientes.json` (250) |
| `clean_sales.csv` | Pedidos | **191** | `ventas.csv` (200) |
| `clean_logs.csv` | Eventos de actividad | **193** | `logs.txt` (207 líneas) |
| `rejected_records.csv` | Cuarentena: lo que no sube, con el motivo | **25** | Los tres |

Formato común: CSV, UTF-8, separador coma, fin de línea LF y cabecera. En CSV, `NULL` se representa como **campo vacío**.

---

## 3. Normalización aplicada

### 3.1 Nombres de campo

Se pasan a `snake_case` en inglés, coherente con los nombres de fichero pedidos (`clean_sales`, `clean_customers`):

| Bronze | Silver | Tipo Silver |
|---|---|---|
| `clientes.id_cliente` | `customer_id` | entero (PK) |
| `clientes.nombre` | `customer_name` | texto, admite NULL |
| `clientes.pais` | `country_code` | ISO 3166-1 alfa-2, admite NULL |
| `ventas.id_pedido` | `order_id` | entero (PK) |
| `ventas.id_cliente` | `customer_id` | entero (FK) |
| `ventas.producto` | `product` | texto: `teclado`, `raton` o `monitor` |
| `ventas.importe` | `amount` | decimal con 2 decimales, mayor que 0 |
| `logs [NIVEL]` | `log_level` | `INFO`, `WARN` o `ERROR` |
| `logs user=` | `customer_id` | entero (FK) |
| `logs action=` | `action` | `login`, `logout`, `compra` o `timeout` |

Columnas de linaje en todas las tablas: `_source_file`, `_source_line` y `_load_ts` (UTC).

> Los **valores** de `product` y `action` se mantienen en español. Traducirlos es una decisión de negocio, no de limpieza.

### 3.2 Conversiones de formato

| Conversión | Registros afectados |
|---|---|
| `id_cliente` de texto a entero | 1 (cliente 120) |
| `UK` → `GB` (ISO) | 1 (cliente 119) |
| `??` / `null` → NULL en país | 2 (clientes 117 y 138) |
| Nombre vacío → NULL | 1 (cliente 112) |
| `importe` → decimal con 2 decimales (`30` → `30.00`) | 191 |
| Texto de log → 3 columnas | 193 |
| CRLF → LF y eliminación de líneas en blanco | Los tres ficheros |

### 3.3 Limpieza (rechazos)

| Origen | Rechazados | Motivos |
|---|---|---|
| `clientes.json` | 2 | Clientes de test/debug (200 `TestUser`, 201 `Debug`) |
| `ventas.csv` | 9 | 4 de clientes de test, cliente inexistente (999), sin cliente, importe no numérico, importe negativo, posible duplicado (pedido 32) |
| `logs.txt` | 14 | Eventos de test/debug, `user` no numérico o inexistente, `user` o `action` vacíos, líneas vacías, cliente de test |

El detalle, línea a línea, está en `rejected_records.csv`. Coincide exactamente con las listas de exclusión de `PROPUESTA_SILVER.md`.

> **Cómo se interpretó "Remove log errors":** se eliminan las líneas de log **erróneas** (mal formadas, de test o sin referencia válida). Los eventos con nivel `ERROR` bien formados **se mantienen**, porque son información (un login o una compra fallidos). Ver §5, S1.

---

## 4. Validación

Comprobaciones hechas sobre los CSV generados, con un script independiente del de carga:

| Comprobación | Resultado |
|---|---|
| `customer_id` único en customers | ✅ |
| `order_id` único en sales | ✅ |
| Toda venta apunta a un cliente existente | ✅ |
| Todo log apunta a un cliente existente | ✅ |
| `amount` > 0 y con 2 decimales | ✅ |
| `product`, `log_level` y `action` dentro de su dominio | ✅ |
| Sin CRLF | ✅ |
| Nulos en sales y logs | 0 |
| Nulos en customers | 3, todos esperados: 112 sin nombre; 117 y 138 sin país |

### Perfil de Silver

- **Ventas:** 191 pedidos, importe total **16.385,00** (moneda sin confirmar), ticket medio **85,79**.
  - Monitor: 64 pedidos, 13.190,00 (80 % del importe).
  - Teclado: 65 pedidos, 1.950,00.
  - Ratón: 62 pedidos, 1.245,00.
- **Clientes:** 248. 189 tienen al menos una compra y 59 ninguna. Solo uno tiene más de una compra (el 101, con 3).
- **País:** ES concentra 224 clientes (90 %) y el 87 % del importe. Hay 2 clientes sin país.
- **Logs:** INFO 131 · WARN 31 · ERROR 31. Acciones: login 80, compra 51, logout 32, timeout 30.

---

## 5. ¿Está lista para Gold?

**Sí, para agregados estáticos** (por producto, por país y por cliente). **No, para análisis temporales ni de comportamiento.** Lo que limita:

| # | Hallazgo | Impacto en Gold |
|---|---|---|
| S1 | **Los 7 clientes con `ERROR compra` en el log tienen una venta en `clean_sales`** (pedidos 12, 37, 57, 77, 90, 102 y 130; 520,00 en total, el 3,2 % del importe) | Si la compra falló, esas ventas inflan la facturación. Sin `order_id` en el log no se puede saber si el error y la venta son el mismo intento |
| S2 | **Cada cliente aparece una sola vez en los logs** (193 eventos, 193 clientes distintos) | No hay sesiones ni recorridos: un embudo login → compra o tasas por cliente **no tienen sentido** |
| S3 | **Sin fechas** en ventas ni en logs | Sin series temporales, comparativas por periodo, cohortes ni retención |
| S4 | Ventas y logs no cuadran: 140 clientes con venta no tienen evento `compra`, y 2 con `compra` en el log no tienen venta | Los logs no sirven para validar ventas; son fuentes independientes |
| S5 | Moneda de `amount` desconocida | Los importes de Gold no se pueden etiquetar ni sumar con otras fuentes |
| S6 | 2 clientes sin país (117 y 138, con 220,00 en ventas) | En los agregados por país necesitan un grupo "N/D" |
| S7 | Datos casi seguro sintéticos (87 % `userNNN`, precios fijos) | Las cifras de Gold describen el dataset, no el negocio |
| S8 | D1–D8 de `PROPUESTA_SILVER.md` se aplicaron con su opción por defecto | Si alguna cambia, hay que relanzar el script; Gold hereda el cambio |

Propuesta para Gold: [`PROPUESTA_GOLD.md`](PROPUESTA_GOLD.md).

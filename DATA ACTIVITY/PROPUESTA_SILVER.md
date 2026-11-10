# Propuesta de carga a la capa Silver

Qué datos de `Bronze/` subirían a `Silver/`, con qué transformaciones y qué se queda fuera. Parte de los problemas descritos en [`ANALISIS_BRONZE.md`](ANALISIS_BRONZE.md).

> **Estado: propuesta.** No se ha escrito nada en `Silver/`. Los criterios de exclusión y corrección deben validarse con el propietario de los datos antes de implementarse.

---

## 1. Resumen

| Dataset | Registros en Bronze | Suben a Silver | Excluidos (cuarentena) | Corregidos al subir |
|---|---|---|---|---|
| `clientes` | 250 | **248** | 2 | 5 |
| `ventas` | 200 | **191** | 9 | 0 |
| `logs` | 207 líneas | **193** | 14 | 0 (se estructuran) |

---

## 2. Criterios generales

1. **Silver = datos limpios, tipados y coherentes entre sí.** Si un registro no se puede corregir sin inventar información, no sube.
2. **Corregir solo lo que es inequívoco**: cambiar el tipo de dato, normalizar códigos a un estándar o convertir valores centinela (`??`, `""`) en `NULL`.
3. **No se borra nada**: lo excluido va a una **cuarentena** con el motivo, para revisarlo después. Bronze no se toca.
4. **Integridad referencial**: toda venta y todo log de Silver apunta a un cliente que existe en Silver.
5. **Datos de test fuera**: los clientes de test y **todo lo que cuelga de ellos** (ventas y logs) no suben.
6. **Trazabilidad**: cada registro de Silver guarda su origen con estas columnas de linaje:

| Columna | Tipo | Contenido |
|---|---|---|
| `_fichero_origen` | texto | `clientes.json`, `ventas.csv` o `logs.txt` |
| `_linea_origen` | entero | Línea del fichero Bronze |
| `_fecha_carga` | timestamp | Momento de la carga a Silver |

---

## 3. `clientes`

### 3.1 Esquema Silver

| Columna | Tipo | Nulos | Regla |
|---|---|---|---|
| `id_cliente` | entero | No | Clave primaria |
| `nombre` | texto | Sí | Cadena vacía → `NULL` |
| `pais` | texto (ISO 3166-1 alfa-2) | Sí | `??` y `null` → `NULL`; `UK` → `GB` |

### 3.2 Registros que suben

**`id_cliente` 101–350, excepto 200 y 201** → 248 clientes.

Suben **con corrección** (5):

| Línea | `id_cliente` | Bronze | Silver |
|---|---|---|---|
| 13 | 112 | `nombre: ""` | `nombre: NULL` |
| 18 | 117 | `pais: null` | `pais: NULL` (sin cambio de valor, solo tipado) |
| 20 | 119 | `pais: "UK"` | `pais: "GB"` |
| 21 | 120 | `id_cliente: "120"` (texto) | `id_cliente: 120` (entero) |
| 41 | 138 | `pais: "??"` | `pais: NULL` |

> Los clientes 112, 117 y 138 suben aunque les falte información porque **tienen ventas válidas** (pedidos 14, 20 y 45). Excluirlos dejaría esas ventas sin cliente.

Distribución de `pais` en Silver: ES 224 · FR 8 · IT 6 · PT 4 · DE 3 · GB 1 · `NULL` 2.

### 3.3 Excluidos

| Línea | `id_cliente` | Motivo |
|---|---|---|
| 109 | 200 | Registro de test (`TestUser`, país `??`) |
| 111 | 201 | Registro de debug (`Debug`) |

---

## 4. `ventas`

### 4.1 Esquema Silver

| Columna | Tipo | Nulos | Regla |
|---|---|---|---|
| `id_pedido` | entero | No | Clave primaria |
| `id_cliente` | entero | No | Clave foránea → `clientes.id_cliente` |
| `producto` | texto | No | Valores permitidos: `teclado`, `raton`, `monitor` |
| `importe` | decimal(10,2) | No | `> 0`; moneda **pendiente de confirmar** |

Además: se eliminan las líneas en blanco y se normaliza el fin de línea (CRLF → LF).

### 4.2 Registros que suben

**`id_pedido` 1–200, excepto 5, 6, 7, 15, 29, 30, 32, 107 y 108** → 191 pedidos.

- Por producto: teclado 65 · monitor 64 · ratón 62.
- Importe total: 16.385 (moneda sin confirmar).

### 4.3 Excluidos

| Línea | `id_pedido` | Datos Bronze | Motivo |
|---|---|---|---|
| 6 | 5 | `999, monitor, 150` | Cliente inexistente |
| 7 | 6 | `104, raton, -10` | Importe negativo: sin estado de pedido no se sabe si es devolución o error |
| 8 | 7 | `105, teclado, abc` | Importe no numérico |
| 16 | 15 | `—, raton, 20` | Sin `id_cliente` |
| 30 | 29 | `200, test, 0` | Cliente de test y producto `test` |
| 31 | 30 | `201, monitor, 9999` | Cliente de debug e importe atípico |
| 34 | 32 | `101, teclado, 30` | Posible duplicado del pedido 31 (sin fecha no se puede confirmar) |
| 116 | 107 | `200, teclado, 30` | Cliente de test |
| 117 | 108 | `201, raton, 20` | Cliente de debug |

---

## 5. `logs`

### 5.1 Esquema Silver

El texto plano pasa a tabla:

| Columna | Tipo | Nulos | Origen |
|---|---|---|---|
| `nivel` | texto | No | `[NIVEL]` → `INFO`, `WARN`, `ERROR` |
| `id_cliente` | entero | No | `user=<id>`; clave foránea → `clientes.id_cliente` (**se asume** que `user` = `id_cliente`) |
| `accion` | texto | No | `action=<acción>` → `login`, `logout`, `compra`, `timeout` |

> No hay columna de fecha porque **el origen no la tiene**. No se inventa.

### 5.2 Registros que suben

**Líneas 1–207, excepto 4, 15, 22, 23, 25, 27, 104, 105, 106, 107, 117, 124, 155 y 186** → 193 eventos.

- Por nivel: INFO 131 · WARN 31 · ERROR 31.
- Por acción: login 80 · compra 51 · logout 32 · timeout 30.

Suben, pero **conviene marcarlos** para revisarlos:

- Línea 19 `[WARN] user=117 action=login`: es la única combinación WARN + login.
- Las 7 líneas `ERROR` + `compra`: no se sabe si la compra llegó a hacerse.

### 5.3 Excluidos

| Línea | Contenido Bronze | Motivo |
|---|---|---|
| 4 | `[ERROR] user=999 action=login` | Cliente inexistente |
| 15 | `[ERROR] user=abc action=login` | `user` no numérico |
| 22 | `[INFO] action=compra` | Sin `user` |
| 23 | `[INFO] user=120 action=` | `action` vacía |
| 25 | `[DEBUG] user=122 action=test` | Evento de test |
| 27 | `[ERROR] user=999 action=compra` | Cliente inexistente |
| 104 | `[INFO] user=200 action=login` | Cliente de test |
| 105 | `[DEBUG] user=201 action=test` | Cliente de debug y evento de test |
| 106 | `[DEBUG] user=202 action=test` | Evento de test |
| 107 | `[DEBUG] user=203 action=test` | Evento de test |
| 117 | `[INFO] user=213 action=` | `action` vacía |
| 124 | `[ERROR] user=xyz action=compra` | `user` no numérico |
| 155 | *(vacía)* | Línea vacía |
| 186 | *(vacía)* | Línea vacía |

---

## 6. Decisiones pendientes de validar

Todas afectan a lo que sube. Hay que cerrarlas con el propietario de los datos **antes** de implementar la carga:

| # | Decisión | Propuesta actual | Alternativa |
|---|---|---|---|
| D1 | ¿`id_cliente` 999 es un centinela de "desconocido"? | Excluir | Crear un cliente "desconocido" en Silver |
| D2 | Pedido 6 (`-10`) | Excluir | Subirlo como devolución si se confirma |
| D3 | Pedido 32 (posible duplicado) | Excluir | Subirlo si se confirma que es una compra real |
| D4 | Pedido 30 (`9999`) | Excluir (además es del cliente `Debug`) | — |
| D5 | ¿`logs.user` = `clientes.id_cliente`? | Se asume que sí | Si no, los logs no se pueden enlazar con clientes |
| D6 | `UK` → `GB` | Normalizar a ISO | Mantener `UK` si algún sistema destino lo espera |
| D7 | Clientes `userNNN` (87 %) | Suben: son los únicos datos disponibles | Si el conjunto es entero de prueba, no debería subir nada |
| D8 | Moneda de `importe` | Sin definir | Añadir la columna `moneda` cuando se confirme |

> **D7 condiciona todo el documento**: si se confirma que el conjunto es sintético, esta propuesta vale como diseño del proceso, pero no como datos de negocio.

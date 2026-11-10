# Análisis de la capa Bronze

Diagnóstico de los ficheros de `DATA ACTIVITY/Bronze/`. Este documento **solo describe** lo que hay en los datos: no se ha modificado ningún fichero ni se ha escrito nada en `Silver/` ni en `Gold/`, que siguen vacías.

> Los números de línea se refieren a la línea del fichero original (contando la cabecera y las líneas en blanco).

---

## 1. Identificación

### 1.1 Tipo de cada fichero

| Fichero | Tipo | Estructura | Volumen | Codificación / fin de línea |
|---|---|---|---|---|
| `clientes.json` | **Semiestructurado** (JSON) | Array de objetos `{id_cliente, nombre, pais}`, un objeto por línea | 250 registros, 273 líneas | ASCII, LF |
| `ventas.csv` | **Estructurado** (CSV tabular) | Cabecera `id_pedido,id_cliente,producto,importe`, separador coma | 200 filas de datos, 218 líneas | ASCII, **CRLF** |
| `logs.txt` | **No estructurado / semiestructurado** (texto plano de log) | Patrón `[NIVEL] user=<id> action=<acción>` | 207 líneas | ASCII, LF |

Papel de cada uno en el modelo:

- `clientes.json` → **dimensión** de clientes (maestro).
- `ventas.csv` → **hechos** transaccionales (pedidos).
- `logs.txt` → **eventos** de actividad de usuario.

Relación aparente: `ventas.id_cliente` y `logs.user` apuntan a `clientes.id_cliente`. Ninguna de las dos relaciones está documentada ni garantizada.

### 1.2 Problemas detectados

#### `clientes.json`

| # | Problema | Dónde | Impacto |
|---|---|---|---|
| C1 | `id_cliente` como **texto** en vez de entero | Línea 21: `"id_cliente":"120"` (Eva) | Rompe el tipado y los joins si no se castea |
| C2 | **Nombre vacío** | Línea 13: `id_cliente` 112, `"nombre":""` | Registro sin identificación legible |
| C3 | **País nulo** | Línea 18: `id_cliente` 117, `"pais":null` | Sin país |
| C4 | **País inválido** `??` (cliente sin país real) | Línea 41: `id_cliente` 138 (`user8`); línea 109: `id_cliente` 200 (`TestUser`) | Valor centinela, no es un país |
| C5 | Código `UK` no es ISO 3166-1 | Línea 20: `id_cliente` 119 | El código ISO es `GB`; los cruces con catálogos estándar fallarán |
| C6 | **Nombres de prueba** `user1` … `user218` | 218 de 250 registros (87 %) | Datos sintéticos, no clientes reales |
| C6b | **Clientes de test/debug explícitos** | Línea 109: `id_cliente` 200 `TestUser`; línea 111: `id_cliente` 201 `Debug` | Registros de prueba en el maestro; son los clientes de los pedidos 29 (`test`) y 30 (`9999`) |
| C7 | Nombre repetido (`Ana`) con distinto id | `id_cliente` 101 y 111 | No es necesariamente un error, pero puede indicar un **duplicado** de persona |
| C8 | Nombres sin tildes (`Maria`, `Lucia`, `Raul`) | Varios | Posible pérdida de caracteres en la extracción |
| C9 | 22 líneas en blanco dentro del array | Cada 10 registros aprox. | El JSON es válido igualmente, pero indica generación manual o concatenación |

No hay ids duplicados (250 distintos, rango 101–350).

#### `ventas.csv`

| # | Problema | Dónde | Impacto |
|---|---|---|---|
| V1 | `importe` **no numérico** (`abc`) | Pedido 7 | Fila no cargable como número |
| V2 | `importe` **negativo** (`-10`) | Pedido 6 (ratón) | ¿Devolución o error? No se distingue |
| V3 | `importe` **atípico** (`9999`) | Pedido 30 (monitor, cliente 201) | Resto de monitores entre 150 y 300; distorsiona sumas y medias |
| V4 | **Producto de prueba** `test` con importe `0` | Pedido 29 (cliente 200) | Registro de test mezclado con producción |
| V5 | `id_cliente` **vacío** | Pedido 15 | Venta huérfana |
| V6 | `id_cliente` **inexistente** (`999`) | Pedido 5 | Rompe integridad referencial con `clientes.json` |
| V7 | **Posible duplicado** | Pedidos 31 y 32: mismo cliente (101), producto y importe, consecutivos | Puede ser doble carga; sin fecha no se puede confirmar |
| V8 | 17 líneas en blanco | Cada 10 filas aprox. | Algunos lectores las interpretan como filas nulas |
| V9 | Fin de línea **CRLF** (los otros dos ficheros usan LF) | Todo el fichero | Riesgo de `\r` pegado al último campo (`importe`) en algunas herramientas |
| V10 | Precios **poco realistas** y casi constantes | Teclado siempre 30, ratón 20 (salvo 1 a 25), monitor 200/210 | Refuerza que son datos sintéticos |

No hay `id_pedido` duplicados ni huecos en la secuencia (1–200).

#### `logs.txt`

| # | Problema | Dónde | Impacto |
|---|---|---|---|
| L1 | **Falta `user`** | Línea 22: `[INFO] action=compra` | Evento sin actor |
| L2 | **`action` vacía** | Líneas 23 (`user=120`) y 117 (`user=213`) | Evento sin significado |
| L3 | **`user` no numérico** | `user=abc`, `user=xyz` | No se puede enlazar con clientes |
| L4 | **`user` inexistente** (`999`) | 2 líneas (login y compra, ambas `ERROR`) | Mismo id fantasma que en ventas (V6) |
| L5 | **Eventos de prueba** | 4 líneas `[DEBUG] ... action=test` | Ruido de test en el log |
| L6 | Líneas **vacías** | Líneas 155 y 186 | Ruido |
| L7 | **Sin marca de tiempo** | Todo el fichero | Imposible ordenar, calcular sesiones o cruzar con ventas en el tiempo |
| L8 | Nivel incoherente con la acción | 1 caso `[WARN] ... action=login` (línea 19) | Semántica de niveles no documentada |
| L9 | `compra` con nivel `ERROR` | 9 casos; 8 de esos usuarios **sí tienen venta** en `ventas.csv` | No se sabe si la compra fallida generó pedido o no |

Distribución: `INFO` 132, `ERROR` 35, `WARN` 31, `DEBUG` 4. Acciones: `login` 83, `compra` 53, `logout` 32, `timeout` 30, `test` 4.

#### Problemas transversales

- **Los registros de prueba se propagan entre ficheros**: el cliente 200 (`TestUser`) tiene los pedidos 29 (`test`, importe 0) y 107, y el evento de log de la línea 104; el cliente 201 (`Debug`) tiene los pedidos 30 (importe 9999) y 108, y el evento `DEBUG test` de la línea 105. Los datos de test no están aislados en un solo fichero.
- **El id `999` aparece en ventas y en logs pero no en clientes**: parece un valor centinela ("desconocido") más que un cliente real.
- **Ventas y logs no cuadran**: 200 pedidos frente a 53 eventos `compra`; 143 clientes con venta no tienen ningún `compra` en el log. Los dos ficheros no describen el mismo proceso, o el log está incompleto.
- **57 clientes sin ninguna venta** y los ids 301–350 no aparecen en ventas ni logs.
- **Formatos de fin de línea mezclados** (CRLF en el CSV, LF en el resto).

---

## 2. Respuestas

### 2.1 ¿Qué datos no se pueden considerar fiables?

**No fiables (hay que excluirlos o marcarlos en cuarentena):**

| Fichero | Registros |
|---|---|
| `ventas.csv` | Pedido 5 (cliente 999), 6 (importe negativo), 7 (`abc`), 15 (sin cliente), 29 (`test`/0), 30 (9999), 107 y 108 (clientes de test) |
| `clientes.json` | 112 (sin nombre), 117 (país nulo), 138 (`??`), 200 (`TestUser`, `??`), 201 (`Debug`) |
| `logs.txt` | Línea 22 (sin user), 23 y 117 (sin action), `user=abc`, `user=xyz`, `user=999` (×2), las 4 de `DEBUG/test`, línea 104 (`user=200`, cliente de test) |

**Fiabilidad dudosa (usables con cautela, requieren confirmación):**

- Pedidos 31 y 32: posible duplicado.
- Cliente `"120"`: el dato es correcto, el tipo no; se recupera con un cast.
- Cliente 119 (`UK`): válido pero no estándar.
- Las 9 líneas `ERROR ... compra`: no se sabe si la compra existió.
- **Cualquier métrica temporal basada en los logs**: sin timestamp no tiene base.

**A nivel global:** el conjunto entero parece **sintético o de prueba** (87 % de nombres `userNNN`, precios fijos, producto `test`). Ninguna conclusión de negocio sacada de aquí debería presentarse como real hasta confirmar el origen.

### 2.2 ¿Qué información falta?

**En los propios datos:**

- **Fechas**: ni los pedidos ni los eventos de log tienen fecha/hora. Es la carencia más grave: sin ella no hay series temporales, ni deduplicación fiable, ni cruce ventas↔logs.
- **Moneda** de `importe` y si incluye impuestos.
- **Cantidad** (unidades) por pedido y **precio unitario**: solo hay un importe total.
- **Catálogo de productos** (id de producto, categoría, precio de lista).
- **Estado del pedido** (pagado, cancelado, devuelto): sin él, el `-10` no se puede interpretar.
- Datos del cliente más allá del nombre: **fecha de alta**, segmento, canal, etc.
- En el log: **sesión**, **origen** (web/app/IP) y **detalle del error** en las líneas `ERROR`.

**Metadatos y documentación:**

- **Sistema de origen** de cada fichero y **fecha de extracción**.
- **Diccionario de datos**: significado de cada campo y valores permitidos (p. ej. qué significa `999`, `??` o el nivel `WARN`).
- Confirmación de que **`logs.user` = `clientes.id_cliente`** (se asume, no está documentado).
- Si los ficheros son **cargas completas o incrementales**.
- **Reglas de calidad** acordadas para pasar a Silver (qué se descarta, qué se corrige, qué va a cuarentena).

---

## 3. Siguientes pasos (pendientes, no aplicados)

1. Confirmar con el propietario de los datos el origen y si son de prueba.
2. Acordar el diccionario de datos y el tratamiento de cada problema de la sección 1.2.
3. Solo entonces diseñar la transformación Bronze → Silver.

> Si alguna vez se incorporan datos reales de clientes, `clientes.json` contiene nombre y país asociados a un identificador (dato personal según RGPD): revisarlo con Legal/DPO antes de versionarlo.

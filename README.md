# MPPOT

Repositorio de datos de actividad (clientes, ventas y logs) en estado crudo. Hoy solo contiene ficheros de datos: no hay scripts, comandos, dependencias, tests ni configuración.

> Propósito, origen de los datos y consumidores: **pendiente de confirmar**. Lo aquí descrito se deduce únicamente de los ficheros.

## Estructura

```
MPPOT/
└── DATA ACTIVITY/
    └── Bronze/
        ├── clientes.json
        ├── logs.txt
        └── ventas.csv
```

La carpeta `Bronze` sugiere una arquitectura medallion, pero **solo existe la capa Bronze**: no hay carpetas Silver ni Gold ni código de transformación. Pendiente: confirmar si se plantean y cómo se procesarán.

## Datasets (capa Bronze)

Los datos parecen sintéticos o de prueba (nombres genéricos como `userNNN`, un producto `test`, valores `abc` o `??`) y contienen filas con problemas de calidad, coherentes con una capa cruda sin limpiar.

### `clientes.json`

- Formato: array JSON, un objeto por línea. 250 registros (~12,6 KB).
- Esquema:

| Campo | Tipo aparente | Notas |
|---|---|---|
| `id_cliente` | entero | Único (250 distintos, 101 a 350). Un caso viene como cadena de texto. |
| `nombre` | cadena | Un registro con cadena vacía. |
| `pais` | cadena (código de país) | Mayoría `ES` (225); también FR, IT, PT, DE, UK. Valores anómalos: `??` (2) y `null` (1). |

- Ejemplo ficticio: `{"id_cliente":999001,"nombre":"Nombre Ejemplo","pais":"ES"}`

### `ventas.csv`

- Formato: CSV con cabecera, separador coma. 200 pedidos (~3,9 KB).
- Esquema:

| Columna | Tipo aparente | Notas |
|---|---|---|
| `id_pedido` | entero | Único (200 distintos). |
| `id_cliente` | entero | 195 clientes distintos; referencia aparente a `clientes.json`. Integridad referencial no verificada. |
| `producto` | cadena | `teclado`, `monitor`, `raton` y un valor `test`. |
| `importe` | numérico | Moneda no indicada (pendiente). Una fila con valor no numérico (`abc`). |

### `logs.txt`

- Formato: texto plano, una línea por evento. 207 líneas (~6,1 KB).
- Patrón: `[NIVEL] user=<id> action=<acción>`
- Niveles observados: `INFO` (la mayoría), `ERROR`, `WARN`, `DEBUG`.
- Acciones observadas: `login`, `logout`, `compra`, `timeout`, `test`.
- Sin marca de tiempo. Hay líneas incompletas (sin `user` o con `action` vacío) y algún usuario no presente en clientes.
- Pendiente: sistema de origen y significado de `user` respecto a `id_cliente`.

## Confidencialidad

Los ficheros parecen datos de prueba, pero `clientes.json` contiene nombres de pila y país asociados a un identificador. Si alguna vez se incorporan datos reales de clientes, no deben versionarse en git sin revisión de Legal/DPO (RGPD).

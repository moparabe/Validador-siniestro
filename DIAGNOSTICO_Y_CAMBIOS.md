# Diagnóstico Técnico y Guía de Cambios
## Portal de Carga para Facilitadores — Versión de Producción

---

## 1. DIAGNÓSTICO DEL CÓDIGO ORIGINAL

### ✅ Qué hace bien el código original
- Usa `streamlit-authenticator` para control de acceso por usuario, buena decisión.
- Inserta automáticamente el campo `FACILITADOR` con el nombre del usuario logueado.
- Verifica columnas faltantes y sobrantes antes de aceptar el archivo.
- Genera un nombre de archivo con timestamp para trazabilidad básica.
- Sube el archivo a GitHub usando la API, lo que permite conectar con Power Automate.

### ❌ Riesgos y problemas críticos detectados

| Problema | Impacto |
|---|---|
| **Sin validación de contenido por columna** | Datos sucios llegan directamente a Power BI |
| **Errores tipográficos en el código** (`streamilt`, `streamLit`, `YamL`, `Autorization`) | El código tal como está no ejecuta |
| **Token de GitHub duplicado** (`[\"token\"][\"token\"]`) | Error en producción silencioso |
| **`branch` referenciado como `Branch`** (mayúscula) | `NameError` en tiempo de ejecución |
| **Sin manejo de duplicados** | Un siniestro puede cargarse dos veces |
| **Sin control de errores en GitHub** aparte del código HTTP | Mensajes crípticos al usuario |
| **Sin logs ni auditoría** | Imposible saber quién cargó qué y cuándo |
| **Sin normalización de fechas** | Power BI recibe formatos inconsistentes |
| **Sin control de campos vacíos** en columnas obligatorias | Registros incompletos en el modelo |
| **Sin modularización** | Todo en un solo archivo, difícil de mantener y escalar |
| **Lógica de UI mezclada con lógica de negocio** | Difícil de probar y modificar |
| **Mensaje de éxito muestra URL del archivo** directamente | Posible exposición de ruta interna |

---

## 2. ARQUITECTURA MEJORADA

### Estructura de archivos

```
validador_siniestros/
│
├── app.py                  ← Interfaz Streamlit (solo UI)
├── validators.py           ← Motor de validación (lógica de negocio)
├── validation_config.py    ← Parámetros y catálogos (configuración)
├── file_service.py         ← Lectura, escritura y GitHub (servicios)
├── audit_logger.py         ← Trazabilidad (auditoría)
├── usuarios.py             ← Credenciales de acceso (sin cambios)
└── logs/
    └── auditoria_cargas.csv  ← Log automático de operaciones
```

### Principio de capas

```
[Streamlit UI - app.py]
        ↓ llama
[Servicios - file_service.py / audit_logger.py]
        ↓ usa
[Motor de validación - validators.py]
        ↓ lee reglas de
[Configuración - validation_config.py]
```

Cada capa solo conoce a la capa que tiene debajo. La UI no contiene lógica de negocio.

---

## 3. LÓGICA DE VALIDACIÓN POR COLUMNA

### Estructura parametrizable

Cada columna tiene una entrada en `COLUMN_RULES` (en `validation_config.py`):

```python
"SINIESTRO": {
    "required": True,          # ¿Es obligatorio?
    "type": "siniestro",       # Tipo de validador a aplicar
    "description": "...",      # Texto para mensajes de error
}
```

Para agregar una nueva columna: solo añadir una entrada al diccionario. No hay que tocar el motor de validación.

### Reglas implementadas por columna

| Columna | Regla |
|---|---|
| `SINIESTRO` | 8 dígitos exactos, O "SAN" + 5 dígitos, sin espacios ni especiales, no vacío |
| `POLIZA` | 9 dígitos exactos, solo dígitos, no vacío |
| `RAMO` | 3 dígitos, inicia con "0", solo dígitos, no vacío |
| `NIT/CC` | Solo dígitos, entre 6 y 15 caracteres |
| `AJUSTE` | Valor en catálogo: AUTOS, VIDA |
| `ESTADO_DOCUMENTO` | Valor en catálogo: RECIBIDO, PENDIENTE |
| `FECHA_*` (7 columnas) | Formato válido, convierte a dd/mm/yyyy, rechaza fechas imposibles |
| `RESERVA` | Número positivo, permite decimales, rechaza texto y negativos |
| `ASEGURADO`, `ANALISTA`, `ESTADO` | Texto, longitud mín/máx, limpieza de espacios |
| `OBSERVACIONES` | Texto opcional, máximo 500 caracteres |
| Duplicados | `SINIESTRO` no puede repetirse dentro del mismo archivo |

### Homologación de columnas

Si el ajustador entrega un archivo con nombres alternativos (ej: `FECHASINIESTRO` en lugar de `FECHA_SINIESTRO`), el sistema los renombra automáticamente usando el diccionario `HOMOLOGACION_COLUMNAS`. Esto reduce rechazos por errores de nombre.

---

## 4. ESTRATEGIA DE SALIDA Y ALMACENAMIENTO

Se generan **tres productos**:

| Archivo | Destino | Uso |
|---|---|---|
| `VALIDOS_...xlsx` | GitHub (carpeta cargas/) | Consumo por Power BI vía Power Automate |
| `ERRORES_...xlsx` | Descarga local del ajustador | El ajustador corrige y recarga |
| Log CSV | Servidor local (`logs/`) | Auditoría interna, opcionalmente en Power BI |

**Los registros rechazados nunca llegan a GitHub.** Solo los registros que pasaron todas las validaciones son enviados al flujo de Power BI.

---

## 5. CAMBIOS REALIZADOS Y POR QUÉ

### 5.1 Corrección de errores de sintaxis
El código original tenía múltiples errores tipográficos (`streamilt`, `YamL`, `Autorization`, `Branch` con mayúscula, token duplicado). Todos fueron corregidos.

### 5.2 Validación de contenido por columna (nuevo)
El código original no validaba el contenido, solo la estructura. Se agregó un motor completo de validación que corre regla por regla, columna por columna, y reporta exactamente qué fila, qué columna y qué regla falló.

### 5.3 Homologación de nombres de columna (nuevo)
En lugar de rechazar al primer intento, el sistema intenta renombrar automáticamente variantes conocidas del nombre de columna antes de reportar error. Esto reduce la fricción para el ajustador.

### 5.4 Resumen de calidad visual (nuevo)
Se agregó un panel con métricas: total de filas, filas válidas, rechazadas, porcentaje de calidad y top columnas con más errores. El ajustador puede priorizar qué corregir primero.

### 5.5 Separación de registros válidos y rechazados (nuevo)
Solo los registros que superan todas las validaciones son enviados a GitHub. Los rechazados se excluyen del envío.

### 5.6 Reporte de errores descargable (nuevo)
Se genera un Excel con dos hojas: los registros fallidos y el detalle de cada error con sugerencia de corrección. El ajustador puede descargarlo, corregir su plantilla y recargar.

### 5.7 Log de auditoría CSV (nuevo)
Cada operación de carga queda registrada: usuario, archivo, timestamp, filas válidas/rechazadas, URL de GitHub y estado de la operación. Puede conectarse a Power BI como tabla de auditoría.

### 5.8 Modularización del código (refactor)
Se separó en 5 archivos con responsabilidades claras. Esto permite modificar las reglas sin tocar la UI, y modificar la UI sin tocar las validaciones.

### 5.9 Control de errores robusto (mejorado)
Se manejan `KeyError` para secrets faltantes, `TimeoutError` en GitHub, `ConnectionError`, archivos vacíos, archivos protegidos y límite de filas. Cada error tiene un mensaje claro para el usuario.

### 5.10 Confirmación antes de enviar (nuevo)
Se agregó un checkbox de confirmación explícita antes del botón de envío, para evitar envíos accidentales.

---

## 6. RECOMENDACIONES ADICIONALES

### Seguridad
- Mueva `cookie_secret` a `st.secrets` en producción. El valor actual en `APP_CONFIG` es solo para desarrollo.
- Restrinja la lista de `ADMINS` en `app.py` a usuarios reales del equipo coordinador.
- No exponga el token de GitHub en logs ni en mensajes de error al usuario.
- Considere agregar límite de tamaño de archivo en la capa de Streamlit (no solo en filas).

### Robustez
- Agregue validación cruzada entre fechas (ej: `FECHA_INFORME_FINAL` no puede ser anterior a `FECHA_SINIESTRO`). Ya existe la estructura para agregarlo en `validators.py`.
- Si el volumen crece, considere procesar el archivo de forma asíncrona con una cola (Celery, Redis Queue) y notificar al ajustador por correo.

### Escalabilidad
- Para agregar una nueva columna: solo añada una entrada en `COLUMN_RULES` en `validation_config.py`.
- Para agregar un nuevo tipo de validación: agregue un validador atómico en `validators.py` y regístrelo en `_despachar_validador()`.
- Para cambiar el destino de almacenamiento (SharePoint, S3, Azure Blob): solo modifique `file_service.py`. El resto del código no cambia.

### Integración con Power BI
- El archivo de salida tiene columnas estables y ordenadas, lo que facilita el modelado.
- Se agrega `_TIMESTAMP_CARGA` en el archivo de válidos para facilitar la carga incremental en Power BI.
- El log de auditoría (`logs/auditoria_cargas.csv`) puede conectarse directamente como fuente en Power BI para reportes de trazabilidad.
- Para carga incremental en el modelo, use `_TIMESTAMP_CARGA` como columna de partición de fecha.

### Control de versiones del esquema
- Si en el futuro cambia la plantilla (columnas nuevas), cambie `COLUMN_RULES` y agregue los alias al `HOMOLOGACION_COLUMNAS`. Las versiones anteriores de archivos seguirán fallando con mensaje claro al ajustador.

---

## 7. CÓMO DESPLEGAR

```bash
# Instalar dependencias
pip install streamlit streamlit-authenticator pandas openpyxl requests pyyaml numpy

# Ejecutar localmente
streamlit run app.py

# Secrets requeridos en .streamlit/secrets.toml
[github]
token  = "ghp_tu_token_aqui"
owner  = "tu_organizacion"
repo   = "nombre_del_repo"
branch = "main"
folder = "cargas"
```

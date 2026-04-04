"""
validation_config.py
====================
Configuración centralizada y parametrizable de las reglas de validación
por columna. Para agregar o modificar reglas, solo edita este archivo.

PARA AJUSTAR AL NEGOCIO:
  - Agrega nuevas columnas en COLUMN_RULES
  - Modifica los valores de catálogos en CATALOGOS
  - Ajusta longitudes, patrones regex o condiciones de obligatoriedad
"""

import re

# ---------------------------------------------------------------------------
# CATÁLOGOS DE VALORES PERMITIDOS
# Modifica estos conjuntos cuando cambien los valores de negocio.
# ---------------------------------------------------------------------------
CATALOGOS = {
    "TIPO_AJUSTE": {"TRADICIONAL", "AGIL"},
    "ESTADO_DOCUMENTO": {"RECIBIDO", "PENDIENTE"},
    "ESTADO_ACTUAL": {"ABIERTO", "CERRADO"},
}

# ---------------------------------------------------------------------------
# PATRONES REGEX REUTILIZABLES
# ---------------------------------------------------------------------------
PATRON_SOLO_DIGITOS = re.compile(r"^\d+$")
PATRON_SINIESTRO_NUMERICO = re.compile(r"^\d{13}$")          # Exactamente 13 dígitos
PATRON_SINIESTRO_BAN = re.compile(r"^BAN\d{10}$")            # BAN + exactamente 10 dígitos
PATRON_POLIZA = re.compile(r"^\d{12}$")                       # Exactamente 12 dígitos
PATRON_RAMO = re.compile(r"^0\d{2}$")                        # 3 dígitos que inician en 0
PATRON_EMAIL = re.compile(r"^[\w\.\+\-]+@[\w\-]+\.[a-zA-Z]{2,}$")

# ---------------------------------------------------------------------------
# FORMATOS DE FECHA ACEPTADOS (en orden de prioridad)
# Se intentará parsear en este orden. El primero que funcione gana.
# ---------------------------------------------------------------------------
FORMATOS_FECHA_ENTRADA = [
    "%d/%m/%Y",   # 31/12/2024  → formato preferido
    "%d-%m-%Y",   # 31-12-2024
    "%Y-%m-%d",   # 2024-12-31  (ISO 8601)
    "%d/%m/%y",   # 31/12/24
    "%d-%m-%y",   # 31-12-24
    "%Y/%m/%d",   # 2024/12/31
]

FORMATO_FECHA_SALIDA = "%d/%m/%Y"   # Formato estándar de salida para Power BI

# ---------------------------------------------------------------------------
# DEFINICIÓN DE REGLAS POR COLUMNA
# Cada entrada es un dict con:
#   required      → bool: si el campo es obligatorio
#   type          → str: "siniestro" | "poliza" | "ramo" | "date" | "numeric"
#                         | "text" | "catalog" | "id" | "email"
#   catalog_key   → str: clave en CATALOGOS (solo para type="catalog")
#   min_len       → int: longitud mínima para campos de texto (opcional)
#   max_len       → int: longitud máxima para campos de texto (opcional)
#   allow_decimal → bool: si se permiten decimales en campos numéricos
#   allow_negative→ bool: si se permiten negativos en campos numéricos
#   min_value     → float: valor mínimo permitido (solo numéricos)
#   description   → str: descripción amigable para mensajes de error
# ---------------------------------------------------------------------------
COLUMN_RULES: dict = {
    # ── Identificadores ─────────────────────────────────────────────────────
    "SINIESTRO_ID": {
        "required": True,
        "type": "siniestro",
        "description": "Número de siniestro (13 dígitos ó BAN + 10 dígitos)",
    },
    "NUMERO_DE_POLIZA": {
        "required": True,
        "type": "poliza",
        "description": "Número de póliza (exactamente 12 dígitos)",
    },
    "RAMO": {
        "required": True,
        "type": "ramo",
        "description": "Código de ramo (3 dígitos, inicia con 0)",
    },
    "NIT/CC": {
        "required": True,
        "type": "id",
        "min_len": 6,
        "max_len": 15,
        "description": "Número de identificación (NIT o CC, solo dígitos)",
    },

    # ── Catálogos ────────────────────────────────────────────────────────────
    "TIPO_AJUSTE": {
        "required": True,
        "type": "catalog",
        "catalog_key": "AJUSTE",
        "description": "Tipo de ajuste (valores permitidos: TRADICIONAL, AGIL)",
    },
    "ESTADO_DOCUMENTO": {
        "required": True,
        "type": "catalog",
        "catalog_key": "ESTADO_DOCUMENTO",
        "description": "Estado del documento (valores permitidos: RECIBIDO, PENDIENTE)",
    },
    "ESTADO_ACTUAL": {
        "required": True,
        "type": "catalog",
        "catalog_key": "ESTADO_ACTUAL",
        "description": "Estado actual del siniestro (valores permitidos: ABIERTO, CERRADO)",
    },

    # ── Fechas ───────────────────────────────────────────────────────────────
    "FECHA_SINIESTRO": {
        "required": True,
        "type": "date",
        "description": "Fecha de ocurrencia del siniestro (dd/mm/yyyy)",
    },
    "FECHA_ASIGNACION": {
        "required": True,
        "type": "date",
        "description": "Fecha de asignación al ajustador (dd/mm/yyyy)",
    },
    "FECHA_PRIMER_CONTACTO": {
        "required": False,
        "type": "date",
        "description": "Fecha de primer contacto con el asegurado (dd/mm/yyyy)",
    },
    "FECHA_INFORME_PRELIMINAR": {
        "required": False,
        "type": "date",
        "description": "Fecha del informe preliminar (dd/mm/yyyy)",
    },
    "FECHA_INFORME_FINAL": {
        "required": False,
        "type": "date",
        "description": "Fecha del informe final (dd/mm/yyyy)",
    },
    "FECHA_ULTIMO_CONTACTO": {
        "required": False,
        "type": "date",
        "description": "Fecha del último contacto (dd/mm/yyyy)",
    },
    "FECHA_ULTIMO_DOCUMENTO": {
        "required": False,
        "type": "date",
        "description": "Fecha del último documento recibido (dd/mm/yyyy)",
    },

    # ── Campos numéricos ─────────────────────────────────────────────────────
    "RESERVA_SUGERIDA": {
        "required": True,
        "type": "numeric",
        "allow_decimal": True,
        "allow_negative": False,
        "min_value": 0.0,
        "description": "Valor de reserva del siniestro (número positivo)",
    },

    # ── Campos de texto ──────────────────────────────────────────────────────
    "NOMBRE_ASEGURADO": {
        "required": True,
        "type": "text",
        "min_len": 2,
        "max_len": 200,
        "description": "Nombre completo del asegurado",
    },
    "ANALISTA_SURA": {
        "required": True,
        "type": "text",
        "min_len": 2,
        "max_len": 100,
        "description": "Nombre del analista responsable",
    },
    "OBSERVACIONES": {
        "required": False,
        "type": "text",
        "min_len": 0,
        "max_len": 500,
        "description": "Observaciones adicionales (campo opcional)",
    },
}

# ---------------------------------------------------------------------------
# COLUMNAS QUE EL SISTEMA INSERTA AUTOMÁTICAMENTE
# Estas columnas son añadidas por la aplicación y NO deben venir en el archivo
# ---------------------------------------------------------------------------
COLUMNAS_SISTEMA = ["FACILITADOR"]

# ---------------------------------------------------------------------------
# COLUMNAS REQUERIDAS EN EL ARCHIVO DEL AJUSTADOR
# (excluye FACILITADOR que se inserta automáticamente)
# ---------------------------------------------------------------------------
COLUMNAS_REQUERIDAS = list(COLUMN_RULES.keys())

# ---------------------------------------------------------------------------
# COLUMNAS FINALES EN EL ARCHIVO DE SALIDA (para Power BI)
# Orden estable y predecible para el modelado del informe
# ---------------------------------------------------------------------------
COLUMNAS_SALIDA = (
    COLUMNAS_SISTEMA
    + COLUMNAS_REQUERIDAS
    + ["_ESTADO_FILA", "_ERRORES_FILA", "_TIMESTAMP_CARGA"]
)

# ---------------------------------------------------------------------------
# NOMBRES HOMOLOGADOS (alias → nombre oficial)
# Si el ajustador entrega columnas con nombres ligeramente distintos,
# el sistema los renombrará automáticamente antes de validar.
# ---------------------------------------------------------------------------
HOMOLOGACION_COLUMNAS: dict = {
    # Variantes comunes de SINIESTRO
    "SINISTRO": "SINIESTRO_ID",
    "NO_SINIESTRO": "SINIESTRO_ID",
    "NUM_SINIESTRO": "SINIESTRO_ID",
    "NUMERO_SINIESTRO": "SINIESTRO_ID",
    # Variantes de NIT/CC
    "NIT": "NIT/CC",
    "CC": "NIT/CC",
    "CEDULA": "NIT/CC",
    "IDENTIFICACION": "NIT/CC",
    # Variantes de fechas
    "FECHASINIESTRO": "FECHA_SINIESTRO",
    "FECHA SINIESTRO": "FECHA_SINIESTRO",
    "FECHA_PRIMER CONTACTO": "FECHA_PRIMER_CONTACTO",
    "FECHA PRIMER CONTACTO": "FECHA_PRIMER_CONTACTO",
    "FECHAPRIMERCONTACTO": "FECHA_PRIMER_CONTACTO",
    "FECHA ASIGNACION": "FECHA_ASIGNACION",
    "FECHAASIGNACION": "FECHA_ASIGNACION",
    "FECHA INFORME PRELIMINAR": "FECHA_INFORME_PRELIMINAR",
    "FECHA INFORME FINAL": "FECHA_INFORME_FINAL",
    "FECHA ULTIMO CONTACTO": "FECHA_ULTIMO_CONTACTO",
    "FECHA ULTIMO DOCUMENTO": "FECHA_ULTIMO_DOCUMENTO",
    "FECHAULTIMOCONTACTO": "FECHA_ULTIMO_CONTACTO",
    "FECHAULTIMOCORRESPONDENCIA": "FECHA_ULTIMO_DOCUMENTO",
    # Variantes de ANALISTA
    "ANALISTA": "ANALISTA",
    "ANALISTa": "ANALISTA",
    "ANALIST": "ANALISTA",
    # Variantes de ESTADO_DOCUMENTO
    "ESTADODOCUMENTO": "ESTADO_DOCUMENTO",
    "ESTADO DOCUMENTO": "ESTADO_DOCUMENTO",
}

# ---------------------------------------------------------------------------
# CONFIGURACIÓN GENERAL DE LA APLICACIÓN
# ---------------------------------------------------------------------------
APP_CONFIG = {
    "titulo": "Portal de Carga para Facilitadores",
    "tipos_archivo_permitidos": ["xlsx"],
    "max_filas": 5000,              # Límite de filas por archivo
    "cookie_expiry_days": 1,
    "cookie_key": "validador_ajustadores",
    "cookie_secret": "clave_secreta_123",  # ← En producción: usar st.secrets
}

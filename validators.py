"""
validators.py
=============
Motor de validación modular. Contiene:
  - Validadores atómicos por tipo de campo
  - Motor principal que recorre el DataFrame y aplica reglas
  - Generación del reporte de calidad

Diseño: cada validador recibe un valor crudo y devuelve
(valor_limpio, error_str | None). Si error_str es None, el valor pasó.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

import numpy as np
import pandas as pd

from validation_config import (
    CATALOGOS,
    COLUMN_RULES,
    COLUMNAS_REQUERIDAS,
    COLUMNAS_SISTEMA,
    FORMATOS_FECHA_ENTRADA,
    FORMATO_FECHA_SALIDA,
    HOMOLOGACION_COLUMNAS,
    PATRON_EMAIL,
    PATRON_POLIZA,
    PATRON_RAMO,
    PATRON_SINIESTRO_NUMERICO,
    PATRON_SINIESTRO_BAN,
    PATRON_SOLO_DIGITOS,
)

# ---------------------------------------------------------------------------
# TIPOS DE SEVERIDAD
# ---------------------------------------------------------------------------
CRITICO = "CRÍTICO"      # Bloquea la carga de esa fila
ADVERTENCIA = "ADVERTENCIA"  # Informa pero no bloquea


# ---------------------------------------------------------------------------
# VALIDADORES ATÓMICOS
# Cada función recibe el valor crudo y devuelve (valor_limpio, mensaje_error)
# mensaje_error = None → pasó la validación
# ---------------------------------------------------------------------------

def _es_vacio(valor: Any) -> bool:
    """Determina si un valor es considerado vacío/nulo."""
    if valor is None:
        return True
    if isinstance(valor, float) and np.isnan(valor):
        return True
    if isinstance(valor, str) and valor.strip() == "":
        return True
    return False


def validar_siniestro(valor: Any) -> tuple[Any, Optional[str]]:
    """
    Reglas:
      - No puede estar vacío.
      - Debe ser exactamente 8 dígitos  OR  "SAN" + exactamente 5 dígitos.
      - No se permiten espacios, caracteres especiales ni letras extra.
    """
    if _es_vacio(valor):
        return None, "El número de siniestro es obligatorio y viene vacío."

    v = str(valor).strip().upper()

    if PATRON_SINIESTRO_NUMERICO.match(v):
        return v, None

    if PATRON_SINIESTRO_BAN.match(v):
        return v, None

    # Dar un mensaje específico según el patrón incorrecto
    if v.startswith("BAN"):
        digitos_ban = v[3:]
        if not PATRON_SOLO_DIGITOS.match(digitos_ban):
            return v, (
                f"El siniestro '{v}' tiene el prefijo BAN pero contiene "
                "caracteres no numéricos después del prefijo."
            )
        return v, (
            f"El siniestro '{v}' tiene el prefijo BAN pero debe ir seguido "
            f"de exactamente 10 dígitos (recibidos: {len(digitos_ban)})."
        )

    if re.search(r"[A-Za-z]", v):
        return v, (
            f"El siniestro '{v}' contiene letras. Solo se permite el prefijo "
            "BAN (mayúscula) seguido de 10 dígitos, o exactamente 13 dígitos."
        )

    if not PATRON_SOLO_DIGITOS.match(v):
        return v, (
            f"El siniestro '{v}' contiene caracteres especiales o espacios. "
            "Solo se permiten dígitos o el formato BAN#####."
        )

    return v, (
        f"El siniestro '{v}' no cumple el formato esperado. "
        f"Debe tener exactamente 13 dígitos (recibidos: {len(v)}) "
        "o el formato BAN##### (BAN + 10 dígitos)."
    )


def validar_poliza(valor: Any) -> tuple[Any, Optional[str]]:
    """
    Reglas:
      - No puede estar vacío.
      - Debe tener exactamente 12 dígitos.
      - No se permiten letras, espacios ni caracteres especiales.
    """
    if _es_vacio(valor):
        return None, "El número de póliza es obligatorio y viene vacío."

    v = str(valor).strip()

    # Eliminar ceros a la izquierda solo si viene como número flotante (ej: 123456789.0)
    if re.match(r"^\d+\.0$", v):
        v = v[:-2]

    if PATRON_POLIZA.match(v):
        return v, None

    if not PATRON_SOLO_DIGITOS.match(v):
        return v, (
            f"La póliza '{v}' contiene caracteres no permitidos. "
            "Solo se aceptan dígitos (sin letras, espacios ni símbolos)."
        )

    return v, (
        f"La póliza '{v}' debe tener exactamente 9 dígitos (recibidos: {len(v)})."
    )


def validar_ramo(valor: Any) -> tuple[Any, Optional[str]]:
    """
    Reglas:
      - No puede estar vacío.
      - Debe tener exactamente 3 dígitos.
      - Debe comenzar con el dígito '0'.
      - No se permiten letras, espacios ni caracteres especiales.
    """
    if _es_vacio(valor):
        return None, "El código de ramo es obligatorio y viene vacío."

    v = str(valor).strip()

    # Normalizar formato numérico con ceros (ej: 12 → 012)
    if PATRON_SOLO_DIGITOS.match(v) and len(v) <= 3:
        v = v.zfill(3)

    if PATRON_RAMO.match(v):
        return v, None

    if not PATRON_SOLO_DIGITOS.match(v):
        return v, (
            f"El ramo '{v}' contiene caracteres no permitidos. "
            "Solo se aceptan dígitos."
        )

    if len(v) != 3:
        return v, (
            f"El ramo '{v}' debe tener exactamente 3 dígitos (recibidos: {len(v)})."
        )

    return v, (
        f"El ramo '{v}' debe comenzar con el dígito '0' (ej: 012, 034)."
    )


def validar_fecha(valor: Any, nombre_columna: str) -> tuple[Any, Optional[str]]:
    """
    Reglas:
      - Intenta parsear el valor con múltiples formatos.
      - Convierte al formato estándar de salida (dd/mm/yyyy).
      - Rechaza fechas imposibles o claramente erróneas.
      - No valida vacío aquí; eso lo maneja el motor principal según 'required'.
    """
    if _es_vacio(valor):
        return None, None  # El motor principal decide si es error según obligatoriedad

    # Si pandas ya lo convirtió a datetime
    if isinstance(valor, (datetime, pd.Timestamp)):
        dt = pd.Timestamp(valor)
        if pd.isnull(dt):
            return None, f"La fecha en '{nombre_columna}' no es válida."
        return dt.strftime(FORMATO_FECHA_SALIDA), None

    v = str(valor).strip()

    for fmt in FORMATOS_FECHA_ENTRADA:
        try:
            dt = datetime.strptime(v, fmt)
            # Sanity check: años razonables
            if dt.year < 1990 or dt.year > 2099:
                return v, (
                    f"La fecha '{v}' en '{nombre_columna}' tiene un año fuera "
                    f"del rango permitido (1990–2099)."
                )
            return dt.strftime(FORMATO_FECHA_SALIDA), None
        except ValueError:
            continue

    return v, (
        f"La fecha '{v}' en '{nombre_columna}' no tiene un formato reconocido. "
        f"Use el formato dd/mm/yyyy (ej: 31/12/2024)."
    )


def validar_numerico(
    valor: Any,
    nombre_columna: str,
    allow_decimal: bool = True,
    allow_negative: bool = False,
    min_value: Optional[float] = None,
) -> tuple[Any, Optional[str]]:
    """
    Reglas:
      - Debe convertirse a número válido.
      - Controla negativos y decimales según configuración.
      - Rechaza texto, símbolos y valores inconsistentes.
    """
    if _es_vacio(valor):
        return None, None  # El motor principal decide si es error según obligatoriedad

    v_str = str(valor).strip()

    # Limpiar formato moneda común (ej: $1.234,56 o 1,234.56)
    v_limpio = v_str.replace("$", "").replace(" ", "")

    # Detectar si usa coma como separador decimal o de miles
    if re.match(r"^\d{1,3}(\.\d{3})*(,\d+)?$", v_limpio):
        # Formato europeo: 1.234,56
        v_limpio = v_limpio.replace(".", "").replace(",", ".")
    elif re.match(r"^\d{1,3}(,\d{3})*(\.\d+)?$", v_limpio):
        # Formato americano: 1,234.56
        v_limpio = v_limpio.replace(",", "")

    try:
        numero = float(v_limpio)
    except ValueError:
        return v_str, (
            f"El valor '{v_str}' en '{nombre_columna}' no es un número válido. "
            "Elimine letras, símbolos o caracteres especiales."
        )

    if not allow_negative and numero < 0:
        return v_str, (
            f"El valor '{v_str}' en '{nombre_columna}' no puede ser negativo."
        )

    if min_value is not None and numero < min_value:
        return v_str, (
            f"El valor '{v_str}' en '{nombre_columna}' es menor que el mínimo "
            f"permitido ({min_value})."
        )

    if not allow_decimal and numero != int(numero):
        return v_str, (
            f"El valor '{v_str}' en '{nombre_columna}' no permite decimales."
        )

    return (int(numero) if not allow_decimal else round(numero, 2)), None


def validar_texto(
    valor: Any,
    nombre_columna: str,
    min_len: int = 0,
    max_len: int = 500,
) -> tuple[Any, Optional[str]]:
    """
    Reglas:
      - Limpia espacios al inicio y al final.
      - Valida longitud mínima y máxima.
    """
    if _es_vacio(valor):
        return None, None

    v = str(valor).strip()

    if min_len > 0 and len(v) < min_len:
        return v, (
            f"El campo '{nombre_columna}' es demasiado corto "
            f"(mínimo {min_len} caracteres, recibidos: {len(v)})."
        )

    if max_len and len(v) > max_len:
        return v[:max_len], (
            f"El campo '{nombre_columna}' excede el límite de {max_len} caracteres "
            f"(recibidos: {len(v)}). El valor fue truncado."
        )

    return v, None


def validar_catalogo(
    valor: Any,
    nombre_columna: str,
    catalog_key: str,
) -> tuple[Any, Optional[str]]:
    """
    Reglas:
      - El valor debe estar exactamente en el catálogo (insensible a mayúsculas).
      - Devuelve el valor normalizado a mayúsculas.
    """
    if _es_vacio(valor):
        return None, None

    v = str(valor).strip().upper()
    valores_permitidos = CATALOGOS.get(catalog_key, set())

    if v in valores_permitidos:
        return v, None

    return v, (
        f"El valor '{v}' en '{nombre_columna}' no es válido. "
        f"Valores permitidos: {sorted(valores_permitidos)}."
    )


def validar_identificacion(
    valor: Any,
    nombre_columna: str,
    min_len: int = 6,
    max_len: int = 15,
) -> tuple[Any, Optional[str]]:
    """
    Reglas:
      - Solo dígitos.
      - Longitud entre min_len y max_len.
    """
    if _es_vacio(valor):
        return None, None

    v = str(valor).strip()

    # Limpiar puntos y guiones comunes en NIT (ej: 900.123.456-7)
    v_limpio = re.sub(r"[\.\-]", "", v)

    if not PATRON_SOLO_DIGITOS.match(v_limpio):
        return v, (
            f"El campo '{nombre_columna}' debe contener solo dígitos. "
            f"Valor recibido: '{v}'."
        )

    if len(v_limpio) < min_len or len(v_limpio) > max_len:
        return v, (
            f"El campo '{nombre_columna}' debe tener entre {min_len} y {max_len} "
            f"dígitos (recibidos: {len(v_limpio)})."
        )

    return v_limpio, None


def validar_email(valor: Any, nombre_columna: str) -> tuple[Any, Optional[str]]:
    """Valida formato de correo electrónico."""
    if _es_vacio(valor):
        return None, None

    v = str(valor).strip().lower()

    if PATRON_EMAIL.match(v):
        return v, None

    return v, (
        f"El correo '{v}' en '{nombre_columna}' no tiene un formato válido "
        "(ej: nombre@dominio.com)."
    )


# ---------------------------------------------------------------------------
# DESPACHADOR: selecciona el validador correcto según el tipo de campo
# ---------------------------------------------------------------------------
def _despachar_validador(valor: Any, col: str, regla: dict) -> tuple[Any, Optional[str]]:
    """Selecciona y ejecuta el validador correspondiente al tipo de campo."""
    tipo = regla.get("type", "text")

    if tipo == "siniestro":
        return validar_siniestro(valor)

    if tipo == "poliza":
        return validar_poliza(valor)

    if tipo == "ramo":
        return validar_ramo(valor)

    if tipo == "date":
        return validar_fecha(valor, col)

    if tipo == "numeric":
        return validar_numerico(
            valor,
            col,
            allow_decimal=regla.get("allow_decimal", True),
            allow_negative=regla.get("allow_negative", False),
            min_value=regla.get("min_value"),
        )

    if tipo == "catalog":
        return validar_catalogo(valor, col, regla["catalog_key"])

    if tipo == "id":
        return validar_identificacion(
            valor,
            col,
            min_len=regla.get("min_len", 6),
            max_len=regla.get("max_len", 15),
        )

    if tipo == "email":
        return validar_email(valor, col)

    # Por defecto: texto
    return validar_texto(
        valor,
        col,
        min_len=regla.get("min_len", 0),
        max_len=regla.get("max_len", 500),
    )


# ---------------------------------------------------------------------------
# VALIDACIÓN DE ESTRUCTURA DEL ARCHIVO
# ---------------------------------------------------------------------------
def validar_estructura(df: pd.DataFrame) -> dict:
    """
    Verifica que el DataFrame tenga exactamente las columnas requeridas.
    Aplica homologación de nombres antes de comparar.

    Retorna un dict con:
      ok           → bool
      faltantes    → list[str]
      sobrantes    → list[str]
      renombradas  → dict[str_original → str_oficial]
      df_homologado→ DataFrame con columnas renombradas
    """
    # 1. Normalizar: strip + upper en nombres de columnas
    mapa_normalizacion = {
        col: col.strip().upper() for col in df.columns
    }
    df_norm = df.rename(columns=mapa_normalizacion)

    # 2. Aplicar homologación (alias → nombre oficial)
    mapa_homologacion = {}
    for col in df_norm.columns:
        if col in HOMOLOGACION_COLUMNAS:
            mapa_homologacion[col] = HOMOLOGACION_COLUMNAS[col]

    df_hom = df_norm.rename(columns=mapa_homologacion)
    renombradas = {k: v for k, v in mapa_normalizacion.items()
                  if k != mapa_normalizacion[k]}
    renombradas.update(mapa_homologacion)

    # 3. Ignorar columnas de sistema que se insertan automáticamente
    columnas_presentes = [c for c in df_hom.columns if c not in COLUMNAS_SISTEMA]

    faltantes = [c for c in COLUMNAS_REQUERIDAS if c not in columnas_presentes]
    sobrantes = [c for c in columnas_presentes if c not in COLUMNAS_REQUERIDAS]

    return {
        "ok": len(faltantes) == 0 and len(sobrantes) == 0,
        "faltantes": faltantes,
        "sobrantes": sobrantes,
        "renombradas": renombradas,
        "df_homologado": df_hom,
    }


# ---------------------------------------------------------------------------
# MOTOR PRINCIPAL DE VALIDACIÓN POR FILAS Y COLUMNAS
# ---------------------------------------------------------------------------
def validar_dataframe(df: pd.DataFrame) -> dict:
    """
    Recorre el DataFrame fila por fila, columna por columna, y aplica
    las reglas definidas en COLUMN_RULES.

    Retorna un dict con:
      df_validado     → DataFrame con valores limpios + columnas de estado
      df_validos      → Solo filas sin errores críticos
      df_rechazados   → Solo filas con al menos un error crítico
      errores         → list[dict] con detalle de cada error
      resumen         → dict con métricas de calidad
    """
    timestamp_carga = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    df_work = df.copy()

    # Convertir todas las columnas a object para evitar TypeError en pandas
    # Cuando se asigna None o texto a columnas numericas o de fechas
    df

    # Registros de errores por fila
    errores_por_fila: dict[int, list[str]] = {}   # fila_excel → [mensajes]

    # Contadores por columna para el resumen
    conteo_errores_columna: dict[str, int] = {col: 0 for col in COLUMNAS_REQUERIDAS}

    # Detalle completo de errores (para mostrar en UI)
    lista_errores: list[dict] = []

    for col in COLUMNAS_REQUERIDAS:
        if col not in df_work.columns:
            continue  # Las faltantes ya se manejaron en validar_estructura

        regla = COLUMN_RULES.get(col, {})
        required = regla.get("required", False)

        for idx in df_work.index:
            valor_raw = df_work.at[idx, col]
            fila_excel = idx + 2  # +2 porque idx=0 es fila 2 en Excel (fila 1 = encabezado)

            # ── Verificar obligatoriedad ──────────────────────────────────
            if required and _es_vacio(valor_raw):
                mensaje = (
                    f"El campo '{col}' es obligatorio y viene vacío. "
                    f"→ {regla.get('description', '')}"
                )
                _registrar_error(lista_errores, errores_por_fila, conteo_errores_columna,
                                 fila_excel, col, mensaje, CRITICO)
                df_work.at[idx, col] = None
                continue

            # ── Ejecutar validador ────────────────────────────────────────
            valor_limpio, error = _despachar_validador(valor_raw, col, regla)

            if error:
                _registrar_error(lista_errores, errores_por_fila, conteo_errores_columna,
                                 fila_excel, col, error, CRITICO)
                df_work.at[idx, col] = valor_limpio  # guardar lo que se limpió aunque haya error
            else:
                df_work.at[idx, col] = valor_limpio  # valor limpio y normalizado

    # ── Validación de duplicados en SINIESTRO ────────────────────────────────
    if "SINIESTRO" in df_work.columns:
        siniestros = df_work["SINIESTRO"].dropna().astype(str)
        duplicados = siniestros[siniestros.duplicated(keep=False)]
        for idx in duplicados.index:
            fila_excel = idx + 2
            val = df_work.at[idx, "SINIESTRO"]
            mensaje = (
                f"El número de siniestro '{val}' aparece duplicado en el archivo. "
                "Cada siniestro debe ser único por carga."
            )
            _registrar_error(lista_errores, errores_por_fila, conteo_errores_columna,
                             fila_excel, "SINIESTRO", mensaje, CRITICO)

    # ── Agregar columnas de estado al DataFrame ──────────────────────────────
    df_work["_ESTADO_FILA"] = df_work.index.map(
        lambda i: "RECHAZADO" if (i + 2) in errores_por_fila else "VÁLIDO"
    )
    df_work["_ERRORES_FILA"] = df_work.index.map(
        lambda i: " | ".join(errores_por_fila.get(i + 2, []))
    )
    df_work["_TIMESTAMP_CARGA"] = timestamp_carga
    # Mes de reporte generado automáticamente por el sistema (YYYY-MM).
    # El ajustador NO lo llena. Sirve para deduplicación y análisis histórico en Power BI.
    df_work["_MES_REPORTE"] = datetime.now().strftime("%Y-%m")

    # ── Separar válidos de rechazados ────────────────────────────────────────
    df_validos = df_work[df_work["_ESTADO_FILA"] == "VÁLIDO"].copy()
    df_rechazados = df_work[df_work["_ESTADO_FILA"] == "RECHAZADO"].copy()

    # ── Resumen de calidad ───────────────────────────────────────────────────
    total_filas = len(df_work)
    filas_validas = len(df_validos)
    filas_rechazadas = len(df_rechazados)

    top_columnas_error = sorted(
        conteo_errores_columna.items(),
        key=lambda x: x[1],
        reverse=True
    )
    top_columnas_error = [(col, cnt) for col, cnt in top_columnas_error if cnt > 0]

    resumen = {
        "total_filas": total_filas,
        "filas_validas": filas_validas,
        "filas_rechazadas": filas_rechazadas,
        "total_errores": len(lista_errores),
        "porcentaje_calidad": round((filas_validas / total_filas * 100), 1) if total_filas else 0,
        "columnas_con_mas_errores": top_columnas_error[:5],
        "timestamp": timestamp_carga,
    }

    return {
        "df_validado": df_work,
        "df_validos": df_validos,
        "df_rechazados": df_rechazados,
        "errores": lista_errores,
        "resumen": resumen,
    }


# ---------------------------------------------------------------------------
# HELPER PRIVADO
# ---------------------------------------------------------------------------
def _registrar_error(
    lista_errores: list,
    errores_por_fila: dict,
    conteo_columna: dict,
    fila_excel: int,
    columna: str,
    mensaje: str,
    severidad: str,
) -> None:
    lista_errores.append({
        "fila": fila_excel,
        "columna": columna,
        "mensaje": mensaje,
        "severidad": severidad,
    })
    errores_por_fila.setdefault(fila_excel, []).append(f"[{columna}] {mensaje}")
    if columna in conteo_columna:
        conteo_columna[columna] += 1

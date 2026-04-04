"""
audit_logger.py
===============
Módulo de trazabilidad y auditoría.

Registra en un archivo de log local (y opcionalmente en GitHub) cada
operación de carga: quién cargó, qué archivo, cuándo, cuántas filas
válidas/rechazadas, y cualquier error de sistema.

El log se almacena en formato CSV para que también pueda conectarse a Power BI
como tabla de auditoría.
"""

from __future__ import annotations

import csv
import io
import os
from datetime import datetime
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# CONFIGURACIÓN DEL LOG
# ---------------------------------------------------------------------------
LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "auditoria_cargas.csv"

LOG_COLUMNS = [
    "timestamp",
    "usuario",
    "nombre_archivo_original",
    "nombre_archivo_guardado",
    "total_filas",
    "filas_validas",
    "filas_rechazadas",
    "total_errores",
    "porcentaje_calidad",
    "url_github",
    "estado_operacion",   # EXITOSO | FALLIDO | PARCIAL
    "mensaje_sistema",
]


# ---------------------------------------------------------------------------
# FUNCIONES PÚBLICAS
# ---------------------------------------------------------------------------

def registrar_carga(
    usuario: str,
    nombre_archivo_original: str,
    nombre_archivo_guardado: str,
    resumen: dict,
    url_github: str = "",
    estado_operacion: str = "EXITOSO",
    mensaje_sistema: str = "",
) -> None:
    """
    Registra una operación de carga en el archivo de auditoría CSV.

    Parámetros:
      usuario                  → nombre del usuario autenticado
      nombre_archivo_original  → nombre del archivo subido por el ajustador
      nombre_archivo_guardado  → nombre final con timestamp
      resumen                  → dict devuelto por validar_dataframe()
      url_github               → URL del archivo en GitHub (si aplica)
      estado_operacion         → "EXITOSO", "FALLIDO" o "PARCIAL"
      mensaje_sistema          → texto libre para errores de sistema
    """
    _asegurar_directorio()

    registro = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "usuario": usuario,
        "nombre_archivo_original": nombre_archivo_original,
        "nombre_archivo_guardado": nombre_archivo_guardado,
        "total_filas": resumen.get("total_filas", 0),
        "filas_validas": resumen.get("filas_validas", 0),
        "filas_rechazadas": resumen.get("filas_rechazadas", 0),
        "total_errores": resumen.get("total_errores", 0),
        "porcentaje_calidad": resumen.get("porcentaje_calidad", 0),
        "url_github": url_github,
        "estado_operacion": estado_operacion,
        "mensaje_sistema": mensaje_sistema,
    }

    try:
        file_exists = LOG_FILE.exists()
        with open(LOG_FILE, mode="a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=LOG_COLUMNS)
            if not file_exists:
                writer.writeheader()
            writer.writerow(registro)
    except Exception as e:
        # El log nunca debe romper el flujo principal
        print(f"[AUDIT WARNING] No se pudo escribir el log: {e}")


def registrar_error_sistema(
    usuario: str,
    nombre_archivo: str,
    error: str,
) -> None:
    """
    Registra un error de sistema (no de validación) en el log de auditoría.
    Útil para rastrear fallos inesperados en producción.
    """
    registrar_carga(
        usuario=usuario,
        nombre_archivo_original=nombre_archivo,
        nombre_archivo_guardado="",
        resumen={"total_filas": 0, "filas_validas": 0, "filas_rechazadas": 0,
                 "total_errores": 0, "porcentaje_calidad": 0},
        estado_operacion="FALLIDO",
        mensaje_sistema=str(error)[:500],
    )


def obtener_log_como_bytes() -> bytes:
    """
    Lee el log de auditoría y lo devuelve como bytes para descarga desde Streamlit.
    Retorna bytes vacíos si el log no existe.
    """
    if not LOG_FILE.exists():
        return b""
    return LOG_FILE.read_bytes()


def obtener_log_como_dataframe():
    """
    Carga el log de auditoría como DataFrame para visualización en Streamlit.
    """
    import pandas as pd

    if not LOG_FILE.exists():
        return pd.DataFrame(columns=LOG_COLUMNS)

    try:
        return pd.read_csv(LOG_FILE, encoding="utf-8")
    except Exception:
        return pd.DataFrame(columns=LOG_COLUMNS)


# ---------------------------------------------------------------------------
# HELPERS PRIVADOS
# ---------------------------------------------------------------------------

def _asegurar_directorio() -> None:
    """Crea el directorio de logs si no existe."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

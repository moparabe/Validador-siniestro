"""
app.py
======
Portal de Carga para Facilitadores — Versión de Producción
Aplicativo Streamlit refactorizado con enfoque empresarial.

Estructura de capas:
  app.py              → Interfaz de usuario (Streamlit UI)
  validators.py       → Motor de validación y reglas de negocio
  validation_config.py→ Parámetros y catálogos configurables
  file_service.py     → Lectura, escritura y subida de archivos
  audit_logger.py     → Trazabilidad y registro de operaciones

Ejecución:
  streamlit run app.py
"""

import streamlit as st
import pandas as pd
from datetime import datetime

# ── Importaciones del proyecto ───────────────────────────────────────────────
from validation_config import APP_CONFIG, COLUMNAS_REQUERIDAS, COLUMN_RULES
from validators import validar_estructura, validar_dataframe
from file_service import (
    construir_nombre_archivo,
    generar_excel_completo,
    generar_excel_reporte_errores,
    generar_excel_validos,
    leer_excel,
    subir_a_github,
)
from audit_logger import (
    obtener_log_como_dataframe,
    obtener_log_como_bytes,
    registrar_carga,
    registrar_error_sistema,
)

# ── Autenticación ─────────────────────────────────────────────────────────────
try:
    import streamlit_authenticator as stauth
    import yaml
    from yaml.loader import SafeLoader
    from usuarios import credentials

    _AUTH_DISPONIBLE = True
except ImportError:
    _AUTH_DISPONIBLE = False


# =============================================================================
# 1. CONFIGURACIÓN DE PÁGINA (debe ser lo primero)
# =============================================================================
st.set_page_config(
    page_title=APP_CONFIG["titulo"],
    page_icon="🛡️",
    layout="centered",
    initial_sidebar_state="expanded",
)


# =============================================================================
# 2. ESTILOS CSS PERSONALIZADOS
# =============================================================================
st.markdown("""
<style>
    .metric-card {
        background: #f0f4f8;
        border-radius: 8px;
        padding: 12px 16px;
        text-align: center;
        border-left: 4px solid #2E75B6;
    }
    .error-row {
        background-color: #fff0f0;
        border-left: 3px solid #e53935;
        padding: 6px 10px;
        margin: 4px 0;
        border-radius: 4px;
        font-size: 0.9em;
    }
    .warning-row {
        background-color: #fff8e1;
        border-left: 3px solid #f9a825;
        padding: 6px 10px;
        margin: 4px 0;
        border-radius: 4px;
        font-size: 0.9em;
    }
    .success-banner {
        background: #e8f5e9;
        border: 1px solid #43a047;
        border-radius: 6px;
        padding: 12px;
        text-align: center;
    }
    div[data-testid="stExpander"] summary {font-weight: 600;}
</style>
""", unsafe_allow_html=True)


# =============================================================================
# 3. SISTEMA DE AUTENTICACIÓN
# =============================================================================
def configurar_autenticacion():
    """Inicializa el autenticador. Retorna (autenticator, status, name, username)."""
    if not _AUTH_DISPONIBLE:
        # Modo sin autenticación (desarrollo local)
        st.warning("⚠️ Módulo de autenticación no encontrado. Ejecutando en modo sin login.")
        return None, True, "Desarrollador", "dev"

    autenticator = stauth.Authenticate(
        credentials,
        APP_CONFIG["cookie_key"],
        APP_CONFIG["cookie_secret"],
        cookie_expiry_days=APP_CONFIG["cookie_expiry_days"],
    )
    autenticator.login()

    status = st.session_state.get("authentication_status")
    name = st.session_state.get("name", "")
    username = st.session_state.get("username", "")
    return autenticator, status, name, username


# =============================================================================
# 4. COMPONENTES DE UI REUTILIZABLES
# =============================================================================

def mostrar_resumen_calidad(resumen: dict) -> None:
    """Muestra el panel de métricas de calidad del archivo cargado."""
    st.subheader("📊 Resumen de Calidad")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total de filas", f"{resumen['total_filas']:,}")
    col2.metric(
        "✅ Filas válidas",
        f"{resumen['filas_validas']:,}",
        delta=f"{resumen['porcentaje_calidad']}%",
        delta_color="normal",
    )
    col3.metric(
        "❌ Filas rechazadas",
        f"{resumen['filas_rechazadas']:,}",
        delta_color="inverse",
    )
    col4.metric("⚠️ Total errores", f"{resumen['total_errores']:,}")

    # Barra de calidad
    calidad = resumen["porcentaje_calidad"]
    color = "#43a047" if calidad == 100 else "#f9a825" if calidad >= 70 else "#e53935"
    st.markdown(
        f"""
        <div style="margin:8px 0">
            <div style="font-size:0.85em;color:#555">Índice de calidad del archivo</div>
            <div style="background:#e0e0e0;border-radius:4px;height:14px;margin-top:4px">
                <div style="width:{calidad}%;background:{color};height:14px;border-radius:4px;
                            transition:width 0.5s"></div>
            </div>
            <div style="font-size:0.9em;color:{color};font-weight:bold;text-align:right">
                {calidad}% limpio
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # Top columnas con errores
    if resumen["columnas_con_mas_errores"]:
        st.markdown("**Columnas con más inconsistencias:**")
        for col_name, count in resumen["columnas_con_mas_errores"]:
            descripcion = COLUMN_RULES.get(col_name, {}).get("description", col_name)
            st.markdown(
                f'<div class="warning-row">📌 <b>{col_name}</b>: {count} error(es) — {descripcion}</div>',
                unsafe_allow_html=True,
            )


def mostrar_detalle_errores(errores: list[dict]) -> None:
    """Muestra el panel de errores detallados por fila y columna."""
    if not errores:
        return

    st.subheader("🔍 Detalle de Errores por Fila")
    st.caption(
        "Corrija los errores en su plantilla y vuelva a cargar el archivo. "
        "Puede descargar el reporte de errores al final de esta página."
    )

    # Agrupar por fila para mejor legibilidad
    errores_por_fila: dict[int, list] = {}
    for e in errores:
        errores_por_fila.setdefault(e["fila"], []).append(e)

    # Mostrar primeras 50 filas con error para no saturar la UI
    MAX_FILAS_MOSTRAR = 50
    filas_mostradas = 0

    for fila, lista in sorted(errores_por_fila.items()):
        if filas_mostradas >= MAX_FILAS_MOSTRAR:
            restantes = len(errores_por_fila) - MAX_FILAS_MOSTRAR
            st.info(
                f"Se muestran los primeros {MAX_FILAS_MOSTRAR} registros con error. "
                f"Hay {restantes} registros adicionales con errores. "
                "Descargue el reporte completo para ver todos."
            )
            break

        with st.expander(f"📄 Fila {fila} — {len(lista)} error(es)", expanded=False):
            for e in lista:
                css_class = "error-row" if e["severidad"] == "CRÍTICO" else "warning-row"
                icono = "❌" if e["severidad"] == "CRÍTICO" else "⚠️"
                st.markdown(
                    f'<div class="{css_class}">'
                    f'{icono} <b>Columna:</b> {e["columna"]} &nbsp;|&nbsp; '
                    f'<b>Problema:</b> {e["mensaje"]}'
                    f'</div>',
                    unsafe_allow_html=True,
                )
        filas_mostradas += 1


def mostrar_plantilla_referencia() -> None:
    """Muestra en el sidebar la guía de la plantilla esperada."""
    with st.sidebar.expander("📋 Guía de columnas requeridas", expanded=False):
        for col, regla in COLUMN_RULES.items():
            obligatorio = "🔴 Obligatorio" if regla.get("required") else "🟡 Opcional"
            st.markdown(f"**{col}**  \n_{regla.get('description', '')}_ · {obligatorio}")


def mostrar_seccion_descarga(
    df_validos: pd.DataFrame,
    df_rechazados: pd.DataFrame,
    lista_errores: list[dict],
    nombre_usuario: str,
    nombre_archivo: str,
) -> None:
    """Muestra los botones de descarga de archivos generados."""
    st.markdown("---")
    st.subheader("📥 Descargar Reportes")

    col_a, col_b = st.columns(2)

    # Descarga: solo válidos
    if not df_validos.empty:
        with col_a:
            bytes_validos = generar_excel_validos(df_validos, nombre_usuario)
            nombre_validos = construir_nombre_archivo(nombre_archivo, nombre_usuario, "VALIDOS")
            st.download_button(
                label="✅ Descargar registros válidos",
                data=bytes_validos,
                file_name=nombre_validos,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="Archivo limpio listo para Power BI. Solo contiene filas sin errores.",
            )

    # Descarga: reporte de errores
    if lista_errores:
        with col_b:
            bytes_errores = generar_excel_reporte_errores(
                df_rechazados, lista_errores, nombre_usuario
            )
            nombre_errores = construir_nombre_archivo(nombre_archivo, nombre_usuario, "ERRORES")
            st.download_button(
                label="❌ Descargar reporte de errores",
                data=bytes_errores,
                file_name=nombre_errores,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="Contiene las filas con errores y la descripción de cada problema.",
            )


# =============================================================================
# 5. LÓGICA PRINCIPAL DE CARGA Y VALIDACIÓN
# =============================================================================

def procesar_archivo(archivo_subido, nombre_usuario: str, username: str) -> None:
    """
    Orquesta el flujo completo:
    1. Leer el archivo
    2. Validar estructura
    3. Validar contenido por columna
    4. Mostrar resultados
    5. Permitir envío si pasa las validaciones
    """

    # ── Paso 1: Leer el archivo ──────────────────────────────────────────────
    archivo_subido.seek(0)
    contenido_bytes = archivo_subido.read()

    df_raw, error_lectura = leer_excel(contenido_bytes, max_filas=APP_CONFIG["max_filas"])
    if error_lectura:
        st.error(f"❌ **Error al leer el archivo:** {error_lectura}")
        registrar_error_sistema(username, archivo_subido.name, error_lectura)
        return

    # ── Paso 2: Insertar columna FACILITADOR ────────────────────────────────
    df_raw.insert(0, "FACILITADOR", nombre_usuario)

    # ── Paso 3: Validar estructura ───────────────────────────────────────────
    resultado_estructura = validar_estructura(df_raw)

    if resultado_estructura["renombradas"]:
        renombradas = resultado_estructura["renombradas"]
        st.info(
            f"ℹ️ Se renombraron automáticamente {len(renombradas)} columna(s) para "
            f"coincidir con la plantilla: {renombradas}"
        )

    if not resultado_estructura["ok"]:
        st.error("❌ **El archivo no tiene la estructura correcta. No se puede procesar.**")

        faltantes = resultado_estructura["faltantes"]
        sobrantes = resultado_estructura["sobrantes"]

        if faltantes:
            st.markdown(
                "**Columnas que faltan en el archivo:**\n"
                + "\n".join(f"- `{c}`" for c in faltantes)
            )
        if sobrantes:
            st.markdown(
                "**Columnas adicionales no permitidas:**\n"
                + "\n".join(f"- `{c}`" for c in sobrantes)
                + "\n\n_Elimine estas columnas de su archivo antes de cargar._"
            )

        st.info(
            "📌 **Columnas esperadas (en cualquier orden):**\n"
            + "  |  ".join(f"`{c}`" for c in COLUMNAS_REQUERIDAS)
        )
        return

    st.success("✅ Estructura del archivo correcta. Procesando validaciones de contenido…")
    df_homologado = resultado_estructura["df_homologado"]

    # ── Paso 4: Vista previa ─────────────────────────────────────────────────
    with st.expander("👁️ Vista previa del archivo (primeras 5 filas)", expanded=False):
        st.dataframe(df_homologado.head(), use_container_width=True)

    # ── Paso 5: Validar contenido ────────────────────────────────────────────
    with st.spinner("Validando calidad de los datos…"):
        resultado_validacion = validar_dataframe(df_homologado)

    resumen = resultado_validacion["resumen"]
    errores = resultado_validacion["errores"]
    df_validos = resultado_validacion["df_validos"]
    df_rechazados = resultado_validacion["df_rechazados"]
    df_validado = resultado_validacion["df_validado"]

    # ── Paso 6: Mostrar resumen de calidad ───────────────────────────────────
    mostrar_resumen_calidad(resumen)

    # ── Paso 7: Mostrar errores si los hay ───────────────────────────────────
    if errores:
        mostrar_detalle_errores(errores)

    # ── Paso 8: Botones de descarga ──────────────────────────────────────────
    mostrar_seccion_descarga(
        df_validos, df_rechazados, errores, nombre_usuario, archivo_subido.name
    )

    # ── Paso 9: Botón de envío ───────────────────────────────────────────────
    st.markdown("---")

    if df_validos.empty:
        st.error(
            "❌ **No hay registros válidos para enviar.** "
            "Corrija los errores indicados y vuelva a cargar el archivo."
        )
        registrar_carga(
            usuario=username,
            nombre_archivo_original=archivo_subido.name,
            nombre_archivo_guardado="",
            resumen=resumen,
            estado_operacion="FALLIDO",
            mensaje_sistema="Sin registros válidos para enviar.",
        )
        return

    if resumen["filas_rechazadas"] > 0:
        st.warning(
            f"⚠️ **{resumen['filas_rechazadas']} fila(s) tienen errores y serán excluidas del envío.** "
            f"Solo se enviarán los {resumen['filas_validas']} registros válidos."
        )

    _mostrar_boton_envio(
        df_validos=df_validos,
        resumen=resumen,
        nombre_archivo_original=archivo_subido.name,
        username=username,
        nombre_usuario=nombre_usuario,
    )


def _mostrar_boton_envio(
    df_validos: pd.DataFrame,
    resumen: dict,
    nombre_archivo_original: str,
    username: str,
    nombre_usuario: str,
) -> None:
    """Muestra el botón de envío y ejecuta la subida a GitHub."""

    st.subheader("📤 Enviar información a la compañía")

    confirmar = st.checkbox(
        "✅ Confirmo que la información es correcta y autorizo el envío.",
        key="checkbox_confirmacion",
    )

    if st.button("📨 Enviar registros válidos", disabled=not confirmar, type="primary"):
        with st.spinner("Enviando archivo a GitHub…"):
            try:
                # Generar archivo de salida limpio
                bytes_validos = generar_excel_validos(df_validos, nombre_usuario)
                nombre_guardado = construir_nombre_archivo(
                    nombre_archivo_original, username, "VALIDOS"
                )

                # Leer credenciales desde st.secrets
                token = st.secrets["github"]["token"]
                owner = st.secrets["github"]["owner"]
                repo = st.secrets["github"]["repo"]
                branch = st.secrets["github"].get("branch", "main")
                folder = st.secrets["github"].get("folder", "cargas")

                exito, resultado = subir_a_github(
                    nombre_archivo=nombre_guardado,
                    contenido_bytes=bytes_validos,
                    token=token,
                    owner=owner,
                    repo=repo,
                    branch=branch,
                    folder=folder,
                )

                if exito:
                    st.success(
                        f"🎉 **¡Archivo enviado exitosamente!**\n\n"
                        f"📁 Nombre guardado: `{nombre_guardado}`\n\n"
                        f"🔗 [Ver en GitHub]({resultado})"
                    )
                    st.info(
                        f"ℹ️ Se enviaron **{resumen['filas_validas']} registros válidos**. "
                        f"Power Automate procesará el archivo automáticamente."
                    )
                    registrar_carga(
                        usuario=username,
                        nombre_archivo_original=nombre_archivo_original,
                        nombre_archivo_guardado=nombre_guardado,
                        resumen=resumen,
                        url_github=resultado,
                        estado_operacion="EXITOSO",
                    )
                else:
                    st.error(f"❌ **Error al subir el archivo:** {resultado}")
                    registrar_carga(
                        usuario=username,
                        nombre_archivo_original=nombre_archivo_original,
                        nombre_archivo_guardado=nombre_guardado,
                        resumen=resumen,
                        estado_operacion="FALLIDO",
                        mensaje_sistema=resultado,
                    )

            except KeyError as e:
                st.error(
                    f"❌ **Configuración incompleta:** No se encontró la credencial {e} "
                    "en los secrets del servidor. Contacte al administrador."
                )
                registrar_error_sistema(username, nombre_archivo_original, str(e))

            except Exception as e:
                st.error(f"❌ **Error inesperado al enviar:** {e}")
                registrar_error_sistema(username, nombre_archivo_original, str(e))


# =============================================================================
# 6. PANEL DE ADMINISTRACIÓN (solo visible en sidebar para usuarios admin)
# =============================================================================

def mostrar_panel_admin(username: str) -> None:
    """Panel de auditoría y logs. Restrinja con lista de admins en producción."""
    ADMINS = ["admin", "coordinador"]  # ← Ajuste según los usuarios admin reales

    if username.lower() not in ADMINS:
        return

    with st.sidebar.expander("🔐 Panel de Auditoría (Admin)", expanded=False):
        st.caption("Historial de cargas registradas")
        df_log = obtener_log_como_dataframe()
        if not df_log.empty:
            st.dataframe(df_log.tail(20), use_container_width=True)
            bytes_log = obtener_log_como_bytes()
            st.download_button(
                "📥 Descargar log completo",
                data=bytes_log,
                file_name=f"auditoria_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )
        else:
            st.info("No hay registros de auditoría aún.")


# =============================================================================
# 7. PUNTO DE ENTRADA PRINCIPAL
# =============================================================================

def main() -> None:
    autenticator, status, nombre_usuario, username = configurar_autenticacion()

    # ── CASO A: Autenticado ──────────────────────────────────────────────────
    if status:
        # Sidebar
        if autenticator:
            autenticator.logout("🚪 Cerrar Sesión", "sidebar")
        st.sidebar.markdown(f"👤 **{nombre_usuario}**")
        st.sidebar.markdown("---")
        mostrar_plantilla_referencia()
        mostrar_panel_admin(username)

        # Encabezado principal
        st.title("🛡️ Portal de Carga para Facilitadores")
        st.markdown(
            "Suba su plantilla de siniestros en formato **.xlsx**. "
            "El sistema validará la información antes de enviarla."
        )
        st.markdown("---")

        # Cargador de archivo
        archivo = st.file_uploader(
            "📂 Seleccione su archivo Excel (.xlsx)",
            type=APP_CONFIG["tipos_archivo_permitidos"],
            help="El archivo debe seguir exactamente la plantilla definida por la compañía.",
        )

        if archivo:
            procesar_archivo(archivo, nombre_usuario, username)
        else:
            _mostrar_instrucciones_inicio()

    # ── CASO B: Credenciales incorrectas ────────────────────────────────────
    elif status is False:
        st.error("❌ Usuario o contraseña incorrectos. Intente nuevamente.")

    # ── CASO C: Sin sesión iniciada ──────────────────────────────────────────
    elif status is None:
        st.info("🔐 Ingrese su usuario y contraseña para continuar.")


def _mostrar_instrucciones_inicio() -> None:
    """Muestra las instrucciones iniciales cuando no hay archivo cargado."""
    with st.container():
        st.subheader("📌 Instrucciones de uso")
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("""
**Antes de cargar el archivo:**
1. Use la plantilla oficial provista por la compañía.
2. No agregue ni elimine columnas.
3. Asegúrese de que los datos cumplan el formato.
4. Guarde el archivo en formato `.xlsx`.
""")
        with col2:
            st.markdown("""
**El sistema validará automáticamente:**
- ✅ Estructura y columnas correctas
- ✅ Formato de siniestros y pólizas
- ✅ Fechas en formato válido
- ✅ Valores de catálogo (Ajuste, Estado)
- ✅ Duplicados dentro del archivo
- ✅ Campos numéricos y de texto
""")

        st.markdown("---")
        st.caption(
            "¿Necesita la plantilla? Solicítela a su coordinador de cuenta. "
            "Para soporte técnico, contacte al equipo de TI."
        )


# =============================================================================
# EJECUCIÓN
# =============================================================================
if __name__ == "__main__":
    main()

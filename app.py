# -*- coding: utf-8 -*-
"""
app.py
======
Control de asistencia y horas extra - MERCADOS DON MANUEL.

Toda la lectura/escritura de datos y el calculo de extras vive en db.py. Este
archivo solo arma la interfaz.

Ejecutar:  streamlit run app.py
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

import db
from db import DIAS_ES, TIPO_ENTRADA, TIPO_SALIDA, fmt_hm

# ---------------------------------------------------------------------------
# CONFIGURACION
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="Asistencia | Mercados Don Manuel",
    page_icon=":camera:",
    layout="centered",
)

try:
    db.inicializar()
except db.ConfiguracionFaltante as e:
    st.error(str(e))
    st.stop()
except Exception as e:  # sin internet, credenciales malas, tablas no creadas...
    st.error("No se pudo conectar con la base de datos. Revisa los Secrets y que hayas ejecutado supabase_setup.sql.")
    st.exception(e)
    st.stop()

COLOR_ENTRADA = "#059669"
COLOR_SALIDA = "#dc2626"

st.markdown(
    """
    <style>
    /* Botones grandes para usar con el dedo */
    div.stButton > button, div.stFormSubmitButton > button { min-height: 3rem; font-size: 1.05rem; }
    /* Tarjeta de estado */
    .tarjeta { border: 1px solid #e2e8f0; border-radius: 12px; padding: 0.9rem 1.1rem; background: #f8fafc; }
    .tarjeta b { font-size: 1.05rem; }
    /* Selector de foto: se oculta el texto de "arrastrar archivo" y se agranda el boton */
    [data-testid="stFileUploaderDropzoneInstructions"] { display: none; }
    [data-testid="stFileUploaderDropzone"] { justify-content: center; padding: 1rem; }
    [data-testid="stFileUploaderDropzone"] button { min-height: 3.2rem; font-size: 1.1rem; width: 100%; }
    .chip { display: inline-block; padding: 0.15rem 0.6rem; border-radius: 999px; color: white; font-weight: 600; font-size: 0.85rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data(ttl=3600, show_spinner=False)
def foto_bytes(ruta: str) -> bytes | None:
    """Descarga una foto del bucket (con cache para no bajarla en cada rerun)."""
    return db.leer_foto(ruta)


def mostrar_foto(ruta: str, **kw):
    datos = foto_bytes(ruta) if ruta else None
    if datos:
        st.image(datos, **kw)
    else:
        st.caption("Sin foto")


def forzar_camara():
    """
    Hace que el selector de archivos abra la camara del celular directamente.
    Streamlit no expone el atributo `capture` del <input type=file>, asi que
    se agrega con un poco de JavaScript desde un iframe del mismo origen.
    """
    components.html(
        """
        <script>
        (function () {
            const doc = window.parent.document;
            function aplicar() {
                doc.querySelectorAll('[data-testid="stFileUploaderDropzone"]').forEach(function (zona) {
                    const input = zona.querySelector('input[type=file]');
                    if (input) {
                        input.setAttribute('capture', 'user');
                        input.setAttribute('accept', 'image/*');
                    }
                    const boton = zona.querySelector('button');
                    if (boton && boton.textContent.indexOf('Tomar foto') === -1) {
                        boton.textContent = '📷 Tomar foto';
                    }
                });
            }
            aplicar();
            new MutationObserver(aplicar).observe(doc.body, { childList: true, subtree: true });
        })();
        </script>
        """,
        height=0,
    )


def chip(tipo: str) -> str:
    color = COLOR_ENTRADA if tipo == TIPO_ENTRADA else COLOR_SALIDA
    return f'<span class="chip" style="background:{color}">{tipo.upper()}</span>'


def hora(dt) -> str:
    if dt is None or (isinstance(dt, float) and pd.isna(dt)) or dt is pd.NaT:
        return "—"
    return pd.Timestamp(dt).strftime("%H:%M")


def hora_t(t: time | None) -> str:
    return t.strftime("%H:%M") if t else "—"


def pedir_admin() -> bool:
    """Muestra el formulario de contraseña si aun no se ha entrado como admin."""
    if st.session_state.get("admin_ok"):
        return True
    st.info("Esta sección es solo para el administrador.")
    with st.form("login_admin"):
        pwd = st.text_input("Contraseña", type="password")
        if st.form_submit_button("Entrar", width="stretch"):
            if db.verificar_admin(pwd):
                st.session_state.admin_ok = True
                st.rerun()
            st.error("Contraseña incorrecta.")
    return False


# ---------------------------------------------------------------------------
# PAGINA: REGISTRAR
# ---------------------------------------------------------------------------

def pagina_registrar():
    st.title("Registro de entrada y salida")

    empleados = db.listar_empleados(solo_activos=True)
    if empleados.empty:
        st.warning("Todavía no hay empleados registrados. Pide al administrador que los cree en **Administración**.")
        return

    nombres = empleados["nombre"].tolist()
    nombre = st.selectbox("¿Quién eres?", nombres, index=None, placeholder="Elige tu nombre")
    if not nombre:
        return

    emp = empleados.loc[empleados["nombre"] == nombre].iloc[0]
    emp_id = int(emp["id"])
    ahora = db.ahora()
    hoy = ahora.date()

    # Si cambia de persona, reiniciamos la foto pendiente
    if st.session_state.get("emp_actual") != emp_id:
        st.session_state.emp_actual = emp_id
        st.session_state.cam_n = st.session_state.get("cam_n", 0) + 1
        st.session_state.pop("foto_hora", None)
        st.session_state.pop("foto_id", None)

    # --- Estado de hoy -------------------------------------------------
    plantilla = db.horario_empleado(emp_id)
    lunes = db.lunes_de(hoy)
    semana = db.semana_empleado(emp_id, lunes, plantilla)
    hor_hoy = dict(semana).get(hoy)
    marcas_hoy = db.registros_del_dia(emp_id, hoy)

    if hor_hoy:
        txt_horario = f"{hor_hoy.texto()} (jornada {fmt_hm(hor_hoy.jornada_min)})"
    else:
        txt_horario = "Libre (sin horario programado)"

    if marcas_hoy:
        ult = marcas_hoy[-1]
        txt_ultimo = f"Último movimiento: {chip(ult['tipo'])} a las {hora(ult['fecha_hora'])}"
    else:
        txt_ultimo = "Aún no tienes marcaciones hoy"

    st.markdown(
        f"""<div class="tarjeta">
        <b>{nombre}</b> · {DIAS_ES[hoy.weekday()]} {hoy.strftime('%d/%m/%Y')}<br>
        Horario de hoy: <b>{txt_horario}</b><br>
        {txt_ultimo}
        </div>""",
        unsafe_allow_html=True,
    )
    st.write("")

    # --- Tipo de marcación --------------------------------------------
    sugerido = db.tipo_sugerido(emp_id, ahora)
    tipo = st.radio(
        "¿Qué vas a registrar?",
        [TIPO_ENTRADA, TIPO_SALIDA],
        index=0 if sugerido == TIPO_ENTRADA else 1,
        format_func=lambda t: "🟢 Entrada" if t == TIPO_ENTRADA else "🔴 Salida",
        horizontal=True,
    )

    if emp["pin"]:
        pin = st.text_input("Tu PIN", type="password", max_chars=8, placeholder="PIN asignado por el administrador")
    else:
        pin = ""

    # --- Foto ----------------------------------------------------------
    # Se usa el selector de archivos (y no st.camera_input) porque iPhone y
    # Android bloquean la camara web cuando la pagina se abre por http:// con
    # una IP de la red. El selector, forzado a modo "camara" con el atributo
    # capture (ver forzar_camara), abre la camara nativa del celular sin HTTPS.
    foto = st.file_uploader(
        "Tómate la foto",
        type=["jpg", "jpeg", "png", "heic", "heif", "webp"],
        key=f"cam_{st.session_state.get('cam_n', 0)}",
        help="En el celular se abre la cámara directamente. En el computador se elige un archivo.",
    )
    forzar_camara()

    # La hora del registro es la del momento en que llega la foto,
    # no la del clic en "Confirmar".
    if foto is not None:
        if st.session_state.get("foto_id") != foto.file_id:
            st.session_state.foto_id = foto.file_id
            st.session_state.foto_hora = db.ahora()
        momento = st.session_state.foto_hora
        c1, c2 = st.columns([1, 2])
        c1.image(foto, width=140)
        c2.caption(f"📷 Foto tomada a las **{momento.strftime('%H:%M:%S')}** del {momento.strftime('%d/%m/%Y')}")
    else:
        momento = None

    listo = foto is not None
    etiqueta = "Confirmar ENTRADA" if tipo == TIPO_ENTRADA else "Confirmar SALIDA"
    if st.button(etiqueta, type="primary", width="stretch", disabled=not listo):
        if not db.verificar_pin(emp_id, pin):
            st.error("PIN incorrecto.")
            return

        ruta = db.guardar_foto(emp_id, tipo, momento, foto.getvalue())
        db.crear_registro(emp_id, tipo, momento, ruta)

        # Preparar la camara para la siguiente persona
        st.session_state.cam_n = st.session_state.get("cam_n", 0) + 1
        st.session_state.pop("foto_hora", None)
        st.session_state.pop("foto_id", None)
        st.session_state.ultimo_ok = (emp_id, tipo, momento, ruta)
        st.rerun()

    # --- Confirmacion del ultimo registro guardado ----------------------
    ok = st.session_state.pop("ultimo_ok", None)
    if ok and ok[0] == emp_id:
        _, tipo_ok, momento_ok, ruta_ok = ok
        st.success(f"✅ {tipo_ok.capitalize()} registrada a las **{momento_ok.strftime('%H:%M:%S')}**")
        mostrar_resumen_hoy(emp_id, nombre, momento_ok.date(), hor_hoy)
        mostrar_foto(ruta_ok, width=220)

    # --- Mi horario de la semana -----------------------------------------
    with st.expander("📅 Mi horario de esta semana", expanded=False):
        tabla_semana(semana, hoy)
        prox = st.checkbox("Ver la próxima semana", key="ver_prox")
        if prox:
            tabla_semana(db.semana_empleado(emp_id, lunes + timedelta(days=7), plantilla), hoy)

    # --- Marcaciones de hoy ---------------------------------------------
    marcas_hoy = db.registros_del_dia(emp_id, hoy)
    if marcas_hoy:
        with st.expander("Ver mis marcaciones de hoy", expanded=False):
            for m in marcas_hoy:
                st.markdown(f"{chip(m['tipo'])} &nbsp; {hora(m['fecha_hora'])}", unsafe_allow_html=True)


def tabla_semana(semana, hoy: date | None = None):
    """Lista de 7 dias con su horario (para el empleado)."""
    filas = []
    total = 0
    for fecha, h in semana:
        marca = "👉 " if fecha == hoy else ""
        filas.append({
            "Día": f"{marca}{DIAS_ES[fecha.weekday()]} {fecha.strftime('%d/%m')}",
            "Horario": h.texto() if h else "Libre",
            "Jornada": fmt_hm(h.jornada_min) if h else "",
        })
        total += h.jornada_min if h else 0
    st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")
    st.caption(f"Total de la semana: **{fmt_hm(total)}**")


def mostrar_resumen_hoy(emp_id: int, nombre: str, fecha: date, hor):
    marcas = [(m["tipo"], m["fecha_hora"]) for m in db.registros_del_dia(emp_id, fecha)]
    r = db.resumir_dia(emp_id, nombre, fecha, marcas, hor, db.tolerancia_min(), db.contar_entrada_anticipada())
    partes = []
    if r.tardanza_min:
        partes.append(f"⏰ Llegada tarde: **{fmt_hm(r.tardanza_min)}**")
    if r.extra_total_min:
        partes.append(f"➕ Horas extra de hoy: **{fmt_hm(r.extra_total_min)}**")
    if r.minutos_trabajados:
        bloques = f" en {r.bloques} bloques" if r.bloques > 1 else ""
        partes.append(f"🕒 Trabajado hoy: **{fmt_hm(r.minutos_trabajados)}**{bloques}"
                      + (f" de {fmt_hm(r.jornada_min)}" if r.jornada_min else ""))
    if r.observacion:
        partes.append(f"ℹ️ {r.observacion}")
    if partes:
        st.markdown("  \n".join(partes))


# ---------------------------------------------------------------------------
# PAGINA: REPORTE DE EXTRAS
# ---------------------------------------------------------------------------

def pagina_reporte():
    st.title("Reporte de horas extra")
    if not pedir_admin():
        return

    hoy = db.ahora().date()
    c0, c1, c2 = st.columns([1.1, 1.2, 1.3])
    modo = c0.selectbox("Período", [db.PERIODO_MES, db.PERIODO_QUINCENA, db.PERIODO_RANGO],
                        format_func=lambda m: {"mes": "Mes", "quincena": "Quincena", "rango": "Rango de fechas"}[m])
    if modo == db.PERIODO_MES:
        ref = c1.date_input("Mes", value=hoy.replace(day=1), format="DD/MM/YYYY", help="Elige cualquier día del mes")
        desde, hasta = db.rango_periodo(modo, ref)
        titulo = f"Mes {desde:%m/%Y}"
    elif modo == db.PERIODO_QUINCENA:
        ref = c1.date_input("Mes", value=hoy.replace(day=1), format="DD/MM/YYYY", help="Elige cualquier día del mes")
        q = c2.radio("Quincena", [1, 2], index=0 if hoy.day <= 15 else 1, horizontal=True,
                     format_func=lambda k: "1ª (1–15)" if k == 1 else "2ª (16–fin)")
        desde, hasta = db.rango_periodo(modo, ref, q)
        titulo = f"{q}ª quincena {desde:%m/%Y}"
    else:
        desde = c1.date_input("Desde", value=hoy.replace(day=1), format="DD/MM/YYYY")
        hasta = c2.date_input("Hasta", value=hoy, format="DD/MM/YYYY")
        titulo = f"{desde:%d/%m/%Y} – {hasta:%d/%m/%Y}"

    empleados = db.listar_empleados(solo_activos=False)
    opciones = {"Todos": None} | {r.nombre: int(r.id) for r in empleados.itertuples()}
    sel = st.selectbox("Empleado", list(opciones))
    emp_id = opciones[sel]

    if desde > hasta:
        st.error("La fecha 'Desde' no puede ser mayor que 'Hasta'.")
        return

    legal_min = db.jornada_legal_min(modo, desde, hasta)
    tol = db.tolerancia_min()
    st.caption(
        f"**{titulo}** ({desde:%d/%m} – {hasta:%d/%m}) · Jornada legal del período: **{fmt_hm(legal_min)}** "
        f"(base {db.horas_semana_legal():g} h/semana = {db.horas_mes_legal():g} h/mes, ajustable en Configuración). "
        "Extra = horas trabajadas en el período − jornada legal."
    )

    resumen = db.reporte_extras(desde, hasta, emp_id)
    registros = db.listar_registros(desde, hasta, emp_id)

    if resumen.empty:
        st.info("No hay marcaciones en ese período.")
        return

    totales = db.totales_periodo(resumen, legal_min, tol)

    # --- Totales -----------------------------------------------------------
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Días con marcación", len(resumen))
    m2.metric("Horas trabajadas", fmt_hm(totales["trabajado_min"].sum()))
    m3.metric("Horas extra del período", fmt_hm(totales["extra_min"].sum()))
    m4.metric("Tardanzas", fmt_hm(totales["tardanza_min"].sum()))

    st.download_button(
        "⬇️ Descargar Excel",
        data=db.exportar_excel(resumen, registros, totales, titulo),
        file_name=f"extras_{desde:%Y%m%d}_{hasta:%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )

    # --- Liquidacion por empleado ---------------------------------------------
    st.subheader("Liquidación del período por empleado")
    tot_vista = pd.DataFrame({
        "Empleado": totales["nombre"],
        "Días": totales["dias"],
        "Horas trabajadas": totales["trabajado_min"].map(fmt_hm),
        "Jornada legal": totales["legal_min"].map(fmt_hm),
        "Horas extra": totales["extra_min"].map(fmt_hm),
        "Extra (min)": totales["extra_min"],
        "Faltante": totales["faltante_min"].map(fmt_hm),
        "Tardanza": totales["tardanza_min"].map(fmt_hm),
    })
    st.dataframe(tot_vista, hide_index=True, width="stretch")

    # --- Horas por semana -------------------------------------------------------
    st.subheader("Horas trabajadas por semana")
    st.caption(f"Referencia: {db.horas_semana_legal():g} h por semana. Las semanas se identifican por su lunes.")
    sem = db.horas_por_semana(resumen)
    sem_vista = sem.copy()
    for c in sem_vista.columns[1:]:
        sem_vista[c] = sem_vista[c].map(fmt_hm)
    st.dataframe(sem_vista, hide_index=True, width="stretch")

    # --- Detalle por dia ------------------------------------------------------
    st.subheader("Detalle por día")
    det = pd.DataFrame({
        "Empleado": resumen["nombre"],
        "Fecha": pd.to_datetime(resumen["fecha"]).dt.strftime("%d/%m/%Y"),
        "Día": resumen["dia"],
        "Horario": resumen["horario_txt"].replace("", "No programado"),
        "Jornada": resumen["jornada_min"].map(fmt_hm),
        "Entrada": resumen["entrada_real"].map(hora),
        "Salida": resumen["salida_real"].map(hora),
        "Bloques": resumen["bloques"],
        "Trabajado": resumen["minutos_trabajados"].map(fmt_hm),
        "Tardanza": resumen["tardanza_min"].map(fmt_hm),
        "Faltante": resumen["faltante_min"].map(fmt_hm),
        "Sobre horario": resumen["extra_total_min"].map(fmt_hm),
        "Observación": resumen["observacion"],
    })
    st.caption("Referencia diaria: *Sobre horario* es lo trabajado por encima del horario de ese día. "
               "Las horas extra oficiales son las de la liquidación del período.")
    st.dataframe(det, hide_index=True, width="stretch")

    # --- Fotos -----------------------------------------------------------------
    st.subheader("Fotos de un día")
    etiquetas = [f"{r.nombre} — {pd.Timestamp(r.fecha):%d/%m/%Y}" for r in resumen.itertuples()]
    i = st.selectbox("Elige empleado y día", range(len(etiquetas)), format_func=lambda k: etiquetas[k], index=None,
                     placeholder="Selecciona…")
    if i is not None:
        fila = resumen.iloc[i]
        fotos = registros[(registros["empleado_id"] == fila["empleado_id"]) & (registros["fecha"] == str(fila["fecha"]))]
        cols = st.columns(max(len(fotos), 1))
        for col, r in zip(cols, fotos.itertuples()):
            with col:
                st.markdown(f"{chip(r.tipo)} {r.fecha_hora:%H:%M:%S}", unsafe_allow_html=True)
                mostrar_foto(r.foto, width="stretch")


# ---------------------------------------------------------------------------
# PAGINA: HORARIO SEMANAL (publica)
# ---------------------------------------------------------------------------

def pagina_horarios():
    st.title("Horario semanal")
    hoy = db.ahora().date()
    ref = st.date_input("Semana del", value=db.lunes_de(hoy), format="DD/MM/YYYY", key="pub_sem")
    lunes = db.lunes_de(ref)
    st.caption(f"Semana del {lunes:%d/%m/%Y} al {lunes + timedelta(days=6):%d/%m/%Y}")
    tabla = db.semana_todos(lunes)
    if tabla.empty:
        st.info("Todavía no hay empleados.")
        return
    st.dataframe(tabla, hide_index=True, width="stretch")

    st.subheader("Ver el mío")
    nombre = st.selectbox("Empleado", tabla["Empleado"].tolist(), index=None, placeholder="Elige tu nombre",
                          key="pub_emp")
    if nombre:
        emp_id = int(db.listar_empleados().set_index("nombre").loc[nombre, "id"])
        tabla_semana(db.semana_empleado(emp_id, lunes), hoy)


# ---------------------------------------------------------------------------
# PAGINA: ADMINISTRACION
# ---------------------------------------------------------------------------

def pagina_admin():
    st.title("Administración")
    if not pedir_admin():
        return

    t_emp, t_hor, t_sem, t_reg, t_cfg = st.tabs(
        ["👥 Empleados", "🕒 Horario base", "📅 Programar semana", "📋 Marcaciones", "⚙️ Configuración"]
    )
    with t_emp:
        admin_empleados()
    with t_hor:
        admin_horarios()
    with t_sem:
        admin_semana()
    with t_reg:
        admin_registros()
    with t_cfg:
        admin_config()


def admin_empleados():
    st.subheader("Nuevo empleado")
    with st.form("nuevo_emp", clear_on_submit=True):
        c1, c2, c3 = st.columns([2, 1.5, 1])
        nombre = c1.text_input("Nombre completo")
        cargo = c2.text_input("Cargo (opcional)")
        pin = c3.text_input("PIN (opcional)", max_chars=8)
        if st.form_submit_button("Agregar", width="stretch"):
            try:
                db.crear_empleado(nombre, cargo, pin)
                st.success(f"Empleado **{nombre.strip()}** creado. Ahora asígnale un horario en la pestaña *Horarios*.")
            except ValueError as e:
                st.error(str(e))
            except Exception:
                st.error("Ya existe un empleado con ese nombre.")

    st.subheader("Empleados")
    empleados = db.listar_empleados(solo_activos=False)
    if empleados.empty:
        st.caption("Sin empleados todavía.")
        return

    for r in empleados.itertuples():
        estado = "" if r.activo else " (inactivo)"
        with st.expander(f"{r.nombre}{estado}"):
            with st.form(f"emp_{r.id}"):
                c1, c2, c3 = st.columns([2, 1.5, 1])
                n = c1.text_input("Nombre", value=r.nombre)
                c = c2.text_input("Cargo", value=r.cargo or "")
                p = c3.text_input("PIN", value=r.pin or "", max_chars=8)
                a = st.checkbox("Activo (aparece en la lista para registrarse)", value=bool(r.activo))
                b1, b2 = st.columns(2)
                if b1.form_submit_button("Guardar", width="stretch"):
                    db.actualizar_empleado(int(r.id), n, c, p, a)
                    st.success("Guardado.")
                    st.rerun()
                if b2.form_submit_button("Eliminar definitivamente", width="stretch"):
                    st.session_state[f"confirmar_del_{r.id}"] = True
            if st.session_state.get(f"confirmar_del_{r.id}"):
                st.warning(f"Se borrarán **todas** las marcaciones y el horario de {r.nombre}. ¿Seguro? "
                           "Si solo quieres que deje de aparecer, desmarca *Activo*.")
                k1, k2 = st.columns(2)
                if k1.button("Sí, eliminar", key=f"del_si_{r.id}", type="primary", width="stretch"):
                    db.eliminar_empleado(int(r.id))
                    st.session_state.pop(f"confirmar_del_{r.id}", None)
                    st.rerun()
                if k2.button("Cancelar", key=f"del_no_{r.id}", width="stretch"):
                    st.session_state.pop(f"confirmar_del_{r.id}", None)
                    st.rerun()


COLS_EDITOR = ["Trabaja", "Entrada 1", "Salida 1", "Entrada 2", "Salida 2"]


def _config_editor(etiqueta_dia: str):
    return {
        etiqueta_dia: st.column_config.TextColumn(etiqueta_dia, disabled=True, width="medium"),
        "Trabaja": st.column_config.CheckboxColumn("Trabaja", width="small"),
        "Entrada 1": st.column_config.TimeColumn("Entrada 1", format="HH:mm", step=300),
        "Salida 1": st.column_config.TimeColumn("Salida 1", format="HH:mm", step=300),
        "Entrada 2": st.column_config.TimeColumn("Entrada 2 (partido)", format="HH:mm", step=300),
        "Salida 2": st.column_config.TimeColumn("Salida 2 (partido)", format="HH:mm", step=300),
    }


def _fila_editor(etiqueta: str, h, etiqueta_col: str) -> dict:
    b = h.bloques if h else []
    return {
        etiqueta_col: etiqueta,
        "Trabaja": h is not None,
        "Entrada 1": b[0][0] if len(b) > 0 else None,
        "Salida 1": b[0][1] if len(b) > 0 else None,
        "Entrada 2": b[1][0] if len(b) > 1 else None,
        "Salida 2": b[1][1] if len(b) > 1 else None,
    }


def _bloques_de_editor(fila) -> list | None:
    """Convierte una fila del editor en lista de bloques (None = no trabaja)."""
    if not bool(fila["Trabaja"]):
        return None

    def t(v):
        if v is None or (isinstance(v, float) and pd.isna(v)) or v is pd.NaT:
            return None
        if isinstance(v, time):
            return v
        return pd.Timestamp(v).time()

    return db.limpiar_bloques([(t(fila["Entrada 1"]), t(fila["Salida 1"])), (t(fila["Entrada 2"]), t(fila["Salida 2"]))])


def editor_semana(clave: str, filas: list[dict], etiqueta_col: str) -> pd.DataFrame:
    """Tabla editable de 7 dias con hasta 2 bloques. Escribe las horas como 08:00."""
    df = pd.DataFrame(filas, columns=[etiqueta_col] + COLS_EDITOR)
    return st.data_editor(
        df, key=clave, hide_index=True, width="stretch", num_rows="fixed",
        column_config=_config_editor(etiqueta_col),
    )


def relleno_rapido(clave: str):
    """Devuelve (bloques, dias_idx) si el usuario pulso 'Aplicar', si no None."""
    with st.expander("Relleno rápido"):
        c1, c2, c3, c4 = st.columns(4)
        e1 = c1.time_input("Entrada 1", value=time(8, 0), key=f"{clave}_e1", step=timedelta(minutes=15))
        s1 = c2.time_input("Salida 1", value=time(12, 0), key=f"{clave}_s1", step=timedelta(minutes=15))
        e2 = c3.time_input("Entrada 2", value=time(14, 0), key=f"{clave}_e2", step=timedelta(minutes=15))
        s2 = c4.time_input("Salida 2", value=time(21, 0), key=f"{clave}_s2", step=timedelta(minutes=15))
        partido = st.checkbox("Turno partido (usar los dos bloques)", value=True, key=f"{clave}_p")
        dias = st.multiselect("Días", DIAS_ES, default=DIAS_ES[:6], key=f"{clave}_d")
        if st.button("Aplicar a los días elegidos", key=f"{clave}_b", width="stretch"):
            bloques = [(e1, s1)] + ([(e2, s2)] if partido else [])
            return bloques, [DIAS_ES.index(d) for d in dias]
    return None


def admin_horarios():
    empleados = db.listar_empleados(solo_activos=False)
    if empleados.empty:
        st.caption("Primero crea empleados.")
        return

    nombres = {r.nombre: int(r.id) for r in empleados.itertuples()}
    sel = st.selectbox("Empleado", list(nombres), key="hor_emp")
    emp_id = nombres[sel]
    actual = db.horario_empleado(emp_id)

    st.caption(
        "Este es el horario **base** que se repite cada semana. Cada día puede tener un bloque "
        "(turno corrido) o dos (turno partido, ej. 8:00–12:00 y 14:00–21:00). "
        "Si una semana cambia, se programa en la pestaña *Programar semana* sin tocar este."
    )

    ver = st.session_state.get(f"ver_hor_{emp_id}", 0)
    prefill = st.session_state.pop(f"prefill_hor_{emp_id}", None)

    r = relleno_rapido(f"rr_hor_{emp_id}")
    if r:
        bloques, idx = r
        base = {d: (actual.get(d).bloques if actual.get(d) else None) for d in range(7)}
        for d in idx:
            base[d] = bloques
        st.session_state[f"prefill_hor_{emp_id}"] = base
        st.session_state[f"ver_hor_{emp_id}"] = ver + 1
        st.rerun()

    otros = [n for n in nombres if nombres[n] != emp_id]
    if otros:
        c4, c5 = st.columns([2, 1])
        origen = c4.selectbox("Copiar horario base de", otros, index=None, placeholder="Elige empleado")
        if c5.button("Copiar", width="stretch", disabled=origen is None):
            db.copiar_horario(nombres[origen], emp_id)
            st.session_state[f"ver_hor_{emp_id}"] = ver + 1
            st.success("Horario copiado.")
            st.rerun()

    filas = []
    for d in range(7):
        if prefill is not None:
            h = db.Horario(prefill[d]) if prefill[d] else None
        else:
            h = actual.get(d)
        filas.append(_fila_editor(DIAS_ES[d], h, "Día"))

    editado = editor_semana(f"ed_hor_{emp_id}_{ver}", filas, "Día")
    if st.button("Guardar horario base", type="primary", width="stretch", key=f"g_hor_{emp_id}"):
        nuevos = {d: _bloques_de_editor(editado.iloc[d]) for d in range(7)}
        db.guardar_horario(emp_id, nuevos)
        st.session_state[f"ver_hor_{emp_id}"] = ver + 1
        st.success(f"Horario base de {sel} guardado.")
        st.rerun()

    if actual:
        st.caption("Horario base actual: " + " · ".join(
            f"{DIAS_ES[d][:3]} {h.texto()}" for d, h in sorted(actual.items())
        ) + f" — {fmt_hm(sum(h.jornada_min for h in actual.values()))}/semana")
    else:
        st.warning("Este empleado no tiene horario base. Sin horario, todo lo que trabaje se contará como extra.")


def admin_semana():
    empleados = db.listar_empleados(solo_activos=True)
    if empleados.empty:
        st.caption("Primero crea empleados.")
        return

    st.caption(
        "Programa aquí los turnos de una semana concreta cuando difieren del horario base "
        "(turnos partidos, cambios de día libre, etc.). Los días que no programes siguen el horario base. "
        "Los empleados ven esta programación en *Registrar → Mi horario de esta semana*."
    )
    c1, c2 = st.columns([1, 2])
    ref = c1.date_input("Semana del", value=db.lunes_de(db.ahora().date()), format="DD/MM/YYYY", key="sem_fecha")
    lunes = db.lunes_de(ref)
    nombres = {r.nombre: int(r.id) for r in empleados.itertuples()}
    sel = c2.selectbox("Empleado", list(nombres), key="sem_emp")
    emp_id = nombres[sel]
    domingo = lunes + timedelta(days=6)
    st.markdown(f"**Semana del {lunes:%d/%m/%Y} al {domingo:%d/%m/%Y}** — {sel}")

    plantilla = db.horario_empleado(emp_id)
    turnos = db.turnos_rango(lunes, domingo, emp_id)
    semana = db.semana_empleado(emp_id, lunes, plantilla, turnos)
    programada = any((emp_id, f) in turnos for f, _ in semana)
    if programada:
        st.info("Esta semana tiene programación propia. Los días marcados con ★ vienen de la programación; el resto, del horario base.")
    else:
        st.info("Esta semana no tiene programación propia: se muestra el horario base. Edita y guarda para programarla.")

    clave = f"{emp_id}_{lunes}"
    ver = st.session_state.get(f"ver_sem_{clave}", 0)
    prefill = st.session_state.pop(f"prefill_sem_{clave}", None)

    r = relleno_rapido(f"rr_sem_{clave}")
    if r:
        bloques, idx = r
        base = {f: (h.bloques if h else None) for f, h in semana}
        for d in idx:
            base[lunes + timedelta(days=d)] = bloques
        st.session_state[f"prefill_sem_{clave}"] = base
        st.session_state[f"ver_sem_{clave}"] = ver + 1
        st.rerun()

    b1, b2 = st.columns(2)
    if b1.button("Copiar la semana anterior", width="stretch", key=f"cp_{clave}"):
        ant = db.semana_empleado(emp_id, lunes - timedelta(days=7), plantilla)
        st.session_state[f"prefill_sem_{clave}"] = {f + timedelta(days=7): (h.bloques if h else None) for f, h in ant}
        st.session_state[f"ver_sem_{clave}"] = ver + 1
        st.rerun()
    if b2.button("Volver al horario base (borrar programación)", width="stretch", key=f"rm_{clave}",
                 disabled=not programada):
        db.borrar_semana(emp_id, lunes)
        st.session_state[f"ver_sem_{clave}"] = ver + 1
        st.success("Programación de la semana eliminada.")
        st.rerun()

    filas = []
    for fecha, h in semana:
        if prefill is not None:
            h = db.Horario(prefill[fecha]) if prefill.get(fecha) else None
        estrella = " ★" if (emp_id, fecha) in turnos else ""
        filas.append(_fila_editor(f"{DIAS_ES[fecha.weekday()]} {fecha:%d/%m}{estrella}", h, "Fecha"))

    editado = editor_semana(f"ed_sem_{clave}_{ver}", filas, "Fecha")
    if st.button("Guardar programación de la semana", type="primary", width="stretch", key=f"g_sem_{clave}"):
        nuevos = {lunes + timedelta(days=i): _bloques_de_editor(editado.iloc[i]) for i in range(7)}
        db.guardar_semana(emp_id, lunes, nuevos)
        st.session_state[f"ver_sem_{clave}"] = ver + 1
        st.success(f"Semana del {lunes:%d/%m} programada para {sel}.")
        st.rerun()

    st.divider()
    st.subheader("Vista de toda la semana")
    tabla = db.semana_todos(lunes)
    if tabla.empty:
        st.caption("Sin empleados activos.")
    else:
        st.dataframe(tabla, hide_index=True, width="stretch")


def admin_registros():
    st.caption("Corrige o elimina marcaciones equivocadas, o agrega una manual (sin foto).")
    hoy = db.ahora().date()
    c1, c2, c3 = st.columns([1, 1, 1.3])
    desde = c1.date_input("Desde", value=hoy - timedelta(days=7), format="DD/MM/YYYY", key="reg_desde")
    hasta = c2.date_input("Hasta", value=hoy, format="DD/MM/YYYY", key="reg_hasta")
    empleados = db.listar_empleados(solo_activos=False)
    opciones = {"Todos": None} | {r.nombre: int(r.id) for r in empleados.itertuples()}
    sel = c3.selectbox("Empleado", list(opciones), key="reg_emp")

    regs = db.listar_registros(desde, hasta, opciones[sel])
    if regs.empty:
        st.info("Sin marcaciones en ese rango.")
    else:
        vista = pd.DataFrame({
            "ID": regs["id"],
            "Empleado": regs["nombre"],
            "Tipo": regs["tipo"],
            "Fecha y hora": regs["fecha_hora"].dt.strftime("%d/%m/%Y %H:%M:%S"),
            "Foto": regs["foto"].map(lambda f: "📷" if f else ""),
            "Nota": regs["nota"],
        })
        st.dataframe(vista, hide_index=True, width="stretch")

        st.subheader("Editar una marcación")
        etiquetas = {int(r.id): f"#{r.id} · {r.nombre} · {r.tipo} · {r.fecha_hora:%d/%m %H:%M}" for r in regs.itertuples()}
        rid = st.selectbox("Marcación", list(etiquetas), format_func=lambda k: etiquetas[k], index=None,
                           placeholder="Selecciona…")
        if rid is not None:
            r = regs.loc[regs["id"] == rid].iloc[0]
            if r["foto"]:
                mostrar_foto(r["foto"], width=200)
            with st.form(f"edit_reg_{rid}"):
                c1, c2, c3 = st.columns(3)
                tipo = c1.radio("Tipo", [TIPO_ENTRADA, TIPO_SALIDA], index=0 if r["tipo"] == TIPO_ENTRADA else 1,
                                horizontal=True)
                f = c2.date_input("Fecha", value=r["fecha_hora"].date(), format="DD/MM/YYYY")
                h = c3.time_input("Hora", value=r["fecha_hora"].time(), step=timedelta(minutes=1))
                nota = st.text_input("Nota", value=r["nota"] or "")
                b1, b2 = st.columns(2)
                if b1.form_submit_button("Guardar cambios", width="stretch"):
                    db.actualizar_registro(rid, tipo, datetime.combine(f, h), nota)
                    st.success("Marcación actualizada.")
                    st.rerun()
                if b2.form_submit_button("Eliminar", width="stretch"):
                    db.eliminar_registro(rid)
                    st.success("Marcación eliminada.")
                    st.rerun()

    st.subheader("Agregar marcación manual")
    if empleados.empty:
        return
    with st.form("nuevo_reg", clear_on_submit=True):
        c1, c2 = st.columns(2)
        nombres = {r.nombre: int(r.id) for r in empleados.itertuples()}
        e = c1.selectbox("Empleado", list(nombres))
        t = c2.radio("Tipo", [TIPO_ENTRADA, TIPO_SALIDA], horizontal=True)
        c3, c4 = st.columns(2)
        f = c3.date_input("Fecha", value=hoy, format="DD/MM/YYYY")
        h = c4.time_input("Hora", value=time(8, 0), step=timedelta(minutes=1))
        nota = st.text_input("Nota (motivo)", placeholder="Ej: olvidó marcar, celular sin batería")
        if st.form_submit_button("Agregar", width="stretch"):
            db.crear_registro(nombres[e], t, datetime.combine(f, h), "", nota or "Registro manual")
            st.success("Marcación agregada.")
            st.rerun()


def admin_config():
    st.subheader("Reglas de cálculo")
    with st.form("cfg"):
        tol = st.number_input(
            "Tolerancia (minutos)", min_value=0, max_value=120, value=db.tolerancia_min(),
            help="Si la diferencia con el horario es menor o igual a esta cantidad, no se cuenta ni como extra ni como tardanza. "
                 "Si la supera, se cuentan todos los minutos.",
        )
        antes = st.checkbox(
            "Contar como extra el tiempo ANTES de la hora de entrada", value=db.contar_entrada_anticipada(),
            help="Si está desmarcado, solo cuenta el tiempo después de la hora de salida programada.",
        )
        c1, c2 = st.columns(2)
        h_sem = c1.number_input(
            "Jornada legal semanal (horas)", min_value=1.0, max_value=60.0, value=float(db.horas_semana_legal()),
            step=0.5, help="Colombia: 42 h desde el 15 de julio de 2026 (Ley 2101 de 2021).",
        )
        h_mes = c2.number_input(
            "Jornada mensual para liquidar (horas)", min_value=1.0, max_value=300.0, value=float(db.horas_mes_legal()),
            step=1.0, help="Convención de nómina: semanal × 5 (mes de 30 días). 42 h/semana → 210 h/mes. "
                           "Quincena = la mitad. Las horas extra del período = trabajadas − esta jornada.",
        )
        if st.form_submit_button("Guardar reglas", width="stretch"):
            db.set_config("tolerancia_min", int(tol))
            db.set_config("contar_entrada_anticipada", "1" if antes else "0")
            db.set_config("horas_semana_legal", f"{h_sem:g}")
            db.set_config("horas_mes_legal", f"{h_mes:g}")
            st.success("Reglas guardadas.")

    st.subheader("Contraseña de administrador")
    with st.form("pwd", clear_on_submit=True):
        p1 = st.text_input("Nueva contraseña", type="password")
        p2 = st.text_input("Repetir contraseña", type="password")
        if st.form_submit_button("Cambiar contraseña", width="stretch"):
            if len(p1) < 4:
                st.error("Mínimo 4 caracteres.")
            elif p1 != p2:
                st.error("Las contraseñas no coinciden.")
            else:
                db.cambiar_password_admin(p1)
                st.success("Contraseña cambiada.")

    st.subheader("Datos")
    st.caption(f"Los datos y las fotos están en Supabase. Zona horaria: `{db.zona().key}`.")
    if st.button("Cerrar sesión de administrador", width="stretch"):
        st.session_state.admin_ok = False
        st.rerun()


# ---------------------------------------------------------------------------
# NAVEGACION
# ---------------------------------------------------------------------------

with st.sidebar:
    st.markdown("### Mercados Don Manuel")
    st.caption("Control de asistencia")
    st.caption("Registra tu entrada y salida con foto.")

pg = st.navigation([
    st.Page(pagina_registrar, title="Registrar", icon="📸", default=True, url_path="registrar"),
    st.Page(pagina_horarios, title="Horario semanal", icon="📅", url_path="horarios"),
    st.Page(pagina_reporte, title="Reporte de extras", icon="📊", url_path="reporte"),
    st.Page(pagina_admin, title="Administración", icon="⚙️", url_path="admin"),
])
pg.run()

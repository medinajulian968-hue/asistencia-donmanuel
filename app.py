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


@st.cache_data(ttl=120, show_spinner=False)
def sedes_activas() -> list[str]:
    return db.listar_sedes()


def opciones_sede(actual: str = "") -> list[str]:
    """Lista de sedes para selectores; incluye la actual aunque este inactiva."""
    ops = sedes_activas()
    if actual and actual not in ops:
        ops = ops + [actual]
    return ops


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
    sede_base = emp["sede"] or ""
    lunes = db.lunes_de(hoy)
    semana = db.semana_empleado(emp_id, lunes, plantilla, sede_defecto=sede_base)
    hor_hoy = dict(semana).get(hoy)
    marcas_hoy = db.registros_del_dia(emp_id, hoy)
    sede_hoy = (hor_hoy.sede if hor_hoy else "") or sede_base

    if hor_hoy:
        txt_horario = f"{hor_hoy.texto()} (jornada {fmt_hm(hor_hoy.jornada_min)})"
    else:
        txt_horario = "Libre (sin horario programado)"
    txt_sede = f"Sede: <b>{sede_hoy}</b><br>" if sede_hoy else ""

    if marcas_hoy:
        ult = marcas_hoy[-1]
        txt_ultimo = f"Último movimiento: {chip(ult['tipo'])} a las {hora(ult['fecha_hora'])}"
    else:
        txt_ultimo = "Aún no tienes marcaciones hoy"

    st.markdown(
        f"""<div class="tarjeta">
        <b>{nombre}</b> · {DIAS_ES[hoy.weekday()]} {hoy.strftime('%d/%m/%Y')}<br>
        {txt_sede}Horario de hoy: <b>{txt_horario}</b><br>
        {txt_ultimo}
        </div>""",
        unsafe_allow_html=True,
    )
    st.write("")

    prox_lunes = lunes + timedelta(days=7)
    prox_turnos = db.turnos_rango(prox_lunes, prox_lunes + timedelta(days=6), emp_id)
    aviso = " — ¡ya está la próxima semana!" if prox_turnos else ""

    with st.expander(f"📅 Mi horario{aviso}", expanded=bool(prox_turnos)):
        cual = st.radio("Semana", ["Esta semana", "Próxima semana"], horizontal=True,
                        label_visibility="collapsed", key=f"sem_cual_{emp_id}")
        if cual == "Esta semana":
            st.caption(f"Del {lunes:%d/%m} al {lunes + timedelta(days=6):%d/%m}")
            tabla_semana(semana, hoy)
        else:
            st.caption(f"Del {prox_lunes:%d/%m} al {prox_lunes + timedelta(days=6):%d/%m}")
            tabla_semana(db.semana_empleado(emp_id, prox_lunes, plantilla, prox_turnos, sede_base), hoy)
            if not prox_turnos:
                st.info("La próxima semana todavía no está programada. Mientras tanto se muestra "
                        "tu horario de siempre, que puede cambiar.")

    # --- Tipo de marcación --------------------------------------------
    sugerido = db.tipo_sugerido(emp_id, ahora)
    tipo = st.radio(
        "¿Qué vas a registrar?",
        [TIPO_ENTRADA, TIPO_SALIDA],
        index=0 if sugerido == TIPO_ENTRADA else 1,
        format_func=lambda t: "🟢 Entrada" if t == TIPO_ENTRADA else "🔴 Salida",
        horizontal=True,
    )

    # --- Clave del colaborador (obligatoria) ---------------------------
    if not emp["pin"]:
        st.error("No tienes clave asignada. Pídele al administrador que te asigne una en *Administración → Empleados* "
                 "para poder marcar.")
        return

    pin = st.text_input("Tu clave", type="password", max_chars=8, placeholder="Escribe tu clave personal",
                        key=f"pin_{emp_id}")
    if not pin:
        st.info("Escribe tu clave para poder tomar la foto.")
        return
    if pin.strip() != str(emp["pin"]).strip():
        st.error("Clave incorrecta.")
        return

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
        db.crear_registro(emp_id, tipo, momento, ruta, sede=sede_hoy)

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
            "Sede": ("" if h is None or h.vacaciones else h.sede) or "",
            "Horario": h.texto() if h else "Libre",
            "Jornada": fmt_hm(h.jornada_min) if h and not h.vacaciones else "",
        })
        total += h.jornada_min if h else 0
    st.dataframe(pd.DataFrame(filas), hide_index=True, width="stretch")
    st.caption(f"Total de la semana: **{fmt_hm(total)}**")


def mostrar_resumen_hoy(emp_id: int, nombre: str, fecha: date, hor):
    marcas = [(m["tipo"], m["fecha_hora"]) for m in db.registros_del_dia(emp_id, fecha)]
    r = db.resumir_dia(emp_id, nombre, fecha, marcas, hor, db.tolerancia_min(), db.contar_entrada_anticipada(),
                       db.gracia_salida_min())
    # Se muestra el tiempo YA CONTADO (no el de permanencia) para que las cifras
    # cuadren entre si sin tener que explicar la gabela: trabajado - jornada = extra.
    partes = []
    if r.minutos_trabajados:
        bloques = f" en {r.bloques} bloques" if r.bloques > 1 else ""
        partes.append(f"🕒 Trabajado hoy: **{fmt_hm(r.minutos_trabajados)}**{bloques}"
                      + (f" de **{fmt_hm(r.jornada_min)}**" if r.jornada_min else ""))
    if r.extra_total_min:
        partes.append(f"➕ Horas extra de hoy: **{fmt_hm(r.extra_total_min)}**")
    if r.tardanza_min:
        partes.append(f"⏰ Llegada tarde: **{fmt_hm(r.tardanza_min)}**")
    # Los demas avisos (sin salida, salida anticipada, faltó marcar el descanso)
    # estan pensados para un dia ya cerrado: a media jornada confunden al que
    # acaba de marcar. Quedan en el reporte, que es donde se revisan.
    AVISOS_UTILES = ("Vacaciones", "Día no programado")
    avisos = [o for o in r.observacion.split(", ") if o in AVISOS_UTILES]
    if avisos:
        partes.append("ℹ️ " + ", ".join(avisos))
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
    modo = c0.selectbox("Período", [db.PERIODO_SEMANA, db.PERIODO_MES, db.PERIODO_QUINCENA, db.PERIODO_RANGO],
                        index=1,
                        format_func=lambda m: {"semana": "Semana", "mes": "Mes", "quincena": "Quincena",
                                               "rango": "Rango de fechas"}[m])
    if modo == db.PERIODO_SEMANA:
        ref = c1.date_input("Semana", value=db.lunes_de(hoy), format="DD/MM/YYYY", help="Elige cualquier día de la semana")
        desde, hasta = db.rango_periodo(modo, ref)
        titulo = f"Semana del {desde:%d/%m/%Y}"
    elif modo == db.PERIODO_MES:
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
    f1, f2 = st.columns(2)
    sel = f1.selectbox("Empleado", list(opciones))
    emp_id = opciones[sel]
    sede_sel = f2.selectbox("Sede", ["Todas"] + sedes_activas(), key="rep_sede")
    sede_f = None if sede_sel == "Todas" else sede_sel

    if desde > hasta:
        st.error("La fecha 'Desde' no puede ser mayor que 'Hasta'.")
        return

    legal_min = db.jornada_legal_min(modo, desde, hasta)
    tol = db.tolerancia_min()
    st.caption(
        f"**{titulo}** ({desde:%d/%m} – {hasta:%d/%m}) · Jornada legal del período: **{fmt_hm(legal_min)}** "
        f"(base {db.horas_semana_legal():g} h/semana = {db.horas_mes_legal():g} h/mes, ajustable en Configuración; "
        f"cada día de vacaciones la baja en {fmt_hm(db.minutos_jornada_dia())}). "
        "Extra = horas trabajadas en el período − jornada legal. "
        f"Los primeros {db.gracia_salida_min()} min por encima de la jornada no cuentan (una sola vez al día)."
    )

    resumen = db.reporte_extras(desde, hasta, emp_id, sede_f)
    registros = db.listar_registros(desde, hasta, emp_id)

    if resumen.empty:
        st.info("No hay marcaciones en ese período.")
        return
    if sede_f:
        st.caption(f"Mostrando solo los días trabajados en **{sede_f}**. La liquidación del período "
                   "se calcula sobre esos días; para la liquidación completa elige *Todas*.")

    vac = db.dias_vacaciones(desde, hasta, emp_id)
    totales = db.totales_periodo(resumen, legal_min, tol, vac)

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
        "Vacaciones (días)": totales["dias_vacaciones"],
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
    st.caption(f"Referencia: {db.horas_semana_legal():g} h por semana. Entre paréntesis, lo que sobra (+) o falta (−) "
               "respecto a esa jornada. Las semanas se identifican por su lunes; una semana cortada por el "
               "inicio o fin del período se ve incompleta.")
    sem = db.horas_por_semana(resumen)
    sem_vista = sem.copy()
    legal_sem = int(round(db.horas_semana_legal() * 60))
    for c in sem_vista.columns[1:]:
        sem_vista[c] = sem_vista[c].map(lambda m: db.fmt_semana(m, legal_sem, tol))
    st.dataframe(sem_vista, hide_index=True, width="stretch")

    # --- Detalle por dia ------------------------------------------------------
    st.subheader("Detalle por día")
    det = pd.DataFrame({
        "Empleado": resumen["nombre"],
        "Fecha": pd.to_datetime(resumen["fecha"]).dt.strftime("%d/%m/%Y"),
        "Día": resumen["dia"],
        "Sede": resumen["sede"],
        "Horario": resumen["horario_txt"].replace("", "No programado"),
        "Jornada": resumen["jornada_min"].map(fmt_hm),
        "Bloques": resumen["bloques"],
        "Marcaciones": resumen["pares"].map(db.fmt_pares),
        "En el sitio": resumen["minutos_presencia"].map(fmt_hm),
        "Contado": resumen["minutos_trabajados"].map(fmt_hm),
        "Tardanza": resumen["tardanza_min"].map(fmt_hm),
        "Salió antes": resumen["faltante_min"].map(fmt_hm),
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
    c1, c2 = st.columns([1.6, 1])
    cual = c1.radio("Semana", ["Esta semana", "Próxima semana", "Otra fecha"], horizontal=True,
                    label_visibility="collapsed", key="pub_cual")
    sede_sel = c2.selectbox("Sede", ["Todas"] + sedes_activas(), key="pub_sede")
    if cual == "Otra fecha":
        ref = st.date_input("Semana del", value=db.lunes_de(hoy), format="DD/MM/YYYY", key="pub_sem")
    else:
        ref = hoy if cual == "Esta semana" else hoy + timedelta(days=7)
    lunes = db.lunes_de(ref)
    st.caption(f"Semana del {lunes:%d/%m/%Y} al {lunes + timedelta(days=6):%d/%m/%Y}"
               + (f" · {sede_sel}" if sede_sel != "Todas" else ""))
    tabla = db.semana_todos(lunes, None if sede_sel == "Todas" else sede_sel)
    if tabla.empty:
        st.info("Nadie programado en esa sede esa semana." if sede_sel != "Todas" else "Todavía no hay empleados.")
    else:
        st.dataframe(tabla, hide_index=True, width="stretch")
        if sede_sel != "Todas":
            st.caption("Entre paréntesis: días en otra sede.")

    st.subheader("Ver el mío")
    emps = db.listar_empleados()
    nombre = st.selectbox("Empleado", emps["nombre"].tolist(), index=None, placeholder="Elige tu nombre",
                          key="pub_emp")
    if nombre:
        emp_id = int(emps.set_index("nombre").loc[nombre, "id"])
        tabla_semana(db.semana_empleado(emp_id, lunes), hoy)


# ---------------------------------------------------------------------------
# PAGINA: SIN MARCAR
# ---------------------------------------------------------------------------

def pagina_pendientes():
    st.title("Sin marcar")
    if not pedir_admin():
        return

    ahora = db.ahora()
    hoy = ahora.date()
    c1, c2, c3 = st.columns([1.2, 1, 1.2])
    fecha = c1.date_input("Día", value=hoy, format="DD/MM/YYYY", key="pend_fecha")
    margen = c2.number_input("Esperar (min)", min_value=0, max_value=480, value=60, step=15,
                             key="pend_margen",
                             help="Cuánto se espera después de la hora antes de reportar a alguien. "
                                  "Con 60, a quien entraba a las 7:00 se le reporta a las 8:00.")
    sede_sel = c3.selectbox("Sede", ["Todas"] + sedes_activas(), key="pend_sede")

    # Para un día ya pasado se revisa el día completo, no solo hasta la hora actual
    momento = ahora if fecha >= hoy else datetime.combine(fecha, time(23, 59))
    try:
        pend = db.pendientes_de_marcar(fecha, momento, int(margen),
                                       None if sede_sel == "Todas" else sede_sel)
    except Exception as e:
        # st.error no se censura en Streamlit Cloud: asi se ve la causa real
        st.error(f"No se pudo armar la lista. Error: **{type(e).__name__}: {e}**")
        st.caption("Mándale este mensaje a quien administra la app.")
        return

    if not pend:
        st.success(f"✅ Nadie pendiente. Todos los que debían marcar hasta ahora el "
                   f"{fecha:%d/%m/%Y} lo hicieron.")
        return

    st.warning(f"**{len(pend)}** marcación(es) sin registrar de **{len({p['empleado_id'] for p in pend})}** persona(s).")

    filas = [{
        "Registrar": False,
        "Empleado": p["nombre"],
        "Sede": p["sede"],
        "Falta": p["tipo"].capitalize(),
        "Debía marcar": f"{p['esperado']:%H:%M}",
        "Hace": fmt_hm(p["atraso_min"]),
        "Horario del día": p["horario"],
    } for p in pend]

    st.caption("Marca **Registrar** en quienes sepas que sí llegaron a la hora y pulsa el botón de abajo: "
               "se les crea la marcación a su hora programada, con nota de que la agregaste tú.")
    editado = st.data_editor(
        pd.DataFrame(filas), hide_index=True, width="stretch", num_rows="fixed",
        key=f"pend_ed_{fecha}_{margen}_{sede_sel}",
        column_config={
            "Registrar": st.column_config.CheckboxColumn("Registrar", width="small"),
            "Empleado": st.column_config.TextColumn(disabled=True),
            "Sede": st.column_config.TextColumn(disabled=True, width="small"),
            "Falta": st.column_config.TextColumn(disabled=True, width="small"),
            "Debía marcar": st.column_config.TextColumn(disabled=True, width="small"),
            "Hace": st.column_config.TextColumn(disabled=True, width="small"),
            "Horario del día": st.column_config.TextColumn(disabled=True),
        },
    )

    elegidos = [p for p, fila in zip(pend, editado.to_dict("records")) if bool(fila["Registrar"])]
    if st.button(f"Registrar {len(elegidos)} marcación(es) a su hora programada",
                 type="primary", width="stretch", disabled=not elegidos):
        for p in elegidos:
            db.crear_registro(p["empleado_id"], p["tipo"], p["esperado"], "",
                              "Agregada por administración (no marcó)", p["sede"])
        st.success(f"Listo: {len(elegidos)} marcación(es) registradas.")
        st.rerun()

    st.caption("A quien no llegó a la hora, déjalo sin marcar y corrígelo en "
               "*Administración → Marcaciones* con la hora real.")


# ---------------------------------------------------------------------------
# PAGINA: ADMINISTRACION
# ---------------------------------------------------------------------------

def pagina_admin():
    st.title("Administración")
    if not pedir_admin():
        return

    t_emp, t_hor, t_sem, t_imp, t_reg, t_sedes, t_cfg = st.tabs(
        ["👥 Empleados", "🕒 Horario base", "📅 Programar semana", "📥 Importar",
         "📋 Marcaciones", "🏬 Sedes", "⚙️ Configuración"]
    )
    with t_imp:
        admin_importar()
    with t_emp:
        admin_empleados()
    with t_sedes:
        admin_sedes()
    with t_hor:
        admin_horarios()
    with t_sem:
        admin_semana()
    with t_reg:
        admin_registros()
    with t_cfg:
        admin_config()


def admin_sedes():
    st.caption("Las sedes se usan para programar en qué tienda trabaja cada persona cada día.")
    with st.form("nueva_sede", clear_on_submit=True):
        c1, c2 = st.columns([3, 1])
        nombre = c1.text_input("Nueva sede", placeholder="Ej: Gourmet, Parque, Centro…")
        if c2.form_submit_button("Agregar", width="stretch"):
            try:
                db.crear_sede(nombre)
                sedes_activas.clear()
                st.success(f"Sede **{nombre.strip()}** agregada.")
                st.rerun()
            except ValueError as e:
                st.error(str(e))
    activas = db.listar_sedes(solo_activas=True)
    todas = db.listar_sedes(solo_activas=False)
    if not todas:
        st.info("No hay sedes todavía. Agrega al menos una.")
        return
    st.subheader("Sedes")
    for nombre in todas:
        c1, c2 = st.columns([3, 1])
        act = nombre in activas
        c1.markdown(f"**{nombre}**" + ("" if act else " (inactiva)"))
        if c2.button("Desactivar" if act else "Activar", key=f"sede_{nombre}", width="stretch"):
            db.activar_sede(nombre, not act)
            sedes_activas.clear()
            st.rerun()


def admin_empleados():
    st.subheader("Nuevo empleado")
    sedes = sedes_activas()
    with st.form("nuevo_emp", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([2, 1.3, 1.2, 0.8])
        nombre = c1.text_input("Nombre completo")
        cargo = c2.text_input("Cargo (opcional)")
        sede = c3.selectbox("Sede base", [""] + sedes, format_func=lambda x: x or "—")
        pin = c4.text_input("Clave", max_chars=8, help="Obligatoria: 4 a 8 caracteres. Sin clave no puede marcar.")
        if st.form_submit_button("Agregar", width="stretch"):
            try:
                if len(pin.strip()) < 4:
                    raise ValueError("La clave es obligatoria y debe tener al menos 4 caracteres.")
                db.crear_empleado(nombre, cargo, pin, sede)
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
        sede_txt = f" · {r.sede}" if r.sede else ""
        sin_clave = "" if r.pin else " ⚠️ sin clave"
        with st.expander(f"{r.nombre}{sede_txt}{estado}{sin_clave}"):
            if not r.pin:
                st.warning("Este empleado no tiene clave: no podrá marcar hasta que le asignes una.")
            with st.form(f"emp_{r.id}"):
                c1, c2, c3, c4 = st.columns([2, 1.3, 1.2, 0.8])
                n = c1.text_input("Nombre", value=r.nombre)
                c = c2.text_input("Cargo", value=r.cargo or "")
                ops = [""] + opciones_sede(r.sede or "")
                sd = c3.selectbox("Sede base", ops, index=ops.index(r.sede or ""), format_func=lambda x: x or "—",
                                  key=f"sede_emp_{r.id}")
                p = c4.text_input("Clave", value=r.pin or "", max_chars=8)
                a = st.checkbox("Activo (aparece en la lista para registrarse)", value=bool(r.activo))
                b1, b2 = st.columns(2)
                if b1.form_submit_button("Guardar", width="stretch"):
                    if len(p.strip()) < 4:
                        st.error("La clave debe tener al menos 4 caracteres.")
                        st.stop()
                    db.actualizar_empleado(int(r.id), n, c, p, a, sd)
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


ESTADOS_DIA = ["Trabaja", "Descanso", "Vacaciones"]
COLS_EDITOR = ["Estado", "Sede", "Entrada 1", "Salida 1", "Entrada 2", "Salida 2"]


def _config_editor(etiqueta_dia: str, con_vacaciones: bool = True):
    return {
        etiqueta_dia: st.column_config.TextColumn(etiqueta_dia, disabled=True, width="medium"),
        "Estado": st.column_config.SelectboxColumn(
            "Estado", options=ESTADOS_DIA if con_vacaciones else ESTADOS_DIA[:2], width="small", required=True),
        "Sede": st.column_config.SelectboxColumn("Sede", options=sedes_activas(), width="small"),
        "Entrada 1": st.column_config.TimeColumn("Entrada 1", format="HH:mm", step=300),
        "Salida 1": st.column_config.TimeColumn("Salida 1", format="HH:mm", step=300),
        "Entrada 2": st.column_config.TimeColumn("Entrada 2 (partido)", format="HH:mm", step=300),
        "Salida 2": st.column_config.TimeColumn("Salida 2 (partido)", format="HH:mm", step=300),
    }


def _fila_editor(etiqueta: str, h, etiqueta_col: str, sede_defecto: str = "") -> dict:
    b = h.bloques if h else []
    if h is None:
        estado = "Descanso"
    elif h.vacaciones:
        estado = "Vacaciones"
    else:
        estado = "Trabaja"
    return {
        etiqueta_col: etiqueta,
        "Estado": estado,
        "Sede": (h.sede if h and h.sede else sede_defecto) or None,
        "Entrada 1": b[0][0] if len(b) > 0 else None,
        "Salida 1": b[0][1] if len(b) > 0 else None,
        "Entrada 2": b[1][0] if len(b) > 1 else None,
        "Salida 2": b[1][1] if len(b) > 1 else None,
    }


def _horario_de_editor(fila) -> "db.Horario | None":
    """Convierte una fila del editor en Horario (None = descanso)."""
    estado = str(fila.get("Estado") or "Descanso")
    sede_txt = fila.get("Sede")
    sede_txt = "" if sede_txt is None or (isinstance(sede_txt, float) and pd.isna(sede_txt)) else str(sede_txt)
    if estado == "Vacaciones":
        return db.Horario([], sede=sede_txt, estado=db.ESTADO_VACACIONES)
    if estado != "Trabaja":
        return None

    bloques = db.limpiar_bloques([
        (hora_valor(fila["Entrada 1"]), hora_valor(fila["Salida 1"])),
        (hora_valor(fila["Entrada 2"]), hora_valor(fila["Salida 2"])),
    ])
    return db.Horario(bloques, sede=sede_txt) if bloques else None


def editor_semana(clave: str, filas: list[dict], etiqueta_col: str, con_vacaciones: bool = True) -> pd.DataFrame:
    """Tabla editable de 7 dias con hasta 2 bloques. Escribe las horas como 08:00."""
    df = pd.DataFrame([normalizar_fila(f) | {etiqueta_col: f[etiqueta_col]} for f in filas],
                      columns=[etiqueta_col] + COLS_EDITOR)
    return st.data_editor(
        df, key=clave, hide_index=True, width="stretch", num_rows="fixed",
        column_config=_config_editor(etiqueta_col, con_vacaciones),
    )


COLS_HORA = ("Entrada 1", "Salida 1", "Entrada 2", "Salida 2")


def hora_valor(v) -> time | None:
    """
    Convierte a `time` lo que venga del editor. Al editar una celda a mano,
    Streamlit devuelve la hora como texto ('07:00:00'); si se mezclara texto
    con `time` en la misma columna, la tabla no se puede volver a dibujar.
    Nunca lanza error: lo que no se entienda queda en None.
    """
    if v is None or v is pd.NaT:
        return None
    if isinstance(v, time):
        return v
    try:
        if isinstance(v, float) and pd.isna(v):
            return None
        if isinstance(v, str):
            v = v.strip()
            if not v:
                return None
            try:
                return time.fromisoformat(v)
            except ValueError:
                pass
        return pd.Timestamp(v).time()
    except (ValueError, TypeError):
        return None


def normalizar_fila(fila: dict) -> dict:
    """Deja cada columna con el tipo que espera la tabla."""
    fila = dict(fila)
    for c in COLS_HORA:
        fila[c] = hora_valor(fila.get(c))
    estado = fila.get("Estado")
    fila["Estado"] = str(estado) if estado in ESTADOS_DIA else "Descanso"
    sede = fila.get("Sede")
    if sede is None or (isinstance(sede, float) and pd.isna(sede)) or not str(sede).strip():
        fila["Sede"] = None
    else:
        fila["Sede"] = str(sede)
    return fila


def estado_editor(clave_editor: str, filas_base: list[dict]) -> list[dict]:
    """
    Filas que el usuario tiene AHORA en la tabla: las filas base con las
    ediciones que aun no ha guardado. Asi 'copiar día' y 'relleno rápido'
    respetan lo que acaba de escribir.
    """
    estado = st.session_state.get(clave_editor)
    filas = [dict(f) for f in filas_base]
    if isinstance(estado, dict):
        for idx, cambios in (estado.get("edited_rows") or {}).items():
            try:
                i = int(idx)
            except (TypeError, ValueError):
                continue
            if 0 <= i < len(filas):
                filas[i].update(cambios)
    return [normalizar_fila(f) for f in filas]


def copiar_dia_ui(clave: str, etiquetas: list[str]):
    """
    Selector para copiar el horario de un día a otros.
    Devuelve (indice_origen, [indices_destino]) si se pulsó Copiar.
    """
    with st.expander("Copiar el horario de un día a otros"):
        st.caption("Útil cuando varios días tienen el mismo turno: llena uno y cópialo a los demás.")
        c1, c2 = st.columns([1, 2])
        origen = c1.selectbox("Copiar el día", range(7), format_func=lambda i: etiquetas[i], key=f"{clave}_or")
        destinos = c2.multiselect("a estos días", range(7), format_func=lambda i: etiquetas[i], key=f"{clave}_de",
                                  placeholder="Elige uno o varios días")
        if st.button("Copiar", key=f"{clave}_b", width="stretch", disabled=not destinos):
            return origen, [d for d in destinos if d != origen]
    return None


def relleno_rapido(clave: str):
    """Devuelve (bloques, dias_idx) si el usuario pulso 'Aplicar', si no None."""
    with st.expander("Relleno rápido"):
        c1, c2, c3, c4 = st.columns(4)
        e1 = c1.time_input("Entrada 1", value=time(8, 0), key=f"{clave}_e1", step=timedelta(minutes=15))
        s1 = c2.time_input("Salida 1", value=time(12, 0), key=f"{clave}_s1", step=timedelta(minutes=15))
        e2 = c3.time_input("Entrada 2", value=time(14, 0), key=f"{clave}_e2", step=timedelta(minutes=15))
        s2 = c4.time_input("Salida 2", value=time(21, 0), key=f"{clave}_s2", step=timedelta(minutes=15))
        partido = st.checkbox("Turno partido (usar los dos bloques)", value=True, key=f"{clave}_p")
        c5, c6 = st.columns([1, 2])
        sede = c5.selectbox("Sede", [""] + sedes_activas(), format_func=lambda x: x or "(sede base)", key=f"{clave}_sd")
        dias = c6.multiselect("Días", DIAS_ES, default=DIAS_ES[:6], key=f"{clave}_d")
        if st.button("Aplicar a los días elegidos", key=f"{clave}_b", width="stretch"):
            bloques = [(e1, s1)] + ([(e2, s2)] if partido else [])
            return db.Horario(bloques, sede=sede), [DIAS_ES.index(d) for d in dias]
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
    prefill = st.session_state.get(f"prefill_hor_{emp_id}")

    sede_base = str(empleados.set_index("id").loc[emp_id, "sede"] or "")

    # Filas base de la tabla: lo guardado, o el relleno pendiente. Tienen que ser
    # SIEMPRE las mismas mientras no cambie `ver`: si a st.data_editor se le pasan
    # datos distintos en cada rerun, Streamlit descarta las ediciones anteriores
    # y se va borrando lo que el usuario acaba de escribir.
    clave_ed = f"ed_hor_{emp_id}_{ver}"
    filas_base = []
    for d in range(7):
        h = prefill[d] if prefill is not None else actual.get(d)
        filas_base.append(_fila_editor(DIAS_ES[d], h, "Día", sede_base))

    def _estado_actual():
        """Lo que se ve ahora en la tabla: base + lo que escribió y aún no guarda."""
        return estado_editor(clave_ed, filas_base)

    def _aplicar_hor(nuevos: dict):
        st.session_state[f"prefill_hor_{emp_id}"] = nuevos
        st.session_state[f"ver_hor_{emp_id}"] = ver + 1
        st.rerun()

    r = relleno_rapido(f"rr_hor_{emp_id}")
    if r:
        h_nuevo, idx = r
        filas = _estado_actual()
        base = {d: _horario_de_editor(filas[d]) for d in range(7)}
        for d in idx:
            base[d] = h_nuevo
        _aplicar_hor(base)

    cd = copiar_dia_ui(f"cd_hor_{emp_id}", DIAS_ES)
    if cd:
        origen, destinos = cd
        filas = _estado_actual()
        base = {d: _horario_de_editor(filas[d]) for d in range(7)}
        for d in destinos:
            base[d] = base[origen]
        _aplicar_hor(base)

    otros = [n for n in nombres if nombres[n] != emp_id]
    if otros:
        c4, c5 = st.columns([2, 1])
        origen = c4.selectbox("Copiar horario base de", otros, index=None, placeholder="Elige empleado")
        if c5.button("Copiar", width="stretch", disabled=origen is None):
            db.copiar_horario(nombres[origen], emp_id)
            st.session_state.pop(f"prefill_hor_{emp_id}", None)
            st.session_state[f"ver_hor_{emp_id}"] = ver + 1
            st.success("Horario copiado.")
            st.rerun()

    editado = editor_semana(clave_ed, filas_base, "Día", con_vacaciones=False)
    if st.button("Guardar horario base", type="primary", width="stretch", key=f"g_hor_{emp_id}"):
        nuevos = {d: _horario_de_editor(editado.iloc[d]) for d in range(7)}
        db.guardar_horario(emp_id, nuevos)
        st.session_state.pop(f"prefill_hor_{emp_id}", None)
        st.session_state[f"ver_hor_{emp_id}"] = ver + 1
        st.success(f"Horario base de {sel} guardado.")
        st.rerun()

    if actual:
        st.caption("Horario base actual: " + " · ".join(
            f"{DIAS_ES[d][:3]} {h.texto(con_sede=True)}" for d, h in sorted(actual.items())
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
        "Los empleados la ven en *Registrar → Mi horario* y en la página *Horario semanal*."
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
    sede_base = str(empleados.set_index("id").loc[emp_id, "sede"] or "")
    turnos = db.turnos_rango(lunes, domingo, emp_id)
    semana = db.semana_empleado(emp_id, lunes, plantilla, turnos, sede_base)
    programada = any((emp_id, f) in turnos for f, _ in semana)
    if programada:
        st.info("Esta semana tiene programación propia. Los días marcados con ★ vienen de la programación; el resto, del horario base.")
    else:
        st.info("Esta semana no tiene programación propia: se muestra el horario base. Edita y guarda para programarla.")

    clave = f"{emp_id}_{lunes}"
    ver = st.session_state.get(f"ver_sem_{clave}", 0)
    prefill = st.session_state.get(f"prefill_sem_{clave}")

    # Filas base de la tabla (ver nota en admin_horarios: deben ser estables)
    clave_ed = f"ed_sem_{clave}_{ver}"
    etiquetas_sem = []
    filas_base = []
    for fecha, h in semana:
        if prefill is not None:
            h = prefill.get(fecha)
        estrella = " ★" if (emp_id, fecha) in turnos else ""
        etiquetas_sem.append(f"{DIAS_ES[fecha.weekday()]} {fecha:%d/%m}")
        filas_base.append(_fila_editor(f"{DIAS_ES[fecha.weekday()]} {fecha:%d/%m}{estrella}", h, "Fecha", sede_base))

    def _estado_actual():
        return estado_editor(clave_ed, filas_base)

    def _aplicar_sem(nuevos: dict):
        st.session_state[f"prefill_sem_{clave}"] = nuevos
        st.session_state[f"ver_sem_{clave}"] = ver + 1
        st.rerun()

    def _base_sem():
        filas = _estado_actual()
        return {lunes + timedelta(days=i): _horario_de_editor(filas[i]) for i in range(7)}

    r = relleno_rapido(f"rr_sem_{clave}")
    if r:
        h_nuevo, idx = r
        base = _base_sem()
        for d in idx:
            base[lunes + timedelta(days=d)] = h_nuevo
        _aplicar_sem(base)

    cd = copiar_dia_ui(f"cd_sem_{clave}", etiquetas_sem)
    if cd:
        origen, destinos = cd
        base = _base_sem()
        for d in destinos:
            base[lunes + timedelta(days=d)] = base[lunes + timedelta(days=origen)]
        _aplicar_sem(base)

    b1, b2 = st.columns(2)
    if b1.button("Copiar la semana anterior", width="stretch", key=f"cp_{clave}"):
        ant = db.semana_empleado(emp_id, lunes - timedelta(days=7), plantilla, sede_defecto=sede_base)
        st.session_state[f"prefill_sem_{clave}"] = {f + timedelta(days=7): h for f, h in ant}
        st.session_state[f"ver_sem_{clave}"] = ver + 1
        st.rerun()
    if b2.button("Volver al horario base (borrar programación)", width="stretch", key=f"rm_{clave}",
                 disabled=not programada):
        db.borrar_semana(emp_id, lunes)
        st.session_state.pop(f"prefill_sem_{clave}", None)
        st.session_state[f"ver_sem_{clave}"] = ver + 1
        st.success("Programación de la semana eliminada.")
        st.rerun()

    editado = editor_semana(clave_ed, filas_base, "Fecha")
    if st.button("Guardar programación de la semana", type="primary", width="stretch", key=f"g_sem_{clave}"):
        nuevos = {lunes + timedelta(days=i): _horario_de_editor(editado.iloc[i]) for i in range(7)}
        db.guardar_semana(emp_id, lunes, nuevos)
        st.session_state.pop(f"prefill_sem_{clave}", None)
        st.session_state[f"ver_sem_{clave}"] = ver + 1
        st.success(f"Semana del {lunes:%d/%m} programada para {sel}.")
        st.rerun()

    st.divider()
    st.subheader("Vista de toda la semana")
    sede_v = st.selectbox("Sede", ["Todas"] + sedes_activas(), key="adm_sede_vista")
    tabla = db.semana_todos(lunes, None if sede_v == "Todas" else sede_v)
    if tabla.empty:
        st.caption("Sin empleados activos.")
    else:
        st.dataframe(tabla, hide_index=True, width="stretch")


PLANTILLA_IMPORT = (
    "empleado,fecha,sede,entrada1,salida1,entrada2,salida2,estado\n"
    "Sebastian Huertas,2026-10-13,Gourmet,07:00,14:00,,,trabaja\n"
    "Marilyn Saba,2026-10-14,Gourmet,10:00,14:00,16:00,21:00,trabaja\n"
    "Sonia,2026-10-12,Gourmet,,,,,vacaciones\n"
    "Yeison Cuadrado,2026-10-18,Gourmet,,,,,descanso\n"
)


def _leer_csv_turnos(texto: str) -> pd.DataFrame:
    """Lee el CSV de importación y normaliza las columnas."""
    import io as _io

    df = pd.read_csv(_io.StringIO(texto), dtype=str).fillna("")
    df.columns = [c.strip().lower() for c in df.columns]
    faltan = {"empleado", "fecha"} - set(df.columns)
    if faltan:
        raise ValueError(f"Al archivo le faltan columnas: {', '.join(sorted(faltan))}")
    for c in ("sede", "entrada1", "salida1", "entrada2", "salida2", "estado"):
        if c not in df.columns:
            df[c] = ""
    for c in df.columns:
        df[c] = df[c].astype(str).str.strip()
    df["estado"] = df["estado"].str.lower().replace({"": "trabaja"})
    return df


def _fila_import_a_horario(fila) -> "db.Horario | None":
    estado = fila["estado"]
    if estado.startswith("vac"):
        return db.Horario([], sede=fila["sede"], estado=db.ESTADO_VACACIONES)
    if estado.startswith("desc") or estado in ("d", "libre"):
        return None
    bloques = db.limpiar_bloques([
        (hora_valor(fila["entrada1"]), hora_valor(fila["salida1"])),
        (hora_valor(fila["entrada2"]), hora_valor(fila["salida2"])),
    ])
    return db.Horario(bloques, sede=fila["sede"]) if bloques else None


def admin_importar():
    st.caption(
        "Carga de una vez la programación de varias personas y fechas. Útil para pasar el cuadro "
        "semanal completo sin escribir celda por celda. Lo que importes queda en *Programar semana* "
        "y se puede corregir allí después."
    )
    with st.expander("Formato del archivo"):
        st.markdown(
            "Un archivo **CSV** (se puede hacer en Excel → *Guardar como CSV*) con una fila por "
            "persona y día:\n\n"
            "- `empleado`: el nombre tal como está en la app\n"
            "- `fecha`: `AAAA-MM-DD`\n"
            "- `sede`: nombre de la sede (si se deja vacío, usa la sede base de la persona)\n"
            "- `entrada1` / `salida1`: el turno (`07:00`, `14:00`)\n"
            "- `entrada2` / `salida2`: el segundo bloque si es turno partido (vacío si no)\n"
            "- `estado`: `trabaja`, `descanso` o `vacaciones`"
        )
        st.code(PLANTILLA_IMPORT, language="csv")
        st.download_button("⬇️ Descargar plantilla", PLANTILLA_IMPORT, "plantilla_horarios.csv", "text/csv")

    archivo = st.file_uploader("Archivo CSV", type=["csv"], key="imp_csv")
    if archivo is None:
        return

    try:
        df = _leer_csv_turnos(archivo.getvalue().decode("utf-8-sig"))
    except Exception as e:
        st.error(f"No se pudo leer el archivo: {e}")
        return

    empleados = db.listar_empleados(solo_activos=False)
    por_nombre = {str(r.nombre).strip().lower(): int(r.id) for r in empleados.itertuples()}

    # --- Nombres que no coinciden: se mapean a mano -------------------------------
    sin_match = sorted({n for n in df["empleado"] if n.strip().lower() not in por_nombre})
    mapa_manual = {}
    if sin_match:
        st.warning(f"No encontré {len(sin_match)} nombre(s) en la app. Indícame a quién corresponde cada uno "
                   "(o deja *— omitir —* para no cargarlo).")
        opciones = ["— omitir —"] + empleados["nombre"].tolist()
        for n in sin_match:
            elegido = st.selectbox(f"«{n}» es:", opciones, key=f"map_{n}")
            if elegido != "— omitir —":
                mapa_manual[n] = int(empleados.set_index("nombre").loc[elegido, "id"])

    # --- Armar los turnos ---------------------------------------------------------
    turnos, problemas, vista = [], [], []
    for fila in df.to_dict("records"):
        nombre = fila["empleado"]
        emp_id = por_nombre.get(nombre.strip().lower()) or mapa_manual.get(nombre)
        if emp_id is None:
            continue
        try:
            fecha = pd.Timestamp(fila["fecha"]).date()
        except Exception:
            problemas.append(f"{nombre}: fecha inválida «{fila['fecha']}»")
            continue
        h = _fila_import_a_horario(fila)
        if fila["estado"] == "trabaja" and h is None:
            problemas.append(f"{nombre} {fecha:%d/%m}: dice «trabaja» pero no tiene horas → se cargará como descanso")
        turnos.append((emp_id, fecha, h))
        vista.append({
            "Empleado": nombre,
            "Fecha": f"{fecha:%d/%m/%Y}",
            "Día": DIAS_ES[fecha.weekday()][:3],
            "Sede": "" if h is None or h.vacaciones else h.sede,
            "Programado": h.texto() if h else "Descanso",
            "Jornada": fmt_hm(h.jornada_min) if h and not h.vacaciones else "",
        })

    if not turnos:
        st.info("No hay filas que se puedan cargar todavía.")
        return

    for p_ in problemas:
        st.warning(p_)

    st.subheader("Revisa antes de cargar")
    fechas = sorted({f for _, f, _ in turnos})
    personas = len({e for e, _, _ in turnos})
    st.caption(f"**{len(turnos)} días** · **{personas} personas** · del {fechas[0]:%d/%m/%Y} al {fechas[-1]:%d/%m/%Y}")
    st.dataframe(pd.DataFrame(vista), hide_index=True, width="stretch")

    st.warning("Al cargar se **reemplaza** la programación que ya exista en esas fechas para esas personas. "
               "Las marcaciones y las horas ya registradas no se tocan.")
    with st.form("form_import"):
        pwd = st.text_input("Confirma con la contraseña de administrador", type="password")
        if st.form_submit_button("Cargar programación", type="primary", width="stretch"):
            if not db.verificar_admin(pwd):
                st.error("Contraseña incorrecta. No se cargó nada.")
            else:
                n = db.guardar_turnos(turnos)
                st.success(f"Listo: se cargaron {n} días. Revísalos en *Programar semana*.")


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
            momento = r["fecha_hora"].to_pydatetime()
            emp_id_r = int(r["empleado_id"])
            hor_dia = db.horario_del_dia(emp_id_r, momento.date())
            sugerida = db.hora_programada(hor_dia, r["tipo"], momento)

            cc1, cc2 = st.columns([1, 2])
            with cc1:
                if r["foto"]:
                    mostrar_foto(r["foto"], width=180)
            with cc2:
                if hor_dia is None:
                    st.info("Ese día no tiene horario programado.")
                else:
                    st.markdown(
                        f"**Horario de ese día:** {hor_dia.texto()}"
                        + (f" · {hor_dia.sede}" if hor_dia.sede else "")
                    )
                if sugerida is not None:
                    dif = int((momento - sugerida).total_seconds() // 60)
                    signo = "después" if dif > 0 else "antes"
                    st.markdown(
                        f"Marcó a las **{momento:%H:%M}**; le correspondía **{sugerida:%H:%M}** "
                        + (f"({fmt_hm(abs(dif))} {signo})" if dif else "(a tiempo)")
                    )
                    if dif and st.button(f"⏱️ Ajustar a las {sugerida:%H:%M}", key=f"aj_{rid}", width="stretch"):
                        st.session_state[f"ajustar_{rid}"] = sugerida
                        st.rerun()

            ajuste = st.session_state.get(f"ajustar_{rid}")
            if ajuste is not None:
                st.warning(f"Se cambiará la marcación de **{momento:%H:%M}** a **{ajuste:%H:%M}**. "
                           "Queda constancia de la hora original en la nota.")
                k1, k2 = st.columns(2)
                if k1.button("Confirmar ajuste", type="primary", key=f"aj_si_{rid}", width="stretch"):
                    nota_prev = (r["nota"] or "").strip()
                    marca = f"Ajustado por administración (marcó {momento:%H:%M})"
                    nota_nueva = f"{nota_prev} · {marca}".strip(" ·") if nota_prev else marca
                    db.actualizar_registro(rid, r["tipo"], ajuste, nota_nueva)
                    st.session_state.pop(f"ajustar_{rid}", None)
                    st.success("Marcación ajustada.")
                    st.rerun()
                if k2.button("Cancelar", key=f"aj_no_{rid}", width="stretch"):
                    st.session_state.pop(f"ajustar_{rid}", None)
                    st.rerun()

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
    st.caption("Para quien olvidó marcar. La app propone la hora que le correspondía según su horario.")
    if empleados.empty:
        return

    nombres = {r.nombre: int(r.id) for r in empleados.itertuples()}
    c1, c2 = st.columns(2)
    e = c1.selectbox("Empleado", list(nombres), key="man_emp")
    t = c2.radio("Tipo", [TIPO_ENTRADA, TIPO_SALIDA], horizontal=True, key="man_tipo")
    c3, c4 = st.columns(2)
    f = c3.date_input("Fecha", value=hoy, format="DD/MM/YYYY", key="man_fecha")

    hor_man = db.horario_del_dia(nombres[e], f)
    prop = db.hora_programada(hor_man, t, datetime.combine(f, time(12, 0)))
    if hor_man is None:
        c4.caption("Ese día no tiene horario programado.")
    else:
        c4.caption(f"Horario de ese día: **{hor_man.texto()}**")

    with st.form("nuevo_reg"):
        h = st.time_input("Hora", value=(prop.time() if prop else time(8, 0)), step=timedelta(minutes=1),
                          key=f"man_hora_{nombres[e]}_{f}_{t}")
        nota = st.text_input("Nota (motivo)", placeholder="Ej: olvidó marcar, celular sin batería")
        if st.form_submit_button("Agregar", width="stretch"):
            db.crear_registro(nombres[e], t, datetime.combine(f, h), "",
                              nota or "Agregada por administración")
            st.success(f"Marcación agregada: {e} · {t} · {f:%d/%m} {h:%H:%M}")
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
        gracia = st.number_input(
            "Gracia después de la salida (minutos)", min_value=0, max_value=180, value=db.gracia_salida_min(),
            help="Minutos de más al día que todavía son parte del turno y NO suman. Es UNA sola gabela "
                 "diaria, aunque el turno sea partido. Ej.: jornada de 7 h con 40 min → las extras "
                 "empiezan a los 7 h 40; quien esté 8 h suma 20 min, se haya quedado de más al final "
                 "o antes del descanso.",
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
            db.set_config("gracia_salida_min", int(gracia))
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

    st.subheader("Limpieza de fotos")
    st.caption(
        "Supabase gratis guarda hasta 1 GB de fotos. Una vez liquidado un mes, puedes borrar sus fotos: "
        "las marcaciones y las horas **se conservan**, solo se elimina la imagen. Esto no se puede deshacer."
    )
    try:
        meses = db.meses_con_fotos()
    except Exception as e:
        meses = []
        st.warning(f"No se pudo leer el almacén de fotos: {e}")
    if not meses:
        st.caption("No hay fotos guardadas.")
    else:
        total_mb = sum(m["mb"] for m in meses)
        st.dataframe(pd.DataFrame(meses).rename(columns={"mes": "Mes", "fotos": "Fotos", "mb": "MB"}),
                     hide_index=True, width="stretch")
        st.progress(min(total_mb / 1024, 1.0), text=f"Usado: {total_mb:.0f} MB de 1024 MB")
        mes_actual = db.ahora().strftime("%Y-%m")
        borrables = [m["mes"] for m in meses if m["mes"] < mes_actual]
        if not borrables:
            st.caption("Solo hay fotos del mes en curso; no se pueden borrar todavía.")
        else:
            c1, c2 = st.columns([2, 1])
            mes_sel = c1.selectbox("Mes a limpiar", borrables, index=0, key="mes_limpiar",
                                   help="Solo meses anteriores al actual.")
            if c2.button("Borrar fotos del mes", width="stretch", key="btn_limpiar"):
                st.session_state["confirmar_limpiar"] = mes_sel
            if st.session_state.get("confirmar_limpiar") == mes_sel:
                n = next(m["fotos"] for m in meses if m["mes"] == mes_sel)
                st.warning(f"Se van a borrar **{n} fotos** de **{mes_sel}**. Las marcaciones quedan. "
                           "Esto no se puede deshacer.")
                with st.form("form_limpiar", clear_on_submit=True):
                    pwd = st.text_input("Confirma con la contraseña de administrador", type="password")
                    k1, k2 = st.columns(2)
                    ok = k1.form_submit_button("Sí, borrar", type="primary", width="stretch")
                    cancelar = k2.form_submit_button("Cancelar", width="stretch")
                if cancelar:
                    st.session_state.pop("confirmar_limpiar", None)
                    st.rerun()
                if ok:
                    if not db.verificar_admin(pwd):
                        st.error("Contraseña incorrecta. No se borró nada.")
                    else:
                        borradas = db.borrar_fotos_mes(mes_sel)
                        foto_bytes.clear()
                        st.session_state.pop("confirmar_limpiar", None)
                        st.success(f"Listo: {borradas} fotos de {mes_sel} eliminadas.")
                        st.rerun()

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
    st.Page(pagina_pendientes, title="Sin marcar", icon="⚠️", url_path="pendientes"),
    st.Page(pagina_reporte, title="Reporte de extras", icon="📊", url_path="reporte"),
    st.Page(pagina_admin, title="Administración", icon="⚙️", url_path="admin"),
])
pg.run()

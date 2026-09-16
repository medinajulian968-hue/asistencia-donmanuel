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
    horario = db.horario_empleado(emp_id)
    hor_hoy = horario.get(hoy.weekday())
    marcas_hoy = db.registros_del_dia(emp_id, hoy)

    if hor_hoy:
        txt_horario = (f"{hora_t(hor_hoy.hora_entrada)} – {hora_t(hor_hoy.hora_salida)} "
                       f"(jornada {fmt_hm(hor_hoy.jornada_min)})")
    else:
        txt_horario = "Sin horario programado (día no laboral)"

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
        mostrar_resumen_hoy(emp_id, nombre, momento_ok.date(), horario)
        mostrar_foto(ruta_ok, width=220)

    # --- Marcaciones de hoy ---------------------------------------------
    marcas_hoy = db.registros_del_dia(emp_id, hoy)
    if marcas_hoy:
        with st.expander("Ver mis marcaciones de hoy", expanded=False):
            for m in marcas_hoy:
                st.markdown(f"{chip(m['tipo'])} &nbsp; {hora(m['fecha_hora'])}", unsafe_allow_html=True)


def mostrar_resumen_hoy(emp_id: int, nombre: str, fecha: date, horario):
    marcas = [(m["tipo"], m["fecha_hora"]) for m in db.registros_del_dia(emp_id, fecha)]
    r = db.resumir_dia(emp_id, nombre, fecha, marcas, horario, db.tolerancia_min(), db.contar_entrada_anticipada())
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
    c1, c2, c3 = st.columns([1, 1, 1.3])
    desde = c1.date_input("Desde", value=hoy.replace(day=1), format="DD/MM/YYYY")
    hasta = c2.date_input("Hasta", value=hoy, format="DD/MM/YYYY")
    empleados = db.listar_empleados(solo_activos=False)
    opciones = {"Todos": None} | {r.nombre: int(r.id) for r in empleados.itertuples()}
    sel = c3.selectbox("Empleado", list(opciones))
    emp_id = opciones[sel]

    if desde > hasta:
        st.error("La fecha 'Desde' no puede ser mayor que 'Hasta'.")
        return

    resumen = db.reporte_extras(desde, hasta, emp_id)
    registros = db.listar_registros(desde, hasta, emp_id)

    if resumen.empty:
        st.info("No hay marcaciones en ese rango.")
        return

    # --- Totales -----------------------------------------------------------
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Días con marcación", len(resumen))
    m2.metric("Horas trabajadas", fmt_hm(resumen["minutos_trabajados"].sum()))
    m3.metric("Horas extra", fmt_hm(resumen["extra_total_min"].sum()))
    m4.metric("Tardanzas", fmt_hm(resumen["tardanza_min"].sum()))

    st.download_button(
        "⬇️ Descargar Excel",
        data=db.exportar_excel(resumen, registros),
        file_name=f"extras_{desde:%Y%m%d}_{hasta:%Y%m%d}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        width="stretch",
    )

    # --- Totales por empleado ------------------------------------------------
    st.subheader("Totales por empleado")
    tot = resumen.groupby("nombre", as_index=False).agg(
        dias=("fecha", "count"),
        trabajado=("minutos_trabajados", "sum"),
        tardanza=("tardanza_min", "sum"),
        extra=("extra_total_min", "sum"),
    )
    tot_vista = pd.DataFrame({
        "Empleado": tot["nombre"],
        "Días": tot["dias"],
        "Horas trabajadas": tot["trabajado"].map(fmt_hm),
        "Tardanza": tot["tardanza"].map(fmt_hm),
        "Horas extra": tot["extra"].map(fmt_hm),
        "Extra (min)": tot["extra"],
    })
    st.dataframe(tot_vista, hide_index=True, width="stretch")

    # --- Detalle por dia ------------------------------------------------------
    st.subheader("Detalle por día")
    det = pd.DataFrame({
        "Empleado": resumen["nombre"],
        "Fecha": pd.to_datetime(resumen["fecha"]).dt.strftime("%d/%m/%Y"),
        "Día": resumen["dia"],
        "Horario": [
            f"{hora_t(e)} – {hora_t(s)}" if e else "No programado"
            for e, s in zip(resumen["programada_entrada"], resumen["programada_salida"])
        ],
        "Jornada": resumen["jornada_min"].map(fmt_hm),
        "Entrada": resumen["entrada_real"].map(hora),
        "Salida": resumen["salida_real"].map(hora),
        "Bloques": resumen["bloques"],
        "Trabajado": resumen["minutos_trabajados"].map(fmt_hm),
        "Tardanza": resumen["tardanza_min"].map(fmt_hm),
        "Faltante": resumen["faltante_min"].map(fmt_hm),
        "Extra": resumen["extra_total_min"].map(fmt_hm),
        "Observación": resumen["observacion"],
    })
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
# PAGINA: ADMINISTRACION
# ---------------------------------------------------------------------------

def pagina_admin():
    st.title("Administración")
    if not pedir_admin():
        return

    t_emp, t_hor, t_reg, t_cfg = st.tabs(["👥 Empleados", "🕒 Horarios", "📋 Marcaciones", "⚙️ Configuración"])
    with t_emp:
        admin_empleados()
    with t_hor:
        admin_horarios()
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
        "Marca los días que trabaja, la hora de entrada (para calcular tardanzas), la hora normal de "
        "salida y las **horas de jornada** que debe cumplir ese día. Lo trabajado por encima de la "
        "jornada es extra. Sirve para turno corrido o partido: cada quien marca entrada/salida las "
        "veces que salga y vuelva, y la app suma solo los bloques trabajados."
    )

    # Relleno rapido
    with st.expander("Relleno rápido"):
        c1, c2, c3, c4 = st.columns([1, 1, 0.8, 1.4])
        q_ent = c1.time_input("Entrada", value=time(8, 0), key="q_ent", step=timedelta(minutes=15))
        q_sal = c2.time_input("Salida", value=time(17, 0), key="q_sal", step=timedelta(minutes=15))
        q_jor = c3.number_input("Jornada (h)", min_value=0.0, max_value=24.0, value=8.0, step=0.5, key="q_jor")
        q_dias = c4.multiselect("Días", DIAS_ES, default=DIAS_ES[:5], key="q_dias")
        if st.button("Aplicar a los días elegidos", width="stretch"):
            for d in q_dias:
                i = DIAS_ES.index(d)
                st.session_state[f"h_on_{emp_id}_{i}"] = True
                st.session_state[f"h_ent_{emp_id}_{i}"] = q_ent
                st.session_state[f"h_sal_{emp_id}_{i}"] = q_sal
                st.session_state[f"h_jor_{emp_id}_{i}"] = float(q_jor)
            st.rerun()

        otros = [n for n in nombres if nombres[n] != emp_id]
        if otros:
            c4, c5 = st.columns([2, 1])
            origen = c4.selectbox("Copiar horario de", otros, index=None, placeholder="Elige empleado")
            if c5.button("Copiar", width="stretch", disabled=origen is None):
                db.copiar_horario(nombres[origen], emp_id)
                for i in range(7):
                    for k in ("h_on", "h_ent", "h_sal", "h_jor"):
                        st.session_state.pop(f"{k}_{emp_id}_{i}", None)
                st.success("Horario copiado.")
                st.rerun()

    # Los widgets se alimentan solo desde session_state (inicializado desde la
    # BD la primera vez) para que el "relleno rapido" pueda modificarlos.
    for i in range(7):
        if f"h_on_{emp_id}_{i}" not in st.session_state:
            h = actual.get(i)
            st.session_state[f"h_on_{emp_id}_{i}"] = h is not None
            st.session_state[f"h_ent_{emp_id}_{i}"] = h.hora_entrada if h else time(8, 0)
            st.session_state[f"h_sal_{emp_id}_{i}"] = h.hora_salida if h else time(17, 0)
            st.session_state[f"h_jor_{emp_id}_{i}"] = round(h.jornada_min / 60, 2) if h else 8.0

    with st.form(f"form_hor_{emp_id}"):
        h1, h2, h3, h4 = st.columns([1.3, 1, 1, 0.8])
        h1.caption("Día")
        h2.caption("Entrada")
        h3.caption("Salida")
        h4.caption("Jornada (h)")
        nuevos: dict[int, tuple[time, time, int] | None] = {}
        for i, dia in enumerate(DIAS_ES):
            c1, c2, c3, c4 = st.columns([1.3, 1, 1, 0.8])
            on = c1.checkbox(dia, key=f"h_on_{emp_id}_{i}")
            ent = c2.time_input("Entrada", key=f"h_ent_{emp_id}_{i}",
                                step=timedelta(minutes=5), label_visibility="collapsed")
            sal = c3.time_input("Salida", key=f"h_sal_{emp_id}_{i}",
                                step=timedelta(minutes=5), label_visibility="collapsed")
            jor = c4.number_input("Jornada", key=f"h_jor_{emp_id}_{i}", min_value=0.0, max_value=24.0,
                                  step=0.5, label_visibility="collapsed")
            nuevos[i] = (ent, sal, int(round(jor * 60))) if on else None
        if st.form_submit_button("Guardar horario", type="primary", width="stretch"):
            db.guardar_horario(emp_id, nuevos)
            st.success(f"Horario de {sel} guardado.")
            st.rerun()

    if actual:
        st.caption("Horario actual: " + " · ".join(
            f"{DIAS_ES[d][:3]} {hora_t(h.hora_entrada)}–{hora_t(h.hora_salida)} ({fmt_hm(h.jornada_min)})"
            for d, h in sorted(actual.items())
        ))
    else:
        st.warning("Este empleado no tiene horario. Sin horario, todo lo que trabaje se contará como extra.")


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
        if st.form_submit_button("Guardar reglas", width="stretch"):
            db.set_config("tolerancia_min", int(tol))
            db.set_config("contar_entrada_anticipada", "1" if antes else "0")
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
    st.Page(pagina_reporte, title="Reporte de extras", icon="📊", url_path="reporte"),
    st.Page(pagina_admin, title="Administración", icon="⚙️", url_path="admin"),
])
pg.run()

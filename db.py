# -*- coding: utf-8 -*-
"""
db.py
=====
Capa de datos del control de asistencia - MERCADOS DON MANUEL.

Todo lo que toca la base de datos (Supabase: Postgres + Storage) y el calculo
de horas extra vive aqui. app.py solo arma la interfaz.

Tablas (se crean con supabase_setup.sql):
  empleados  -> quienes pueden registrarse (nombre, cargo, PIN opcional)
  horarios   -> horario por empleado y dia de la semana (0=lunes ... 6=domingo)
  registros  -> cada marcacion: entrada o salida, hora exacta y foto
  config     -> parametros (contrasena admin, tolerancia, etc.)
Bucket de Storage:
  fotos      -> las fotos de cada marcacion (AAAA-MM/archivo.jpg)

Credenciales: se leen de st.secrets (Streamlit Cloud o .streamlit/secrets.toml)
o de las variables de entorno SUPABASE_URL y SUPABASE_KEY.

Las horas se guardan en hora local (zona TIMEZONE, por defecto America/Bogota)
sin zona horaria, porque el servidor de Streamlit Cloud esta en UTC.
"""

from __future__ import annotations

import hashlib
import io
import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from functools import lru_cache
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

import pandas as pd
from supabase import Client, create_client

DIAS_ES = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
DIAS_CORTO = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]

TIPO_ENTRADA = "entrada"
TIPO_SALIDA = "salida"
BUCKET_FOTOS = "fotos"

CONFIG_DEFAULT = {
    "admin_password": hashlib.sha256(b"admin").hexdigest(),
    "tolerancia_min": "10",            # minutos de gracia antes de contar extra/tardanza
    "contar_entrada_anticipada": "0",  # 1 = llegar antes de la hora tambien suma extra
}


class ConfiguracionFaltante(Exception):
    """No hay credenciales de Supabase."""


# ---------------------------------------------------------------------------
# CONEXION
# ---------------------------------------------------------------------------

def _secreto(nombre: str, defecto: str = "") -> str:
    """Busca primero en st.secrets y luego en variables de entorno."""
    try:
        import streamlit as st

        if nombre in st.secrets:
            return str(st.secrets[nombre])
    except Exception:
        pass
    return os.environ.get(nombre, defecto)


@lru_cache(maxsize=1)
def cliente() -> Client:
    url = _secreto("SUPABASE_URL").strip().strip("<>\"' ")
    key = _secreto("SUPABASE_KEY").strip().strip("<>\"' ")
    if not url or not key:
        raise ConfiguracionFaltante(
            "Faltan SUPABASE_URL y SUPABASE_KEY. Ponlos en los Secrets de Streamlit Cloud "
            "o en el archivo .streamlit/secrets.toml (ver DESPLIEGUE.md)."
        )
    # Solo se necesita https://xxxx.supabase.co ; si pegaron la URL con
    # /rest/v1 u otra ruta al final, se recorta.
    if not url.startswith("http"):
        url = "https://" + url
    partes = urlsplit(url)
    url = f"{partes.scheme}://{partes.netloc}"
    return create_client(url, key)


@lru_cache(maxsize=1)
def zona() -> ZoneInfo:
    return ZoneInfo(_secreto("TIMEZONE", "America/Bogota"))


def ahora() -> datetime:
    """Hora local actual (sin tzinfo), independiente de donde corra el servidor."""
    return datetime.now(zona()).replace(tzinfo=None, microsecond=0)


def inicializar() -> None:
    """Verifica la conexion y asegura los valores de configuracion por defecto."""
    sb = cliente()
    existentes = {f["clave"] for f in sb.table("config").select("clave").execute().data}
    faltan = [{"clave": k, "valor": v} for k, v in CONFIG_DEFAULT.items() if k not in existentes]
    if faltan:
        sb.table("config").insert(faltan).execute()


# ---------------------------------------------------------------------------
# UTILIDADES DE CONVERSION
# ---------------------------------------------------------------------------

def _parse_dt(txt: str) -> datetime:
    return datetime.fromisoformat(txt).replace(tzinfo=None)


def _parse_hora(txt: str) -> time:
    h, m = txt.split(":")[:2]
    return time(int(h), int(m))


def _iso(dt: datetime) -> str:
    return dt.replace(tzinfo=None).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# CONFIG
# ---------------------------------------------------------------------------

def get_config(clave: str) -> str:
    data = cliente().table("config").select("valor").eq("clave", clave).limit(1).execute().data
    return data[0]["valor"] if data else CONFIG_DEFAULT.get(clave, "")


def set_config(clave: str, valor) -> None:
    cliente().table("config").upsert({"clave": clave, "valor": str(valor)}, on_conflict="clave").execute()


def _hash(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def verificar_admin(password: str) -> bool:
    return _hash(password) == get_config("admin_password")


def cambiar_password_admin(nueva: str) -> None:
    set_config("admin_password", _hash(nueva))


def tolerancia_min() -> int:
    try:
        return int(get_config("tolerancia_min"))
    except ValueError:
        return 0


def contar_entrada_anticipada() -> bool:
    return get_config("contar_entrada_anticipada") == "1"


# ---------------------------------------------------------------------------
# EMPLEADOS
# ---------------------------------------------------------------------------

COLS_EMPLEADO = ["id", "nombre", "cargo", "pin", "activo", "creado_en"]


def listar_empleados(solo_activos: bool = True) -> pd.DataFrame:
    q = cliente().table("empleados").select(",".join(COLS_EMPLEADO))
    if solo_activos:
        q = q.eq("activo", True)
    data = q.order("nombre").execute().data
    df = pd.DataFrame(data, columns=COLS_EMPLEADO)
    if not df.empty:
        df["activo"] = df["activo"].astype(bool)
        df["cargo"] = df["cargo"].fillna("")
        df["pin"] = df["pin"].fillna("")
        # Orden sin distinguir mayusculas/acentos como hacia SQLite
        df = df.sort_values("nombre", key=lambda s: s.str.lower()).reset_index(drop=True)
    return df


def obtener_empleado(empleado_id: int) -> dict | None:
    data = cliente().table("empleados").select("*").eq("id", empleado_id).limit(1).execute().data
    return data[0] if data else None


def crear_empleado(nombre: str, cargo: str = "", pin: str = "") -> int:
    nombre = nombre.strip()
    if not nombre:
        raise ValueError("El nombre no puede estar vacío.")
    data = (
        cliente()
        .table("empleados")
        .insert({"nombre": nombre, "cargo": cargo.strip(), "pin": pin.strip(), "activo": True,
                 "creado_en": _iso(ahora())})
        .execute()
        .data
    )
    return int(data[0]["id"])


def actualizar_empleado(empleado_id: int, nombre: str, cargo: str, pin: str, activo: bool) -> None:
    cliente().table("empleados").update(
        {"nombre": nombre.strip(), "cargo": cargo.strip(), "pin": pin.strip(), "activo": bool(activo)}
    ).eq("id", empleado_id).execute()


def eliminar_empleado(empleado_id: int) -> None:
    """Borra el empleado, sus horarios y sus registros (las fotos quedan en Storage)."""
    cliente().table("empleados").delete().eq("id", empleado_id).execute()


def verificar_pin(empleado_id: int, pin: str) -> bool:
    emp = obtener_empleado(empleado_id)
    if emp is None:
        return False
    if not emp.get("pin"):
        return True  # sin PIN configurado -> no se exige
    return emp["pin"] == pin.strip()


# ---------------------------------------------------------------------------
# HORARIOS
# ---------------------------------------------------------------------------

@dataclass
class Horario:
    dia_semana: int
    hora_entrada: time
    hora_salida: time
    jornada_min: int  # minutos que debe trabajar ese dia (sin contar descansos)

    @property
    def cruza_medianoche(self) -> bool:
        return self.hora_salida <= self.hora_entrada


def duracion_min(entrada: time, salida: time) -> int:
    """Minutos entre dos horas; si la salida es menor, se asume que cruza medianoche."""
    e = entrada.hour * 60 + entrada.minute
    s_ = salida.hour * 60 + salida.minute
    return s_ - e if s_ > e else s_ + 24 * 60 - e


def horario_empleado(empleado_id: int) -> dict[int, Horario]:
    """Devuelve {dia_semana: Horario} solo para los dias que trabaja."""
    data = (
        cliente().table("horarios").select("dia_semana,hora_entrada,hora_salida,jornada_min")
        .eq("empleado_id", empleado_id).execute().data
    )
    out = {}
    for f in data:
        ent, sal = _parse_hora(f["hora_entrada"]), _parse_hora(f["hora_salida"])
        jor = f.get("jornada_min") or duracion_min(ent, sal)
        out[f["dia_semana"]] = Horario(f["dia_semana"], ent, sal, int(jor))
    return out


def guardar_horario(empleado_id: int, dias: dict[int, tuple[time, time, int] | None]) -> None:
    """dias = {dia_semana: (entrada, salida, jornada_min)} o None si ese dia no trabaja."""
    sb = cliente()
    sb.table("horarios").delete().eq("empleado_id", empleado_id).execute()
    filas = []
    for dia, valor in dias.items():
        if valor is None:
            continue
        ent, sal, jor = valor
        filas.append({
            "empleado_id": empleado_id, "dia_semana": dia,
            "hora_entrada": ent.strftime("%H:%M"), "hora_salida": sal.strftime("%H:%M"),
            "jornada_min": int(jor) if jor else duracion_min(ent, sal),
        })
    if filas:
        sb.table("horarios").insert(filas).execute()


def copiar_horario(origen_id: int, destino_id: int) -> None:
    hor = horario_empleado(origen_id)
    guardar_horario(destino_id, {d: (h.hora_entrada, h.hora_salida, h.jornada_min) for d, h in hor.items()})


# ---------------------------------------------------------------------------
# REGISTROS Y FOTOS
# ---------------------------------------------------------------------------

def guardar_foto(empleado_id: int, tipo: str, momento: datetime, contenido: bytes) -> str:
    """Reduce la foto, la sube al bucket y devuelve su ruta (AAAA-MM/archivo.jpg)."""
    from PIL import Image, ImageOps

    try:  # fotos HEIC de iPhone, si esta instalado pillow-heif
        from pillow_heif import register_heif_opener
        register_heif_opener()
    except ImportError:
        pass

    img = Image.open(io.BytesIO(contenido))
    img = ImageOps.exif_transpose(img).convert("RGB")
    img.thumbnail((900, 900))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82, optimize=True)

    ruta = f"{momento.strftime('%Y-%m')}/{momento.strftime('%Y%m%d_%H%M%S')}_emp{empleado_id}_{tipo}.jpg"
    cliente().storage.from_(BUCKET_FOTOS).upload(
        ruta, buf.getvalue(), {"content-type": "image/jpeg", "upsert": "true"}
    )
    return ruta


def leer_foto(ruta: str) -> bytes | None:
    """Descarga la foto del bucket; None si no existe."""
    if not ruta:
        return None
    try:
        return cliente().storage.from_(BUCKET_FOTOS).download(ruta)
    except Exception:
        return None


def crear_registro(empleado_id: int, tipo: str, momento: datetime, foto: str = "", nota: str = "") -> int:
    if tipo not in (TIPO_ENTRADA, TIPO_SALIDA):
        raise ValueError("Tipo de registro inválido.")
    data = (
        cliente().table("registros")
        .insert({
            "empleado_id": empleado_id,
            "tipo": tipo,
            "fecha": momento.strftime("%Y-%m-%d"),
            "fecha_hora": _iso(momento),
            "foto": foto,
            "nota": nota,
            "creado_en": _iso(ahora()),
        })
        .execute().data
    )
    return int(data[0]["id"])


def actualizar_registro(registro_id: int, tipo: str, momento: datetime, nota: str) -> None:
    cliente().table("registros").update({
        "tipo": tipo, "fecha": momento.strftime("%Y-%m-%d"), "fecha_hora": _iso(momento), "nota": nota,
    }).eq("id", registro_id).execute()


def eliminar_registro(registro_id: int) -> None:
    cliente().table("registros").delete().eq("id", registro_id).execute()


def _normalizar_registro(f: dict) -> dict:
    f = dict(f)
    f["fecha_hora"] = _parse_dt(f["fecha_hora"])
    f["foto"] = f.get("foto") or ""
    f["nota"] = f.get("nota") or ""
    return f


def registros_del_dia(empleado_id: int, fecha: date) -> list[dict]:
    data = (
        cliente().table("registros").select("*")
        .eq("empleado_id", empleado_id).eq("fecha", fecha.strftime("%Y-%m-%d"))
        .order("fecha_hora").execute().data
    )
    return [_normalizar_registro(f) for f in data]


def ultimo_registro(empleado_id: int) -> dict | None:
    data = (
        cliente().table("registros").select("*")
        .eq("empleado_id", empleado_id).order("fecha_hora", desc=True).limit(1).execute().data
    )
    return _normalizar_registro(data[0]) if data else None


def tipo_sugerido(empleado_id: int, momento: datetime) -> str:
    """Si el ultimo movimiento fue una entrada sin salida -> toca salida; si no -> entrada."""
    ult = ultimo_registro(empleado_id)
    if ult is None:
        return TIPO_ENTRADA
    if ult["tipo"] == TIPO_ENTRADA:
        # Una entrada de hace mas de 20 h sin salida se considera olvidada.
        return TIPO_SALIDA if momento - ult["fecha_hora"] < timedelta(hours=20) else TIPO_ENTRADA
    return TIPO_ENTRADA


COLS_REGISTRO = ["id", "empleado_id", "nombre", "tipo", "fecha", "fecha_hora", "foto", "nota"]


def listar_registros(desde: date, hasta: date, empleado_id: int | None = None) -> pd.DataFrame:
    q = (
        cliente().table("registros")
        .select("id,empleado_id,tipo,fecha,fecha_hora,foto,nota,empleados(nombre)")
        .gte("fecha", desde.strftime("%Y-%m-%d")).lte("fecha", hasta.strftime("%Y-%m-%d"))
    )
    if empleado_id is not None:
        q = q.eq("empleado_id", empleado_id)
    data = q.order("fecha_hora").execute().data
    filas = []
    for f in data:
        f = dict(f)
        f["nombre"] = (f.pop("empleados") or {}).get("nombre", "")
        filas.append(f)
    df = pd.DataFrame(filas, columns=COLS_REGISTRO)
    if not df.empty:
        df["fecha_hora"] = pd.to_datetime(df["fecha_hora"]).dt.tz_localize(None)
        df["foto"] = df["foto"].fillna("")
        df["nota"] = df["nota"].fillna("")
    return df


# ---------------------------------------------------------------------------
# CALCULO DE EXTRAS
# ---------------------------------------------------------------------------

@dataclass
class ResumenDia:
    empleado_id: int
    nombre: str
    fecha: date
    dia_semana: int
    programada_entrada: time | None
    programada_salida: time | None
    jornada_min: int
    entrada_real: datetime | None
    salida_real: datetime | None
    bloques: int
    minutos_trabajados: int
    tardanza_min: int
    extra_total_min: int
    faltante_min: int
    observacion: str


def _minutos(delta: timedelta) -> int:
    return int(delta.total_seconds() // 60)


def _aplicar_tolerancia(minutos: int, tolerancia: int) -> int:
    """Si no supera la tolerancia, no cuenta. Si la supera, cuentan todos los minutos."""
    return minutos if minutos > tolerancia else 0


def _sesiones(marcas: list[tuple[str, datetime]]) -> tuple[list[tuple[datetime, datetime]], bool, bool]:
    """
    Empareja entradas con salidas en orden cronologico: entrada + salida = un bloque.
    Devuelve (bloques, hay_entrada_sin_salida, hay_salida_sin_entrada).
    Una entrada repetida sin salida en medio se ignora (se conserva la primera).
    """
    bloques = []
    abierta = None
    salida_suelta = False
    for tipo, m in sorted(marcas, key=lambda x: x[1]):
        if tipo == TIPO_ENTRADA:
            if abierta is None:
                abierta = m
        else:
            if abierta is not None and m > abierta:
                bloques.append((abierta, m))
                abierta = None
            else:
                salida_suelta = True
    return bloques, abierta is not None, salida_suelta


def resumir_dia(
    empleado_id: int,
    nombre: str,
    fecha: date,
    marcas: list[tuple[str, datetime]],
    horario: dict[int, Horario],
    tolerancia: int,
    contar_antes: bool,
) -> ResumenDia:
    """
    Calcula el resumen de un dia a partir de las marcaciones.

    Reglas:
      - Las marcaciones se emparejan entrada+salida en bloques (sirve para
        turno partido: entrada, salida, entrada, salida...).
      - Trabajado = suma de los bloques. Los descansos no cuentan.
      - Extra = trabajado - jornada programada (si supera la tolerancia).
      - Tardanza = primera entrada vs hora de entrada programada.
      - Si contar_antes es False, el tiempo antes de la hora de entrada
        programada no se cuenta como trabajado.
      - Dia sin horario: todo lo trabajado es extra.
    """
    bloques, sin_salida, sin_entrada = _sesiones(marcas)
    entradas = [m for t, m in marcas if t == TIPO_ENTRADA]
    salidas = [m for t, m in marcas if t == TIPO_SALIDA]
    entrada_real = min(entradas) if entradas else None
    salida_real = max(salidas) if salidas else None

    dia = fecha.weekday()
    hor = horario.get(dia)
    obs = []
    if sin_salida:
        obs.append("Sin salida")
    if sin_entrada:
        obs.append("Sin entrada")

    tardanza = extra = faltante = 0
    jornada = hor.jornada_min if hor else 0

    if hor is None:
        trabajados = sum(_minutos(s_ - e) for e, s_ in bloques)
        if trabajados:
            extra = trabajados
            obs.append("Día no programado")
    else:
        prog_ent_dt = datetime.combine(fecha, hor.hora_entrada)
        # Recortar lo trabajado antes de la hora de entrada si no debe contar
        recortados = []
        for e, s_ in bloques:
            if not contar_antes and e < prog_ent_dt:
                e = min(prog_ent_dt, s_)
            recortados.append((e, s_))
        trabajados = sum(_minutos(s_ - e) for e, s_ in recortados)

        if entrada_real and entrada_real > prog_ent_dt:
            tardanza = _aplicar_tolerancia(_minutos(entrada_real - prog_ent_dt), tolerancia)

        if trabajados > jornada:
            extra = _aplicar_tolerancia(trabajados - jornada, tolerancia)
        elif bloques and not sin_salida and trabajados < jornada:
            faltante = _aplicar_tolerancia(jornada - trabajados, tolerancia)
            if faltante:
                obs.append("Jornada incompleta")

    return ResumenDia(
        empleado_id=empleado_id,
        nombre=nombre,
        fecha=fecha,
        dia_semana=dia,
        programada_entrada=hor.hora_entrada if hor else None,
        programada_salida=hor.hora_salida if hor else None,
        jornada_min=jornada,
        entrada_real=entrada_real,
        salida_real=salida_real,
        bloques=len(bloques),
        minutos_trabajados=trabajados,
        tardanza_min=tardanza,
        extra_total_min=extra,
        faltante_min=faltante,
        observacion=", ".join(obs),
    )


def reporte_extras(desde: date, hasta: date, empleado_id: int | None = None) -> pd.DataFrame:
    """Un renglon por empleado y dia con marcaciones en el rango."""
    regs = listar_registros(desde, hasta, empleado_id)
    if regs.empty:
        return pd.DataFrame()

    tol = tolerancia_min()
    antes = contar_entrada_anticipada()
    horarios_cache: dict[int, dict[int, Horario]] = {}
    filas = []

    for (emp_id, nombre, fecha_txt), grupo in regs.groupby(["empleado_id", "nombre", "fecha"], sort=True):
        if emp_id not in horarios_cache:
            horarios_cache[emp_id] = horario_empleado(int(emp_id))
        fecha = date.fromisoformat(fecha_txt)
        marcas = [(r.tipo, r.fecha_hora.to_pydatetime()) for r in grupo.itertuples()]
        filas.append(resumir_dia(int(emp_id), nombre, fecha, marcas, horarios_cache[emp_id], tol, antes))

    df = pd.DataFrame([r.__dict__ for r in filas])
    df["dia"] = df["dia_semana"].map(lambda d: DIAS_CORTO[d])
    return df


def fmt_hm(minutos) -> str:
    """90 -> '1h 30m'"""
    if minutos is None or pd.isna(minutos):
        return ""
    minutos = int(minutos)
    if minutos == 0:
        return "0"
    h, m = divmod(minutos, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m"


def exportar_excel(df_resumen: pd.DataFrame, df_registros: pd.DataFrame) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        if not df_resumen.empty:
            res = df_resumen.copy()
            res["horas_trabajadas"] = (res["minutos_trabajados"] / 60).round(2)
            res["horas_extra"] = (res["extra_total_min"] / 60).round(2)
            for c in ("entrada_real", "salida_real"):
                res[c] = pd.to_datetime(res[c]).dt.strftime("%H:%M").fillna("")
            for c in ("programada_entrada", "programada_salida"):
                res[c] = res[c].map(lambda t: t.strftime("%H:%M") if t else "")
            res["horas_jornada"] = (res["jornada_min"] / 60).round(2)
            cols = [
                "nombre", "fecha", "dia", "programada_entrada", "programada_salida", "horas_jornada",
                "entrada_real", "salida_real", "bloques", "horas_trabajadas", "tardanza_min",
                "faltante_min", "extra_total_min", "horas_extra", "observacion",
            ]
            res[cols].rename(columns={
                "nombre": "Empleado", "fecha": "Fecha", "dia": "Día",
                "programada_entrada": "Entrada prog.", "programada_salida": "Salida prog.",
                "entrada_real": "Entrada real", "salida_real": "Salida real",
                "horas_trabajadas": "Horas trabajadas", "tardanza_min": "Tardanza (min)",
                "horas_jornada": "Jornada (h)", "bloques": "Bloques", "faltante_min": "Faltante (min)",
                "extra_total_min": "Extra total (min)", "horas_extra": "Horas extra", "observacion": "Observación",
            }).to_excel(xw, sheet_name="Resumen por día", index=False)

            tot = (
                res.groupby("nombre", as_index=False)
                .agg(dias=("fecha", "count"), horas_trabajadas=("horas_trabajadas", "sum"),
                     tardanza_min=("tardanza_min", "sum"), extra_total_min=("extra_total_min", "sum"))
            )
            tot["horas_extra"] = (tot["extra_total_min"] / 60).round(2)
            tot.rename(columns={
                "nombre": "Empleado", "dias": "Días", "horas_trabajadas": "Horas trabajadas",
                "tardanza_min": "Tardanza (min)", "extra_total_min": "Extra total (min)", "horas_extra": "Horas extra",
            }).to_excel(xw, sheet_name="Totales por empleado", index=False)

        if not df_registros.empty:
            reg = df_registros[["nombre", "tipo", "fecha", "fecha_hora", "foto", "nota"]].copy()
            reg["fecha_hora"] = reg["fecha_hora"].dt.strftime("%Y-%m-%d %H:%M:%S")
            reg.rename(columns={
                "nombre": "Empleado", "tipo": "Tipo", "fecha": "Fecha",
                "fecha_hora": "Fecha y hora", "foto": "Foto", "nota": "Nota",
            }).to_excel(xw, sheet_name="Marcaciones", index=False)

        # Ajuste de ancho de columnas
        for hoja in xw.sheets.values():
            for col in hoja.columns:
                ancho = max(len(str(c.value)) if c.value is not None else 0 for c in col)
                hoja.column_dimensions[col[0].column_letter].width = min(max(ancho + 2, 10), 40)
    return buf.getvalue()

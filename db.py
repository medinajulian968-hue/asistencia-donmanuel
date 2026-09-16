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

Bloque = tuple[time, time]


@dataclass
class Horario:
    """Lo que debe trabajar una persona un dia: 1 o 2 bloques (turno partido)."""
    bloques: list[Bloque]
    origen: str = "plantilla"  # "plantilla" (dia de la semana) o "turno" (fecha programada)

    @property
    def hora_entrada(self) -> time:
        return self.bloques[0][0]

    @property
    def hora_salida(self) -> time:
        return self.bloques[-1][1]

    @property
    def jornada_min(self) -> int:
        return sum(duracion_min(e, s_) for e, s_ in self.bloques)

    @property
    def partido(self) -> bool:
        return len(self.bloques) > 1

    def texto(self) -> str:
        return " y ".join(f"{e.strftime('%H:%M')}–{s_.strftime('%H:%M')}" for e, s_ in self.bloques)


def duracion_min(entrada: time, salida: time) -> int:
    """Minutos entre dos horas; si la salida es menor, se asume que cruza medianoche."""
    e = entrada.hour * 60 + entrada.minute
    s_ = salida.hour * 60 + salida.minute
    return s_ - e if s_ > e else s_ + 24 * 60 - e


def _bloques_de_fila(f: dict) -> list[Bloque]:
    bloques = []
    if f.get("hora_entrada") and f.get("hora_salida"):
        bloques.append((_parse_hora(f["hora_entrada"]), _parse_hora(f["hora_salida"])))
    if f.get("hora_entrada2") and f.get("hora_salida2"):
        bloques.append((_parse_hora(f["hora_entrada2"]), _parse_hora(f["hora_salida2"])))
    return bloques


def _fila_de_bloques(bloques: list[Bloque]) -> dict:
    b1 = bloques[0] if bloques else None
    b2 = bloques[1] if len(bloques) > 1 else None
    return {
        "hora_entrada": b1[0].strftime("%H:%M") if b1 else None,
        "hora_salida": b1[1].strftime("%H:%M") if b1 else None,
        "hora_entrada2": b2[0].strftime("%H:%M") if b2 else None,
        "hora_salida2": b2[1].strftime("%H:%M") if b2 else None,
    }


def limpiar_bloques(bloques) -> list[Bloque]:
    """Quita bloques incompletos y los ordena por hora de inicio."""
    out = [(e, s_) for e, s_ in bloques if e is not None and s_ is not None and e != s_]
    return sorted(out, key=lambda b: (b[0].hour, b[0].minute))[:2]


# --- Plantilla por dia de la semana ----------------------------------------

def horario_empleado(empleado_id: int) -> dict[int, Horario]:
    """Plantilla: {dia_semana: Horario} solo para los dias que trabaja."""
    data = (
        cliente().table("horarios").select("dia_semana,hora_entrada,hora_salida,hora_entrada2,hora_salida2")
        .eq("empleado_id", empleado_id).execute().data
    )
    out = {}
    for f in data:
        b = _bloques_de_fila(f)
        if b:
            out[f["dia_semana"]] = Horario(b, "plantilla")
    return out


def guardar_horario(empleado_id: int, dias: dict[int, list[Bloque] | None]) -> None:
    """dias = {dia_semana: [bloques]} o None/[] si ese dia no trabaja."""
    sb = cliente()
    sb.table("horarios").delete().eq("empleado_id", empleado_id).execute()
    filas = []
    for dia, bloques in dias.items():
        bloques = limpiar_bloques(bloques or [])
        if not bloques:
            continue
        fila = _fila_de_bloques(bloques)
        fila["jornada_min"] = Horario(bloques).jornada_min
        filas.append({"empleado_id": empleado_id, "dia_semana": dia, **fila})
    if filas:
        sb.table("horarios").insert(filas).execute()


def copiar_horario(origen_id: int, destino_id: int) -> None:
    hor = horario_empleado(origen_id)
    guardar_horario(destino_id, {d: h.bloques for d, h in hor.items()})


# --- Turnos programados por fecha -------------------------------------------

def lunes_de(fecha: date) -> date:
    return fecha - timedelta(days=fecha.weekday())


def turnos_rango(desde: date, hasta: date, empleado_id: int | None = None) -> dict[tuple[int, date], Horario | None]:
    """
    Turnos programados por fecha: {(empleado_id, fecha): Horario} o None si ese
    dia se marco explicitamente como libre.
    """
    q = (
        cliente().table("turnos").select("*")
        .gte("fecha", desde.strftime("%Y-%m-%d")).lte("fecha", hasta.strftime("%Y-%m-%d"))
    )
    if empleado_id is not None:
        q = q.eq("empleado_id", empleado_id)
    out = {}
    for f in q.execute().data:
        b = _bloques_de_fila(f)
        out[(int(f["empleado_id"]), date.fromisoformat(f["fecha"]))] = Horario(b, "turno") if b and not f.get("libre") else None
    return out


def guardar_turno(empleado_id: int, fecha: date, bloques: list[Bloque] | None) -> None:
    """bloques=None o [] -> dia libre programado."""
    bloques = limpiar_bloques(bloques or [])
    fila = {"empleado_id": empleado_id, "fecha": fecha.strftime("%Y-%m-%d"), "libre": not bloques,
            **_fila_de_bloques(bloques)}
    cliente().table("turnos").upsert(fila, on_conflict="empleado_id,fecha").execute()


def guardar_semana(empleado_id: int, lunes: date, dias: dict[date, list[Bloque] | None]) -> None:
    filas = []
    for fecha, bloques in dias.items():
        bloques = limpiar_bloques(bloques or [])
        filas.append({"empleado_id": empleado_id, "fecha": fecha.strftime("%Y-%m-%d"), "libre": not bloques,
                      **_fila_de_bloques(bloques)})
    if filas:
        cliente().table("turnos").upsert(filas, on_conflict="empleado_id,fecha").execute()


def borrar_semana(empleado_id: int, lunes: date) -> None:
    """Quita la programacion de esa semana: vuelve a regir la plantilla."""
    domingo = lunes + timedelta(days=6)
    (cliente().table("turnos").delete().eq("empleado_id", empleado_id)
     .gte("fecha", lunes.strftime("%Y-%m-%d")).lte("fecha", domingo.strftime("%Y-%m-%d")).execute())


def horario_del_dia(empleado_id: int, fecha: date, plantilla: dict[int, Horario] | None = None,
                    turnos: dict | None = None) -> Horario | None:
    """Turno programado para esa fecha si existe; si no, la plantilla del dia de la semana."""
    if turnos is None:
        turnos = turnos_rango(fecha, fecha, empleado_id)
    clave = (empleado_id, fecha)
    if clave in turnos:
        return turnos[clave]
    if plantilla is None:
        plantilla = horario_empleado(empleado_id)
    return plantilla.get(fecha.weekday())


def semana_empleado(empleado_id: int, lunes: date, plantilla=None, turnos=None) -> list[tuple[date, Horario | None]]:
    """Los 7 dias de la semana con el horario que rige cada uno."""
    if turnos is None:
        turnos = turnos_rango(lunes, lunes + timedelta(days=6), empleado_id)
    if plantilla is None:
        plantilla = horario_empleado(empleado_id)
    return [(lunes + timedelta(days=i), horario_del_dia(empleado_id, lunes + timedelta(days=i), plantilla, turnos))
            for i in range(7)]


def semana_todos(lunes: date) -> pd.DataFrame:
    """Tabla empleados x dias con el texto del horario de cada dia (para la vista publica)."""
    emps = listar_empleados(solo_activos=True)
    turnos = turnos_rango(lunes, lunes + timedelta(days=6))
    filas = []
    for e in emps.itertuples():
        plantilla = horario_empleado(int(e.id))
        fila = {"Empleado": e.nombre}
        for fecha, h in semana_empleado(int(e.id), lunes, plantilla, turnos):
            etiqueta = f"{DIAS_CORTO[fecha.weekday()]} {fecha.day:02d}"
            fila[etiqueta] = h.texto() if h else "Libre"
        filas.append(fila)
    return pd.DataFrame(filas)


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
    horario_txt: str
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
    hor: Horario | None,
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
      - Tardanza = cada bloque trabajado se compara con el bloque programado
        correspondiente (1o con 1o, 2o con 2o).
      - Si contar_antes es False, el tiempo antes de la hora de entrada
        programada de cada bloque no se cuenta como trabajado.
      - Dia sin horario: todo lo trabajado es extra.
    """
    bloques, sin_salida, sin_entrada = _sesiones(marcas)
    entradas = [m for t, m in marcas if t == TIPO_ENTRADA]
    salidas = [m for t, m in marcas if t == TIPO_SALIDA]
    entrada_real = min(entradas) if entradas else None
    salida_real = max(salidas) if salidas else None

    dia = fecha.weekday()
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
        # Inicio programado de cada bloque (en datetime)
        inicios = [datetime.combine(fecha, b[0]) for b in hor.bloques]
        recortados = []
        for i, (e, s_) in enumerate(bloques):
            prog = inicios[i] if i < len(inicios) else None
            if prog is not None:
                if e > prog:
                    tardanza += _aplicar_tolerancia(_minutos(e - prog), tolerancia)
                elif not contar_antes:
                    e = min(prog, s_)
            recortados.append((e, s_))
        trabajados = sum(_minutos(s_ - e) for e, s_ in recortados)

        if hor.partido and not sin_salida and 0 < len(bloques) < len(hor.bloques):
            obs.append("Faltó marcar el descanso")

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
        horario_txt=hor.texto() if hor else "",
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
    turnos = turnos_rango(desde, hasta, empleado_id)
    horarios_cache: dict[int, dict[int, Horario]] = {}
    filas = []

    for (emp_id, nombre, fecha_txt), grupo in regs.groupby(["empleado_id", "nombre", "fecha"], sort=True):
        if emp_id not in horarios_cache:
            horarios_cache[emp_id] = horario_empleado(int(emp_id))
        fecha = date.fromisoformat(fecha_txt)
        hor = horario_del_dia(int(emp_id), fecha, horarios_cache[emp_id], turnos)
        marcas = [(r.tipo, r.fecha_hora.to_pydatetime()) for r in grupo.itertuples()]
        filas.append(resumir_dia(int(emp_id), nombre, fecha, marcas, hor, tol, antes))

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
            res["horas_jornada"] = (res["jornada_min"] / 60).round(2)
            cols = [
                "nombre", "fecha", "dia", "horario_txt", "horas_jornada",
                "entrada_real", "salida_real", "bloques", "horas_trabajadas", "tardanza_min",
                "faltante_min", "extra_total_min", "horas_extra", "observacion",
            ]
            res[cols].rename(columns={
                "nombre": "Empleado", "fecha": "Fecha", "dia": "Día",
                "horario_txt": "Horario programado",
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

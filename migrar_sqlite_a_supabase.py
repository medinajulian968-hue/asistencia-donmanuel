# -*- coding: utf-8 -*-
"""
migrar_sqlite_a_supabase.py
===========================
Copia los datos de la version local (asistencia.db + carpeta fotos/) a Supabase.
Solo hace falta si alcanzaste a registrar empleados o marcaciones en la version
local antes de pasar a la nube.

Requisitos:
  - Haber ejecutado supabase_setup.sql en Supabase.
  - Tener .streamlit/secrets.toml con SUPABASE_URL y SUPABASE_KEY.

Ejecutar:  python migrar_sqlite_a_supabase.py
"""

from __future__ import annotations

import sqlite3
import sys
import tomllib
from pathlib import Path

BASE = Path(__file__).resolve().parent
DB_LOCAL = BASE / "asistencia.db"
FOTOS_LOCAL = BASE / "fotos"


def main() -> None:
    if not DB_LOCAL.exists():
        sys.exit("No existe asistencia.db: no hay nada que migrar.")

    secretos = BASE / ".streamlit" / "secrets.toml"
    if not secretos.exists():
        sys.exit("Falta .streamlit/secrets.toml con SUPABASE_URL y SUPABASE_KEY.")
    cfg = tomllib.loads(secretos.read_text(encoding="utf-8"))

    from supabase import create_client

    sb = create_client(cfg["SUPABASE_URL"], cfg["SUPABASE_KEY"])
    con = sqlite3.connect(DB_LOCAL)
    con.row_factory = sqlite3.Row

    # --- Empleados (se mapea id local -> id en Supabase por nombre) ---------
    mapa: dict[int, int] = {}
    for e in con.execute("SELECT * FROM empleados"):
        existente = sb.table("empleados").select("id").eq("nombre", e["nombre"]).execute().data
        if existente:
            mapa[e["id"]] = existente[0]["id"]
            print(f"  empleado ya existe: {e['nombre']}")
        else:
            nuevo = sb.table("empleados").insert({
                "nombre": e["nombre"], "cargo": e["cargo"] or "", "pin": e["pin"] or "",
                "activo": bool(e["activo"]), "creado_en": e["creado_en"],
            }).execute().data[0]
            mapa[e["id"]] = nuevo["id"]
            print(f"  empleado creado: {e['nombre']}")

    # --- Horarios ------------------------------------------------------------
    for h in con.execute("SELECT * FROM horarios"):
        sb.table("horarios").upsert({
            "empleado_id": mapa[h["empleado_id"]], "dia_semana": h["dia_semana"],
            "hora_entrada": h["hora_entrada"], "hora_salida": h["hora_salida"], "jornada_min": None,
        }, on_conflict="empleado_id,dia_semana").execute()
    print("  horarios copiados")

    # --- Registros y fotos ----------------------------------------------------
    n = 0
    for r in con.execute("SELECT * FROM registros ORDER BY id"):
        ruta = ""
        if r["foto"]:
            local = BASE / r["foto"]
            if local.exists():
                ruta = r["foto"].removeprefix("fotos/")
                sb.storage.from_("fotos").upload(
                    ruta, local.read_bytes(), {"content-type": "image/jpeg", "upsert": "true"}
                )
        sb.table("registros").insert({
            "empleado_id": mapa[r["empleado_id"]], "tipo": r["tipo"], "fecha": r["fecha"],
            "fecha_hora": r["fecha_hora"], "foto": ruta, "nota": r["nota"] or "", "creado_en": r["creado_en"],
        }).execute()
        n += 1
    print(f"  {n} marcaciones copiadas")

    # --- Config ----------------------------------------------------------------
    for c in con.execute("SELECT * FROM config"):
        sb.table("config").upsert({"clave": c["clave"], "valor": c["valor"]}, on_conflict="clave").execute()
    print("  configuración copiada")
    print("\nListo. Ya puedes renombrar o borrar asistencia.db y la carpeta fotos/.")


if __name__ == "__main__":
    main()

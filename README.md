# Control de asistencia y horas extra — Mercados Don Manuel

App para que cada compañero registre su **entrada** y **salida** con foto desde el
celular, desde cualquier lugar. La hora que queda guardada es la del momento en
que se toma la foto. Con el horario de cada persona, la app calcula tardanzas y
horas extra.

Corre en **Streamlit Community Cloud** y guarda los datos y fotos en **Supabase**
(ambos gratis). **Para publicarla sigue [DESPLIEGUE.md](DESPLIEGUE.md).**

## Primer uso (administrador)

1. Entra a **Administración** (contraseña inicial: `admin` — cámbiala en la pestaña
   *Configuración*).
2. **Empleados**: crea a cada compañero. El PIN es opcional pero recomendado para
   que nadie marque por otro.
3. **Horarios**: para cada persona marca los días que trabaja con hora de entrada y
   salida. Hay un *relleno rápido* (ej. Lun–Vie 8:00–17:00) y se puede copiar el
   horario de otro compañero.
4. **Configuración**: tolerancia en minutos y si el tiempo antes de la entrada
   cuenta como extra.

## Registro diario

En **Registrar**: elegir el nombre → la app sugiere *Entrada* o *Salida* según el
último movimiento → escribir el PIN (si tiene) → **📷 Tomar foto** (abre la cámara
del celular) → **Confirmar**. Al confirmar muestra la hora registrada y, si aplica,
la tardanza o las horas extra del día.

En el celular conviene guardar la dirección en la pantalla de inicio
(Safari/Chrome → Compartir → *Agregar a pantalla de inicio*).

## Reglas de cálculo de extras

- Se toma la **primera entrada** y la **última salida** de cada día.
- **Extra después** = minutos entre la salida programada y la salida real.
- **Extra antes** = minutos entre la entrada real y la entrada programada
  (solo si está activado en Configuración).
- **Tardanza** = minutos entre la entrada programada y la entrada real.
- **Tolerancia**: si la diferencia no supera los minutos de tolerancia, no cuenta.
  Si la supera, cuentan todos los minutos.
- **Día no programado** (ej. domingo sin horario): todo el tiempo trabajado es extra.
- Un turno que cruza medianoche (ej. 22:00–06:00) se calcula bien siempre que la
  salida se marque en el mismo turno.

## Reporte

**Reporte de extras** (requiere contraseña de administrador): rango de fechas,
totales por empleado, detalle por día, fotos de cada marcación y descarga a Excel
con tres hojas (resumen por día, totales por empleado, marcaciones).

## Correcciones

En **Administración → Marcaciones** se puede editar la hora o el tipo de una
marcación, eliminarla, o agregar una manual (por ejemplo si alguien olvidó marcar).

## Zona horaria

Las horas se guardan en la zona `TIMEZONE` de los Secrets (por defecto
`America/Bogota`). Si estás en otro país, cámbiala ahí (ej. `America/Mexico_City`,
`America/Lima`, `America/Argentina/Buenos_Aires`).

## Correr en el PC (opcional)

Crea `.streamlit/secrets.toml` a partir de `.streamlit/secrets.example.toml` con
tus claves de Supabase y ejecuta `iniciar_asistencia.bat`. Usa la misma base de
datos que la versión en línea.

## Archivos

| Archivo | Qué es |
|---|---|
| `app.py` | Interfaz (Streamlit) |
| `db.py` | Acceso a Supabase y cálculo de extras |
| `supabase_setup.sql` | Crea las tablas y el bucket de fotos en Supabase |
| `requirements.txt` | Librerías necesarias |
| `DESPLIEGUE.md` | Guía para publicarla en la nube |
| `iniciar_asistencia.bat` | Lanzador para correrla en el PC |
| `migrar_sqlite_a_supabase.py` | Pasa datos de la versión local anterior a la nube |
| `.streamlit/secrets.example.toml` | Plantilla de las claves |

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
3. **Horario base**: para cada persona, el horario que se repite cada semana. Cada
   día puede tener **un bloque** (turno corrido, ej. 7:00–15:00) o **dos bloques**
   (turno partido, ej. 8:00–12:00 y 14:00–21:00). Hay un *relleno rápido* y se
   puede copiar el horario de otro compañero.
4. **Programar semana**: cuando una semana concreta es distinta del horario base
   (turnos partidos ocasionales, cambio de día libre…), se programa ahí por fechas.
   Los días que no se programen siguen el horario base. Botones para copiar la
   semana anterior o volver al horario base.
5. **Configuración**: tolerancia en minutos y si el tiempo antes de la entrada
   cuenta como trabajado.

## Horario semanal (para los empleados)

- En **Registrar**, al elegir su nombre, cada uno ve **Mi horario de esta semana**
  (y la próxima).
- La página **Horario semanal** muestra el cuadro completo de todos, por semana.

## Registro diario

En **Registrar**: elegir el nombre → la app sugiere *Entrada* o *Salida* según el
último movimiento → escribir el PIN (si tiene) → **📷 Tomar foto** (abre la cámara
del celular) → **Confirmar**. Al confirmar muestra la hora registrada y, si aplica,
la tardanza o las horas extra del día.

En el celular conviene guardar la dirección en la pantalla de inicio
(Safari/Chrome → Compartir → *Agregar a pantalla de inicio*).

## Reglas de cálculo de extras

- Cada persona marca **entrada** y **salida** cada vez que llega o se va. En turno
  partido son 4 marcaciones (entrada, salida al descanso, entrada, salida final).
- La app empareja cada entrada con su salida en **bloques** y suma solo lo
  trabajado; los descansos no cuentan.
- La **jornada** del día es la suma de sus bloques programados (ej. 8–12 y 14–21 = 11h).
- La **tardanza** se calcula por bloque: la entrada real de cada bloque contra la
  hora programada de ese bloque.
- **Extra** = horas trabajadas − jornada (si supera la tolerancia).
- **Faltante** = jornada − horas trabajadas, cuando el día quedó completo pero corto.
- **Tardanza** = minutos entre la hora de entrada programada y la primera entrada real.
- **Tolerancia**: si la diferencia no supera los minutos de tolerancia, no cuenta.
  Si la supera, cuentan todos los minutos.
- Por defecto el tiempo **antes** de la hora de entrada no cuenta como trabajado
  (se puede activar en Configuración).
- **Día no programado** (ej. domingo sin horario): todo el tiempo trabajado es extra.

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

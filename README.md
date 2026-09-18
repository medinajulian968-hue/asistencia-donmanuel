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
2. **Empleados**: crea a cada compañero con su **clave personal** (obligatoria,
   4–8 caracteres). Sin clave no puede marcar; así nadie marca por otro.
3. **Horario base**: para cada persona, el horario que se repite cada semana. Cada
   día puede tener **un bloque** (turno corrido, ej. 7:00–15:00) o **dos bloques**
   (turno partido, ej. 8:00–12:00 y 14:00–21:00). Hay un *relleno rápido* y se
   puede copiar el horario de otro compañero.
4. **Programar semana**: cuando una semana concreta es distinta del horario base
   (turnos partidos ocasionales, cambio de día libre…), se programa ahí por fechas.
   Los días que no se programen siguen el horario base. Botones para copiar la
   semana anterior o volver al horario base.
5. **Sedes**: las tiendas (Gourmet, Parque, …). Cada empleado tiene una **sede
   base** y en el horario base o en la programación semanal se puede poner una
   sede distinta cada día (hoy en Gourmet, mañana en Parque).
6. **Configuración**: tolerancia, jornada legal semanal/mensual y si el tiempo
   antes de la entrada cuenta como trabajado.

## Horario semanal (para los empleados)

- En **Registrar**, al elegir su nombre, cada uno ve **Mi horario de esta semana**
  (y la próxima).
- La página **Horario semanal** muestra el cuadro completo de todos, por semana,
  con filtro por sede (cada tienda ve a su gente; los días en otra sede salen
  entre paréntesis).

## Registro diario

En **Registrar**: elegir el nombre → la app sugiere *Entrada* o *Salida* según el
último movimiento → escribir su **clave** → **📷 Tomar foto** (abre la cámara
del celular) → **Confirmar**. Al confirmar muestra la hora registrada y, si aplica,
la tardanza o las horas extra del día.

En el celular conviene guardar la dirección en la pantalla de inicio
(Safari/Chrome → Compartir → *Agregar a pantalla de inicio*).

## Reglas de cálculo de extras

**Las horas extra se liquidan por período (mes o quincena), no día a día:**

- **Extra del período = horas trabajadas en el período − jornada legal del período.**
- Jornada legal: 42 h/semana (Colombia, Ley 2101 de 2021) → **210 h/mes** con la
  convención de nómina (mes de 30 días = 5 semanas). Quincena = 105 h. Un rango de
  fechas cualquiera se prorratea (210 × días / 30). Ambos valores se ajustan en
  *Configuración*.
- Así, una semana de 48 h y otra de 36 h se compensan dentro del mes; y dentro de
  la semana, un día de 6 h y otro de 8 h se compensan entre sí (lo que importa es
  el total del período, no el día a día).
- Con el período **Semana** la jornada legal es 42 h (7 h × 6 días, un día de
  descanso); la tabla *Horas por semana* muestra en cada semana lo que sobra (+) o
  falta (−) respecto a 42 h.
- Si trabajó menos que la jornada legal, aparece como **Faltante**.

Cómo se cuentan las horas trabajadas:

- Cada persona marca **entrada** y **salida** cada vez que llega o se va. En turno
  partido son 4 marcaciones (entrada, salida al descanso, entrada, salida final).
- La app empareja cada entrada con su salida en **bloques** y suma solo lo
  trabajado; los descansos no cuentan.
- Por defecto el tiempo **antes** de la hora de entrada programada no cuenta como
  trabajado (se puede activar en Configuración).
- **Tardanza** = minutos entre la hora de entrada programada de cada bloque y la
  entrada real (con tolerancia).
- **Tolerancia**: si la diferencia no supera los minutos de tolerancia, no cuenta.
- **Gracia de salida** (40 min por defecto, en Configuración): los minutos después
  de la salida programada hasta salida + gracia siguen siendo parte del turno y no
  suman. Turno hasta 14:00 → hasta 14:40 no cuenta; si sale a 15:00 suman 20 min.

El detalle por día muestra además *Sobre horario* (lo trabajado por encima del
horario de ese día) como referencia; no es la cifra oficial de extras.

## Reporte

**Reporte de extras** (requiere contraseña de administrador): elige **Semana**
(42 h), **Mes**, **Quincena** o **Rango**; liquidación del período por empleado (trabajadas, jornada
legal, extra, faltante, tardanzas), horas por semana, detalle por día, fotos de
cada marcación y descarga a Excel (resumen por día, liquidación del período,
marcaciones).

## Correcciones

En **Administración → Marcaciones** se puede editar la hora o el tipo de una
marcación, eliminarla, o agregar una manual (por ejemplo si alguien olvidó marcar).

## Limpieza de fotos

Supabase gratis guarda 1 GB de fotos (~1 año con 23 personas). En
**Administración → Configuración → Limpieza de fotos** se ve cuánto ocupa cada
mes y se pueden borrar las fotos de meses ya liquidados. Las marcaciones y las
horas se conservan; solo desaparece la imagen. Recomendado: descargar el Excel
del mes y luego limpiar.

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

# Publicar la app en la nube (paso a paso)

Al final tendrás una dirección tipo `https://asistencia-donmanuel.streamlit.app`
que funciona desde cualquier celular, en cualquier red, sin que tu PC esté
encendido. Todo es gratis.

Necesitas crear 3 cuentas (con tu correo de Gmail sirve para todas):

| Servicio | Para qué | Dirección |
|---|---|---|
| GitHub | Guardar el código | https://github.com |
| Supabase | Guardar datos y fotos | https://supabase.com |
| Streamlit Community Cloud | Correr la app | https://share.streamlit.io |

Tiempo estimado: 15–20 minutos.

---

## Paso 1 — Supabase (base de datos y fotos)

1. Entra a https://supabase.com → **Start your project** → crea la cuenta.
2. **New project**:
   - Name: `asistencia`
   - Database password: inventa una y **guárdala** (no la vas a necesitar en la app, pero Supabase la pide).
   - Region: la más cercana (ej. *South America (São Paulo)* o *East US*).
   - **Create new project** y espera 1–2 minutos a que quede listo.
3. En el menú izquierdo → **SQL Editor** → **New query**.
   Abre el archivo `supabase_setup.sql` de esta carpeta con el Bloc de notas,
   copia **todo** el contenido, pégalo en el editor y presiona **Run**.
   Debe decir "Success. No rows returned".
4. Menú izquierdo → **Project Settings** (ícono de engranaje) → **API**:
   - Copia **Project URL** (ej. `https://abcdefgh.supabase.co`).
   - En *Project API keys*, copia la clave **`service_role`** (dale a *Reveal*;
     es larga, empieza por `eyJ...`).

   > ⚠️ La clave `service_role` es como la contraseña maestra. Solo va en los
   > *Secrets* de Streamlit (paso 3). Nunca la pegues en el código ni la subas a GitHub.

---

## Paso 2 — GitHub (el código)

1. Entra a https://github.com → **Sign up** → crea la cuenta.
2. Arriba a la derecha **+** → **New repository**:
   - Repository name: `asistencia-donmanuel`
   - Marca **Private**.
   - **Create repository**.
3. En la página del repositorio nuevo, clic en **uploading an existing file**
   (o botón **Add file → Upload files**).
4. Arrastra estos archivos de la carpeta `asistencia`:
   - `app.py`
   - `db.py`
   - `requirements.txt`
   - `supabase_setup.sql`
   - `.gitignore`
   - `README.md`, `DESPLIEGUE.md` (opcionales)

   **NO subas**: `asistencia.db`, la carpeta `fotos`, ni `.streamlit/secrets.toml`.
5. Abajo, **Commit changes**.

> Alternativa si manejas git (desde la carpeta `asistencia`):
> ```
> git init -b main
> git add .
> git commit -m "App de asistencia"
> git remote add origin https://github.com/TU_USUARIO/asistencia-donmanuel.git
> git push -u origin main
> ```
> El `.gitignore` ya excluye los secretos, la base local y las fotos.

---

## Paso 3 — Streamlit Community Cloud (la app en línea)

1. Entra a https://share.streamlit.io → **Continue with GitHub** → autoriza.
2. **Create app** → **Deploy a public app from GitHub** (aunque el repo sea privado, funciona).
3. Llena:
   - Repository: `TU_USUARIO/asistencia-donmanuel`
   - Branch: `main`
   - Main file path: `app.py`
   - App URL: elige un nombre, ej. `asistencia-donmanuel` → quedará
     `https://asistencia-donmanuel.streamlit.app`
4. Clic en **Advanced settings**:
   - Python version: `3.12`
   - En **Secrets**, pega exactamente esto (con tus valores del paso 1):
     ```toml
     SUPABASE_URL = "https://abcdefgh.supabase.co"
     SUPABASE_KEY = "eyJ...la clave service_role completa..."
     TIMEZONE = "America/Bogota"
     ```
   - **Save**.
5. **Deploy**. Tarda 2–3 minutos la primera vez. Cuando cargue, verás la
   pantalla "Registro de entrada y salida".

Si aparece un error de conexión, revisa que los Secrets estén bien y que hayas
corrido el SQL del paso 1 (en Streamlit Cloud: menú **⋮ → Settings → Secrets**
para corregirlos; **Reboot app** para reiniciar).

---

## Paso 4 — Primer uso

1. Abre tu dirección `https://....streamlit.app` → **Administración** →
   contraseña `admin` → **cámbiala** en la pestaña *Configuración*.
2. Crea los empleados (con PIN) y sus horarios.
3. Comparte la dirección con los compañeros. En el celular:
   **Safari/Chrome → Compartir → Agregar a pantalla de inicio** para tenerla como app.

---

## Si ya tenías datos en la versión local

Si registraste empleados o marcaciones con la versión anterior (archivo
`asistencia.db`), puedes pasarlos a la nube:

1. Copia `.streamlit/secrets.example.toml` como `.streamlit/secrets.toml` y
   pon tus valores de Supabase.
2. Ejecuta en esta carpeta:
   ```
   python migrar_sqlite_a_supabase.py
   ```

---

## Preguntas frecuentes

**¿La app se "duerme"?** En el plan gratuito de Streamlit, si nadie la usa por
varios días se pausa; al abrirla de nuevo tarda ~1 minuto en despertar. Con uso
diario no pasa.

**¿Cuánto espacio hay para fotos?** Supabase gratis da 1 GB. Cada foto pesa
~60–100 KB, así que caben más de 10.000 marcaciones.

**¿Cómo actualizo la app si cambia el código?** Sube el archivo nuevo al
repositorio de GitHub (Add file → Upload files → reemplaza) y Streamlit Cloud se
actualiza sola en un minuto.

**¿Cómo hago copia de seguridad?** En Supabase → **Table Editor** puedes
exportar cada tabla a CSV. Las fotos están en **Storage → fotos**. Además el
reporte de la app descarga todo a Excel.

**¿Sigue funcionando en mi PC?** Sí: crea `.streamlit/secrets.toml` con los
mismos valores y usa `iniciar_asistencia.bat`. Usará la misma base de datos en
línea.

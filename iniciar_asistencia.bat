@echo off
setlocal enabledelayedexpansion
title Control de asistencia - Mercados Don Manuel

REM ===================================================================
REM  ESTE es el archivo que abre la app de asistencia.
REM  Doble clic aqui, o ejecutarlo desde la terminal.
REM
REM  (app.py y db.py NO se abren con doble clic: son el codigo.)
REM ===================================================================

cd /d "%~dp0"

echo.
echo  ============================================================
echo   Control de asistencia - Mercados Don Manuel
echo  ============================================================
echo.

REM --- 1. Buscar un Python que funcione -------------------------------

set "PY="

for %%P in (
    "%LOCALAPPDATA%\Python\bin\python.exe"
    "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe"
) do (
    if not defined PY (
        if exist %%P (
            %%P -c "import sys" >nul 2>nul
            if !errorlevel! equ 0 set "PY=%%~P"
        )
    )
)

if not defined PY (
    python -c "import sys" >nul 2>nul
    if !errorlevel! equ 0 set "PY=python"
)

if not defined PY (
    py -c "import sys" >nul 2>nul
    if !errorlevel! equ 0 set "PY=py"
)

if not defined PY (
    echo  ERROR: no se encontro Python en este equipo.
    echo.
    echo  Instalalo desde https://www.python.org/downloads/
    echo  y marca la casilla "Add Python to PATH" durante la instalacion.
    echo.
    goto :fin
)

echo  Python encontrado: %PY%
echo.

REM --- 2. Instalar dependencias si faltan ------------------------------

"%PY%" -c "import streamlit, pandas, PIL, openpyxl, supabase" >nul 2>nul
if !errorlevel! neq 0 (
    echo  Faltan librerias. Instalandolas por primera vez...
    echo  Esto puede tardar varios minutos. No cierres esta ventana.
    echo.
    "%PY%" -m pip install --disable-pip-version-check -r requirements.txt
    if !errorlevel! neq 0 (
        echo.
        echo  ERROR: no se pudieron instalar las librerias.
        echo  Revisa que tengas conexion a internet y vuelve a intentar.
        echo.
        goto :fin
    )
    echo.
    echo  Librerias instaladas correctamente.
    echo.
)

REM --- 3. Verificar que esten los archivos -----------------------------

if not exist "app.py" (
    echo  ERROR: no se encuentra app.py en esta carpeta:
    echo  %CD%
    echo.
    goto :fin
)

if not exist ".streamlit\secrets.toml" (
    echo  ERROR: falta el archivo .streamlit\secrets.toml con las claves de Supabase.
    echo  Copia .streamlit\secrets.example.toml como secrets.toml y pon tus valores.
    echo  (Ver DESPLIEGUE.md)
    echo.
    goto :fin
)

REM --- 4. Arrancar ------------------------------------------------------

echo  Abriendo la app en el navegador...
echo.
echo  En este equipo: http://localhost:8502
echo  (Los datos se guardan en Supabase, igual que la version en linea.)
echo.
echo  ------------------------------------------------------------
echo   PARA CERRARLA: presiona Ctrl+C aqui, o cierra esta ventana.
echo   NO cierres esta ventana mientras la usen.
echo  ------------------------------------------------------------
echo.

"%PY%" -m streamlit run app.py --server.port 8502 --browser.gatherUsageStats false

if !errorlevel! neq 0 (
    echo.
    echo  La app termino con un error. El detalle esta arriba.
    echo.
)

:fin
echo.
pause
endlocal

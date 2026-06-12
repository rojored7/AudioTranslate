@echo off
:: ============================================================
::  AudioBook Lite - Reproductor PC B
::  Analiza el equipo, instala Python si falta (winget o
::  instalador oficial) y arranca el reproductor en el 9002.
:: ============================================================

:: Version que se descarga si hay que instalar Python a mano
:: (debe ser una version concreta existente en python.org/ftp)
set "PYTHON_INSTALL_VERSION=3.12.10"

echo ============================================
echo  AudioBook Lite - Reproductor PC B
echo ============================================
echo.

:: --- Cargar .env si existe (GITHUB_TOKEN, GITHUB_REPO, etc.) ---
:: eol=# hace que for /f ignore las lineas de comentario que empiezan con #
if exist "%~dp0.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%~dp0.env") do (
        if not "%%A"=="" set "%%A=%%B"
    )
)

:: --- PASO 1: Analisis - buscar un Python 3.10 o superior ---
echo [1/3] Buscando Python 3.10 o superior...
set "PYEXE="
call :try_python py -3
if defined PYEXE goto launch
call :try_python python
if defined PYEXE goto launch
call :try_python python3
if defined PYEXE goto launch
call :try_known_paths
if defined PYEXE goto launch

echo       No se encontro un Python compatible en este equipo.
echo.

:: --- PASO 2: Analisis - hay internet? ---
echo [2/3] Comprobando conexion a internet...
curl.exe -s -I --max-time 8 https://www.python.org >nul 2>&1
if errorlevel 1 (
    echo       Sin conexion a internet o falta curl.
    goto manual
)
echo       Conexion OK. Instalando Python automaticamente...
echo.

:: --- PASO 3a: Intentar instalar con winget ---
winget --version >nul 2>&1
if not errorlevel 1 (
    echo [3/3] Instalando Python 3.12 con winget, puede tardar unos minutos...
    winget install -e --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements
    call :try_known_paths
    if defined PYEXE goto launch
    echo       winget no completo la instalacion. Probando otra via...
    echo.
)

:: --- PASO 3b: Descargar el instalador oficial de python.org ---
:: El instalador es de 64 bits; en un Windows de 32 bits no funcionaria
:: y el usuario entraria en un bucle de "vuelve a ejecutar run.bat".
if "%PROCESSOR_ARCHITECTURE%"=="x86" if not defined PROCESSOR_ARCHITEW6432 (
    echo       Este equipo es Windows de 32 bits: el instalador automatico
    echo       no sirve aqui. Instala Python a mano desde python.org.
    goto manual
)
echo [3/3] Descargando instalador oficial de Python %PYTHON_INSTALL_VERSION%...
curl.exe -L --fail -o "%TEMP%\python-setup.exe" "https://www.python.org/ftp/python/%PYTHON_INSTALL_VERSION%/python-%PYTHON_INSTALL_VERSION%-amd64.exe"
if errorlevel 1 (
    echo       ERROR: fallo la descarga del instalador.
    goto manual
)
echo       Instalando Python en modo silencioso, puede tardar unos minutos...
"%TEMP%\python-setup.exe" /quiet InstallAllUsers=0 PrependPath=1
del "%TEMP%\python-setup.exe" >nul 2>&1
call :try_known_paths
if defined PYEXE goto launch

echo.
echo Python quedo instalado, pero esta ventana todavia no lo ve.
echo CIERRA esta ventana y vuelve a hacer doble clic en run.bat
goto end

:: --- Fallback manual ---
:manual
echo.
echo ------------------------------------------------------------
echo  No se pudo instalar Python automaticamente.
echo  Instalalo a mano desde:  https://python.org
echo  Marca la casilla "Add Python to PATH" al instalar
echo  y vuelve a ejecutar run.bat.  Mas ayuda: LEEME.txt
echo ------------------------------------------------------------
goto end

:: --- Arranque del reproductor ---
:launch
echo       Python encontrado: %PYEXE%
echo.
echo Iniciando servidor en http://localhost:9002 ...
"%PYEXE%" "%~dp0server.py"
goto end

:: --- Subrutinas ---

:try_python
:: %* = comando a probar (py -3 / python / python3).
:: Deja en PYEXE la ruta real del ejecutable SOLO si la version es >= 3.10.
:: El propio Python compara la version; comparar texto en batch es un bug
:: conocido: "3.9" pareceria mayor que "3.10".
for /f "delims=" %%p in ('%* -c "import sys; v=sys.version_info; sys.exit(1) if (v.major, v.minor) < (3, 10) else print(sys.executable)" 2^>nul') do set "PYEXE=%%p"
goto :eof

:try_known_paths
:: Busca instalaciones recientes en la ruta tipica de instalacion por usuario
:: (alli instalan tanto winget como el instalador oficial con InstallAllUsers=0).
for %%d in (Python313 Python312 Python311 Python310) do (
    if not defined PYEXE if exist "%LocalAppData%\Programs\Python\%%d\python.exe" set "PYEXE=%LocalAppData%\Programs\Python\%%d\python.exe"
)
goto :eof

:end
pause

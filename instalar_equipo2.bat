@echo off
:: ============================================================
::  AudioBook Lite - INSTALADOR para el Equipo 2 (PC B)
::
::  Este es el UNICO archivo que hay que llevar al otro equipo.
::  Que hace:
::    1. Pide los datos de GitHub (repo y token) la primera vez
::    2. Descarga el codigo del reproductor desde GitHub
::    3. Lo instala en la carpeta AudioBookLite junto a este .bat
::    4. Arranca run.bat (que instala Python solo si falta)
::
::  Volver a ejecutarlo = actualizar a la ultima version.
::  Los libros, el audio y el progreso NUNCA se borran.
:: ============================================================

setlocal
set "INSTALL_DIR=%~dp0AudioBookLite"
set "ZIP=%TEMP%\audiobook_code.zip"
set "EXTRACT=%TEMP%\audiobook_extract"

echo ============================================
echo  AudioBook Lite - Instalador Equipo 2
echo ============================================
echo.

:: --- PASO 1: datos de GitHub (de .env si ya existe, si no se piden) ---
set "GITHUB_REPO="
set "GITHUB_TOKEN="
if exist "%INSTALL_DIR%\.env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%A in ("%INSTALL_DIR%\.env") do (
        if /i "%%A"=="GITHUB_REPO" set "GITHUB_REPO=%%B"
        if /i "%%A"=="GITHUB_TOKEN" set "GITHUB_TOKEN=%%B"
    )
)

if not defined GITHUB_REPO (
    echo Escribe el repositorio de GitHub, formato  usuario/repositorio
    set /p GITHUB_REPO=Repo:
)
if not defined GITHUB_TOKEN (
    echo.
    echo Pega el token de GitHub ^(empieza por ghp_...^)
    set /p GITHUB_TOKEN=Token:
)
if not defined GITHUB_REPO goto datos_invalidos
if not defined GITHUB_TOKEN goto datos_invalidos

:: --- PASO 2: descargar el codigo desde GitHub ---
echo.
echo [1/3] Descargando la ultima version desde GitHub...
curl.exe -L --fail -H "Authorization: Bearer %GITHUB_TOKEN%" -H "Accept: application/vnd.github+json" -o "%ZIP%" "https://api.github.com/repos/%GITHUB_REPO%/zipball"
if errorlevel 1 (
    echo.
    echo ERROR: no se pudo descargar. Revisa:
    echo   - que hay internet
    echo   - que el repo es  %GITHUB_REPO%  ^(formato usuario/repositorio^)
    echo   - que el token es valido y tiene permiso "repo"
    goto end
)

:: --- PASO 3: extraer e instalar (sin tocar datos) ---
echo [2/3] Instalando en %INSTALL_DIR% ...
if exist "%EXTRACT%" rmdir /s /q "%EXTRACT%"
powershell -NoProfile -Command "Expand-Archive -Force '%ZIP%' '%EXTRACT%'"
if errorlevel 1 (
    echo ERROR: no se pudo extraer el archivo descargado.
    goto end
)

:: el zip de GitHub trae una carpeta interna con nombre usuario-repo-hash
set "SRC="
for /d %%D in ("%EXTRACT%\*") do set "SRC=%%D"
if not defined SRC (
    echo ERROR: el zip descargado vino vacio.
    goto end
)

:: copiar SOLO el reproductor; /e /y sobreescribe codigo pero no borra
:: nada extra (la carpeta data\ con libros y progreso queda intacta)
xcopy "%SRC%\player_lite" "%INSTALL_DIR%" /e /i /y >nul

:: guardar la configuracion para el sync automatico y futuras actualizaciones
(
    echo GITHUB_TOKEN=%GITHUB_TOKEN%
    echo GITHUB_REPO=%GITHUB_REPO%
) > "%INSTALL_DIR%\.env"

:: limpiar temporales
del "%ZIP%" >nul 2>&1
rmdir /s /q "%EXTRACT%" >nul 2>&1

:: --- PASO 4: arrancar ---
echo [3/3] Instalado. Arrancando el reproductor...
echo.
endlocal & call "%~dp0AudioBookLite\run.bat"
goto :eof

:datos_invalidos
echo.
echo No se puede continuar sin el repo y el token de GitHub.
echo Pideselos a la persona del equipo principal ^(estan en su archivo .env^).

:end
pause

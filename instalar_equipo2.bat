@echo off
:: ============================================================
::  AudioBook - Equipo 2 (PC B)
::
::  UNICO archivo que hay que llevar al otro equipo.
::  Que hace:
::    1. Descarga (o actualiza) reproductor.html desde GitHub
::    2. Lo abre en el navegador  -  y ya esta
::
::  No instala Python ni nada. Volver a ejecutarlo = actualizar.
::  Los libros y el progreso viven DENTRO del navegador:
::  este archivo nunca los toca.
:: ============================================================

setlocal
set "REPO=rojored7/AudioTranslate"
set "DEST=%~dp0reproductor.html"

echo ============================================
echo  AudioBook - Reproductor (sin instalacion)
echo ============================================
echo.
echo [1/2] Descargando la ultima version del reproductor...
curl.exe -L --fail -o "%DEST%.nuevo" "https://raw.githubusercontent.com/%REPO%/main/reproductor.html"
if errorlevel 1 goto sin_descarga

:: una descarga cortada dejaria un archivo a medias: comprobar tamano
set "TAM=0"
for %%F in ("%DEST%.nuevo") do set "TAM=%%~zF"
if %TAM% LSS 15000 (
    del "%DEST%.nuevo" >nul 2>&1
    goto sin_descarga
)
move /y "%DEST%.nuevo" "%DEST%" >nul
echo       Reproductor actualizado.
goto abrir

:sin_descarga
if exist "%DEST%" (
    echo       Sin internet o GitHub no responde.
    echo       Se abre la version ya descargada.
    goto abrir
)
echo.
echo ERROR: no se pudo descargar y no hay una version previa.
echo Revisa la conexion a internet y vuelve a ejecutar este archivo.
pause
exit /b 1

:abrir
echo [2/2] Abriendo el reproductor en el navegador...
start "" "%DEST%"

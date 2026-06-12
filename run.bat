@echo off
REM Script para instalar dependencias e iniciar AudioBook Player

echo ===== AudioBook Player Setup =====
echo.

REM Check if venv exists
if not exist venv (
    echo Creando entorno virtual...
    python -m venv venv
    echo.
)

REM Activate venv
echo Activando entorno virtual...
call venv\Scripts\activate.bat
echo.

REM Install dependencies
echo Instalando dependencias...
pip install -q -r requirements.txt
echo.

REM Initialize database
echo Inicializando base de datos...
python -c "from db import init_db; init_db(); print('✓ Base de datos creada')"
echo.

REM Start server
echo.
echo ===== INICIANDO SERVIDOR =====
echo.
echo 📚 AudioBook Player está corriendo en: http://localhost:8000
echo.
echo Presiona Ctrl+C para detener
echo.

python main.py

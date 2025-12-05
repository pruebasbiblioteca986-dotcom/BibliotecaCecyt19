@echo off
REM Script para inicializar la Biblioteca CECyT 19

echo.
echo ======================================
echo BIBLIOTECA CECyT 19 - Inicialización
echo ======================================
echo.

REM Verificar que existe venv
if not exist venv (
    echo ❌ Entorno virtual no encontrado. Creando...
    python -m venv venv
    echo ✅ Entorno virtual creado
)

REM Activar entorno virtual
call venv\Scripts\activate.bat

REM Mostrar información
echo.
echo ✅ Entorno virtual activado
echo.
echo Información del proyecto:
echo - Python: 
python --version
echo - Flask: 3.0.0
echo - MongoDB: Requerido en localhost:27017
echo - Base de datos: "Biblioteca"
echo.
echo Dependencias instaladas:
echo   - Flask (Web Framework)
echo   - Flask-CORS (Cross-Origin Requests)
echo   - PyMongo (MongoDB Driver)
echo   - Pandas (Datos y análisis)
echo   - OpenPyXL (Excel support)
echo   - Unidecode (Normalización de texto)
echo.

REM Verificar MongoDB
echo Verificando MongoDB...
netstat -an | find "27017" >nul
if %errorlevel% neq 0 (
    echo ⚠️  ADVERTENCIA: MongoDB no parece estar corriendo en puerto 27017
    echo    Inicia MongoDB y luego presiona una tecla...
    pause
) else (
    echo ✅ MongoDB está corriendo
)

echo.
echo Iniciando aplicación...
echo.
echo 🚀 La aplicación estará disponible en: http://localhost:5000
echo 📧 Correos: Configurados en .env (MODO_PRUEBA=true)
echo.
echo Presiona Ctrl+C para detener el servidor
echo.

REM Iniciar la aplicación
python app.py

REM Desactivar entorno virtual al salir
deactivate

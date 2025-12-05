# Script para inicializar la Biblioteca CECyT 19

Write-Host "`n" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "BIBLIOTECA CECyT 19 - Inicialización" -ForegroundColor Cyan
Write-Host "======================================" -ForegroundColor Cyan
Write-Host "`n"

$projectPath = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $projectPath

# Verificar que existe venv
if (-not (Test-Path "venv")) {
    Write-Host "❌ Entorno virtual no encontrado. Creando..." -ForegroundColor Yellow
    python -m venv venv
    Write-Host "✅ Entorno virtual creado" -ForegroundColor Green
}

# Activar entorno virtual
& ".\venv\Scripts\Activate.ps1"

Write-Host "`n✅ Entorno virtual activado" -ForegroundColor Green
Write-Host "`nInformación del proyecto:" -ForegroundColor Cyan
Write-Host "- Python: " -NoNewline
python --version
Write-Host "- Flask: 3.0.0"
Write-Host "- MongoDB: Requerido en localhost:27017"
Write-Host "- Base de datos: `"Biblioteca`""
Write-Host "`nDependencias instaladas:" -ForegroundColor Cyan
Write-Host "  - Flask (Web Framework)"
Write-Host "  - Flask-CORS (Cross-Origin Requests)"
Write-Host "  - PyMongo (MongoDB Driver)"
Write-Host "  - Pandas (Datos y análisis)"
Write-Host "  - OpenPyXL (Excel support)"
Write-Host "  - Unidecode (Normalización de texto)"

# Verificar MongoDB
Write-Host "`nVerificando MongoDB..." -ForegroundColor Yellow
try {
    $mongoRunning = $null -ne (Get-NetTCPConnection -LocalPort 27017 -ErrorAction SilentlyContinue)
    if ($mongoRunning) {
        Write-Host "✅ MongoDB está corriendo en puerto 27017" -ForegroundColor Green
    } else {
        Write-Host "⚠️  ADVERTENCIA: MongoDB no parece estar corriendo en puerto 27017" -ForegroundColor Yellow
        Write-Host "   Inicia MongoDB antes de continuar" -ForegroundColor Yellow
        Read-Host "   Presiona Enter cuando MongoDB esté listo"
    }
} catch {
    Write-Host "⚠️  No se pudo verificar MongoDB (posible permisos limitados)" -ForegroundColor Yellow
}

Write-Host "`n" -ForegroundColor Green
Write-Host "Iniciando aplicación..." -ForegroundColor Green
Write-Host "`n"
Write-Host "🚀 La aplicación estará disponible en: http://localhost:5000" -ForegroundColor Cyan
Write-Host "📧 Correos: Configurados en .env (MODO_PRUEBA=true)" -ForegroundColor Cyan
Write-Host "📁 Base de datos: MongoDB (Biblioteca)" -ForegroundColor Cyan
Write-Host "`nPresiona Ctrl+C para detener el servidor" -ForegroundColor Yellow
Write-Host "`n" -ForegroundColor Gray

# Iniciar la aplicación
python app.py

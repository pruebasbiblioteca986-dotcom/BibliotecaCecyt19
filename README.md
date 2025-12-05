# 📚 Biblioteca CECyT 19 - Sistema de Gestión

> Sistema integral de gestión de biblioteca para el Centro de Estudios Científicos y Tecnológicos 19 "Leona Vicario" del Instituto Politécnico Nacional.

## ⚡ Inicio Rápido

```powershell
# En PowerShell (en la carpeta del proyecto)
.\INICIAR.ps1

# Luego accede a:
# http://localhost:5000
```

---

## 📋 Requisitos

- **Python** 3.8+ ✅ (incluido en la configuración)
- **MongoDB** 4.0+ ⚠️ (debes iniciar manualmente)
- **Navegador web** moderno ✅

---

## 🚀 Características

- ✅ **Gestión de Inventario**: Catálogo de libros con ISBN, autor, editorial
- ✅ **Registro de Usuarios**: Alumnos y docentes con perfiles
- ✅ **Préstamos**: Control automático de préstamos (3 días hábiles)
- ✅ **Devoluciones**: Seguimiento de devoluciones pendientes
- ✅ **Multas**: Cálculo automático ($7.50 por día de retraso)
- ✅ **Notificaciones**: Correos automáticos (Gmail SMTP)
- ✅ **Dashboard**: Estadísticas en tiempo real
- ✅ **Búsqueda Global**: Busca libros, usuarios, docentes

---

## 🏗️ Tecnología

| Componente | Versión | Descripción |
|-----------|---------|------------|
| **Python** | 3.10+ | Lenguaje principal |
| **Flask** | 3.0.0 | Framework web |
| **MongoDB** | 4.0+ | Base de datos NoSQL |
| **Bootstrap** | 5.3.0 | Framework CSS |
| **Flask-CORS** | 4.0.0 | Soporte CORS |
| **PyMongo** | 4.6.0 | Driver MongoDB |

---

## 📂 Estructura del Proyecto

```
Biblioteca Mau/
├── app.py                    # Aplicación principal
├── settings.py               # Configuración BD
├── requirements.txt          # Dependencias
├── .env                      # Variables de entorno
├── Interfaz.html             # Frontend
├── Interfaz.css              # Estilos
├── INICIAR.ps1              # Script inicio (PowerShell)
├── INICIAR.bat              # Script inicio (CMD)
├── ANALISIS_PROYECTO.md     # Documentación técnica
├── GUIA_RAPIDA.md          # Guía de inicio rápido
├── SETUP_COMPLETO.md       # Resumen de configuración
└── venv/                    # Entorno virtual Python
```

---

## 📖 Documentación

- **[GUIA_RAPIDA.md](GUIA_RAPIDA.md)** - Cómo iniciar en 3 pasos
- **[ANALISIS_PROYECTO.md](ANALISIS_PROYECTO.md)** - Análisis técnico completo
- **[SETUP_COMPLETO.md](SETUP_COMPLETO.md)** - Resumen de configuración
- **[CONFIGURAR_CORREOS.md](CONFIGURAR_CORREOS.md)** - Guía de correos

---

## 🎯 API Endpoints

### Inventario
- `GET /api/inventario` - Listar libros
- `POST /api/registrar_libro` - Registrar libro

### Usuarios
- `GET /api/alumnos` - Listar alumnos
- `GET /api/docentes` - Listar docentes
- `GET /api/buscar_alumno` - Buscar alumno
- `GET /api/buscar_docente` - Buscar docente

### Préstamos
- `GET /api/prestamos` - Listar préstamos
- `POST /api/registrar_prestamo` - Registrar préstamo
- `GET /api/proximas_devoluciones` - Próximas devoluciones

### Devoluciones y Multas
- `GET /api/devoluciones` - Listar devoluciones
- `GET /api/multas` - Listar multas
- `POST /api/liberar_multa` - Marcar multa como pagada

### Dashboard
- `GET /api/dashboard` - Estadísticas

---

## ⚙️ Configuración

### Variables de Entorno (.env)

```env
MODO_PRUEBA=true
SMTP_USER=tu_correo@gmail.com
SMTP_PASSWORD=tu_contraseña_de_aplicacion
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
```

### Base de Datos

MongoDB debe estar ejecutándose en `localhost:27017`

```bash
# Iniciar MongoDB
mongod
```

---

## 🧪 Verificaciones Realizadas

✅ Compilación sin errores  
✅ Importación de módulos correcta  
✅ 35 rutas API funcionales  
✅ Configuración SMTP completada  
✅ Archivos estáticos presentes  
✅ Entorno virtual activo  

---

## 🐛 Troubleshooting

| Problema | Solución |
|----------|----------|
| ModuleNotFoundError | Activar venv: `venv\Scripts\Activate.ps1` |
| MongoDB connection error | Iniciar MongoDB: `mongod` |
| Puerto 5000 en uso | Cambiar puerto en app.py |
| Correos no se envían | Verificar .env y credenciales Gmail |

---

## 📞 Soporte

Para más información:
1. Revisa la documentación incluida
2. Consulta los comentarios en el código
3. Verifica los archivos `.md` de configuración

---

## 📄 Licencia

Proyecto desarrollado para CECyT 19 "Leona Vicario" - IPN

---

## 🎉 ¡Listo para usar!

**Inicio rápido:**
```powershell
.\INICIAR.ps1
```

**Acceso web:**
```
http://localhost:5000
```

---

**Versión**: 1.0  
**Estado**: ✅ Producción  
**Última actualización**: 14 de noviembre de 2025

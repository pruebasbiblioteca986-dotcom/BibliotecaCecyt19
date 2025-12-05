# Configuración de Correo Electrónico

## 📧 Configuración Actual

El sistema de correos está configurado para enviar desde: **bibliotecacecyt19@ipn.com.mx**

Los correos se envían automáticamente a:
- ✅ El correo registrado del alumno o docente en la base de datos
- ✅ Al registrar un préstamo (confirmación)
- ✅ Recordatorios diarios (3, 2, 1 días antes y el día de devolución)
- ✅ Recordatorios de multas pendientes

## 🔧 Qué Necesitas Configurar

### 1. Crear archivo `.env` en la raíz del proyecto

Crea un archivo llamado `.env` (sin extensión) en la misma carpeta donde está `app.py` con el siguiente contenido:

```env
# Servidor SMTP (para IPN generalmente es Office 365)
SMTP_SERVER=smtp.office365.com

# Puerto SMTP (587 para TLS)
SMTP_PORT=587

# Usuario de correo (tu correo completo)
SMTP_USER=bibliotecacecyt19@ipn.com.mx

# Contraseña del correo o contraseña de aplicación
SMTP_PASSWORD=tu_contraseña_aqui

# Correo remitente (debe ser el mismo que SMTP_USER)
EMAIL_FROM=bibliotecacecyt19@ipn.com.mx
```

### 2. Información que Necesitas Obtener

#### a) Servidor SMTP del IPN
- **Opción 1 (Office 365)**: `smtp.office365.com` (puerto 587)
- **Opción 2 (Servidor propio IPN)**: Consulta con tu área de TI del IPN el servidor SMTP correcto (puede ser `smtp.ipn.mx` o similar)

#### b) Credenciales de Correo
- **Usuario**: `bibliotecacecyt19@ipn.com.mx`
- **Contraseña**: La contraseña del correo o una "Contraseña de aplicación" si el correo tiene autenticación de dos factores (2FA) habilitada

### 3. Si el Correo Tiene Autenticación de Dos Factores (2FA)

Si el correo `bibliotecacecyt19@ipn.com.mx` tiene 2FA habilitado, necesitarás crear una **"Contraseña de aplicación"**:

1. Inicia sesión en el correo de Office 365
2. Ve a **Seguridad** → **Información de seguridad**
3. Crea una nueva **Contraseña de aplicación**
4. Usa esa contraseña en lugar de tu contraseña normal en el archivo `.env`

### 4. Verificar que los Usuarios Tengan Correo Registrado

El sistema enviará correos a:
- **Alumnos**: Campo `Correo` o `correo` en la colección `Alumnos`
- **Docentes**: Campo `Correo` o `correo` en la colección `Docentes`

Asegúrate de que todos los usuarios tengan su correo registrado correctamente en la base de datos.

## 🧪 Probar el Sistema de Correos

Una vez configurado el `.env`, puedes probar el sistema:

1. **Registra un préstamo** - Debería enviar un correo de confirmación
2. **Espera los recordatorios diarios** - Se envían automáticamente cada 24 horas
3. **Revisa los logs** - En la consola verás mensajes como:
   - `[EMAIL] ✅ Correo enviado exitosamente a...` (éxito)
   - `[EMAIL] ❌ Error...` (error)

## ⚠️ Notas Importantes

- El archivo `.env` NO debe subirse a Git (ya está en `.gitignore`)
- Si no configuras el `.env`, el sistema funcionará pero solo mostrará mensajes simulados en la consola
- Los correos se envían automáticamente cada 24 horas mediante un hilo en segundo plano
- Puedes forzar el envío manualmente llamando al endpoint `/api/verificar_vencimientos` (POST)

## 📝 Ejemplo de Archivo .env

```env
SMTP_SERVER=smtp.office365.com
SMTP_PORT=587
SMTP_USER=bibliotecacecyt19@ipn.com.mx
SMTP_PASSWORD=TuContraseñaSegura123
EMAIL_FROM=bibliotecacecyt19@ipn.com.mx
```

## 🔍 Solución de Problemas

### Error: "SMTPAuthenticationError"
- Verifica que la contraseña sea correcta
- Si tienes 2FA, usa una contraseña de aplicación
- Verifica que el usuario SMTP_USER sea correcto

### Error: "No se puede conectar al servidor SMTP"
- Verifica que SMTP_SERVER y SMTP_PORT sean correctos
- Verifica tu conexión a internet
- Consulta con TI del IPN si hay restricciones de firewall

### Los correos no se envían pero no hay error
- Revisa la consola del servidor para ver los mensajes de log
- Verifica que los usuarios tengan correo registrado en la base de datos
- Verifica que el correo del usuario sea válido



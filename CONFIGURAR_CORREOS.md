# 📧 Configuración de Correos para Pruebas

## Pasos Rápidos (5 minutos)

### 1. Crea el archivo `.env`

En la misma carpeta donde está `app.py`, crea un archivo llamado `.env` (sin extensión) con este contenido:

**Opción A: Enviar a correos reales de usuarios (recomendado)**
```env
MODO_PRUEBA=true
SMTP_USER=tu_correo@gmail.com
SMTP_PASSWORD=tu_contraseña_de_aplicacion
# CORREO_PRUEBA= (déjalo vacío o no lo pongas)
```

**Opción B: Redirigir todos los correos a tu correo (para pruebas controladas)**
```env
MODO_PRUEBA=true
SMTP_USER=tu_correo@gmail.com
SMTP_PASSWORD=tu_contraseña_de_aplicacion
CORREO_PRUEBA=tu_correo@gmail.com
```

### 2. Obtén tu Contraseña de Aplicación de Gmail

1. Ve a: https://myaccount.google.com/security
2. Activa "Verificación en 2 pasos" (si no está activa)
3. Busca "Contraseñas de aplicaciones" o ve a: https://myaccount.google.com/apppasswords
4. Selecciona:
   - **Aplicación**: Correo
   - **Dispositivo**: Otro (nombre personalizado) → escribe "Biblioteca"
5. Copia la contraseña de 16 caracteres (ejemplo: `abcd efgh ijkl mnop`)
6. Pégala en `SMTP_PASSWORD` en tu archivo `.env`

### 3. Completa tu archivo `.env`

**Para enviar a correos reales de usuarios:**
```env
MODO_PRUEBA=true
SMTP_USER=tu_correo@gmail.com
SMTP_PASSWORD=abcd efgh ijkl mnop
```

**Para redirigir todos a tu correo (opcional):**
```env
MODO_PRUEBA=true
SMTP_USER=tu_correo@gmail.com
SMTP_PASSWORD=abcd efgh ijkl mnop
CORREO_PRUEBA=tu_correo@gmail.com
```

**Reemplaza:**
- `tu_correo@gmail.com` → Tu correo Gmail real
- `abcd efgh ijkl mnop` → La contraseña de aplicación que copiaste

### 4. Reinicia el servidor

```bash
# Detén el servidor (Ctrl+C) y vuelve a iniciarlo
python3 app.py
```

## ✅ Listo

**Si NO configuraste CORREO_PRUEBA:**
- Los correos se enviarán a los correos reales de los usuarios registrados en la base de datos
- Usarás Gmail SMTP para enviar (más fácil para pruebas)

**Si SÍ configuraste CORREO_PRUEBA:**
- Todos los correos se redirigirán a tu correo (útil para pruebas controladas)
- Verás quién era el destinatario original en el cuerpo del correo

## 📝 Ejemplo Completo

Si tu correo es `juan.perez@gmail.com`, tu archivo `.env` quedaría así:

```env
MODO_PRUEBA=true
SMTP_USER=juan.perez@gmail.com
SMTP_PASSWORD=abcd efgh ijkl mnop
CORREO_PRUEBA=juan.perez@gmail.com
```

## 🔍 Verificar que Funciona

1. Registra un préstamo
2. Deberías recibir un correo de confirmación en tu correo
3. Revisa la consola del servidor, deberías ver: `[EMAIL] ✅ Correo enviado exitosamente...`

## ⚠️ Si No Funciona

- **Error de autenticación**: Verifica que la contraseña de aplicación sea correcta (16 caracteres sin espacios o con espacios, ambos funcionan)
- **No llegan correos**: Revisa la carpeta de spam
- **Error de conexión**: Verifica tu conexión a internet


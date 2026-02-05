# Guía de Integración - NiceGUI con APSA Dashboard

## 🎯 Objetivo

Guía paso a paso para integrar una aplicación NiceGUI con el sistema Lazy SSO de APSA Portal Dashboard.

## 📋 Pre-requisitos

Antes de comenzar, asegúrate de tener:

- ✅ Acceso al portal APSA Dashboard (como administrador)
- ✅ Docker y Docker Compose instalados
- ✅ Apache proxy reverso configurado
- ✅ Dominio/subdominio para proxy reverso accesible (ej: `petunia.apsagroup.com`)

## 🚀 Paso 1: Clonar la Plantilla

```bash
# Opción A: Clonar desde repositorio
git clone <repo-url> mi-aplicacion-nicegui
cd mi-aplicacion-nicegui

# Opción B: Copiar archivos manualmente
mkdir mi-aplicacion-nicegui
cd mi-aplicacion-nicegui
# Copiar main.py, Dockerfile, docker-compose.yml, etc.
```

## 📝 Paso 2: Configurar Variables de Entorno

```bash
# 1. Copiar plantilla
cp .env.example .env

# 2. Editar con tu editor favorito
nano .env
```

### Variables Críticas a Configurar

```env
# URL del portal (DEBE ser HTTPS en producción)
PORTAL_URL=https://petunia.apsagroup.com

# Nombre de tu aplicación (será visible en el portal)
APP_NAME=Mi Aplicación Cool

# CRÍTICO: Debe coincidir con el audience registrado en el portal para la aplicación
APP_AUDIENCE=mi-app-cool

# Base path del proxy reverso a la aplicación
BASE_PATH=/mi-app-cool
```

### ⚠️ IMPORTANTE: APP_AUDIENCE

El valor de `APP_AUDIENCE` debe coincidir **EXACTAMENTE** con el campo `audience` de la webapp en APSA Portal Dashboard, hecho que podremos corroborar a través del frontend de administración de APSA Portal Dashboard, o también directamente via SQL:

```sql
-- En la BD del portal, el campo name debe ser igual:
SELECT name FROM webapps WHERE name = 'mi-app-cool';
```

Si no coinciden → **Token inválido** → Autenticación falla ❌

## 👨‍💻 Paso 2.5: Implementar Lógica SSO Lazy (Código Python)

El sistema ahora utiliza **"Lazy SSO"** para eficiencia, ya que el tamaño de token que se puede proporcionar via url a las apliaciones tiene un límite de tamaño y hay que manejarlo con cuidado. Esto significa que toda aplicación debe realizar la validación en **dos pasos**:

1. **Validar JWT (Local):** Verificar firma y expiración del token mínimo (implica token de tamaño mínimo).
2. **Obtener Datos (Remoto):** Llamar al endpoint `/internal/session-data` para obtener permisos y datos de perfil adicionales (sin restricción de tamaño ya que la respuesta es via JSON).

### Código de Validación en `main.py`

Debes asegurarte de que tu función de validación se vea así:

```python
import requests
import jwt

# ... imports ...

def validate_token_and_get_user(token: str) -> Optional[dict]:
    """
    Valida el token SSO en dos pasos:
    1. Valida firma y expiración del JWT mínimo localmente
    2. Recupera datos completos de sesión del Portal
    
    Args:
        token: JWT string recibido en URL
        
    Returns:
        dict: User data completo o None si es inválido
    """
    try:
        # PASO 1: Validación Local del JWT Mínimo
        # ----------------------------------------
        # Solo verificamos que fue firmado por el Portal y es para nosotros
        payload_min = jwt.decode(
            token,
            PUBLIC_KEY_CONTENT,  # Tu clave pública del portal
            algorithms=['RS256'],
            audience=os.getenv('APP_AUDIENCE')
        )
        
        # PASO 2: Recuperación de Datos (Lazy Load)
        # -----------------------------------------
        # Usamos el JTI y Email para pedir los datos completos
        # El portal valida que la sesión siga activa en Redis
        response = requests.post(
            f"{os.getenv('PORTAL_URL')}/internal/session-data",
            json={
                'jti': payload_min['jti'],
                'email': payload_min['email']
            },
            timeout=5,  # Importante: timeout corto
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code != 200:
            print(f"❌ Error recuperando sesión: {response.text}")
            return None
            
        # Retornamos el payload completo (con permisos, nombre, foto, etc.)
        full_payload = response.json()
        print(f"✅ Sesión recuperada para: {full_payload.get('email')}")
        return full_payload

    except jwt.ExpiredSignatureError:
        print("❌ Token expirado")
        return None
    except jwt.InvalidTokenError as e:
        print(f"❌ Token inválido: {e}")
        return None
    except Exception as e:
        print(f"❌ Error inesperado en validación: {e}")
        return None
```

> [!IMPORTANT]
> El token JWT recibido en la URL **ya no contiene** `permissions`, `name` o `picture`. Si intentas usarlos directamente del token descifrado, tu aplicación fallará. **Debes** hacer la llamada a `/internal/session-data`.

## 🏗️ Paso 3: Registrar en APSA Dashboard

### 3.1 Acceder al Panel de Administración

1. Ir a `https://petunia.apsagroup.com`
2. Login como administrador
3. Click en "Panel Administración"

### 3.2 Crear Nueva Aplicación

1. Ir a **"Aplicaciones Web"** → **"Nueva Aplicación"**

2. **Completar formulario:**
   ```
   Nombre:          Mi App Cool 
   Descripción:     Es mi Aplicación Cool sólo para regocijo personal
   URL:             https://petunia.apsagroup.com/mi-app-cool/
   Categoría:       [Seleccionar apropiada]
   Tipo (Origin):   internal           # ← Para SSO con JWT
   Audiencia:       mi-app-cool        # ← DEBE coincidir con APP_AUDIENCE
   Icono:           bi-grid-3x3        # ← Cualquier icono Bootstrap
   ... etc
   Activa:          ✓ Sí
   ```

3. **Guardar**

### 3.3 Asignar Permisos

1. Ir a **"Perfiles de Acceso"**
2. Editar el perfil deseado (ej: "Desarrollador")
3. Marcar checkbox de "mi-app-cool"
4. Guardar

O alternativamente:

1. Ir a **"Usuarios"**
2. Editar usuario específico
3. En "Aplicaciones Adicionales" marcar "mi-app-cool"
4. Guardar

## 🔧 Paso 4: Asegurar Configuración Apache Reverse Proxy

### 4.1 Configuración del Virtual Host (Apache 2.4)

Asegúrate de tener habilitados los módulos necesarios:
```bash
sudo a2enmod proxy proxy_http proxy_wstunnel rewrite headers
sudo systemctl restart apache2
```

Edita tu archivo de configuración (ej: `/etc/apache2/sites-available/petunia-apsagroup.conf`):

```apache
<VirtualHost *:443>
    ServerName petunia.apsagroup.com
    
    # ... configuración SSL existente ...

    # ============================================
    # LOCATION PARA TU APLICACIÓN NICEGUI
    # ============================================
    <Location /nicegui-demo/>
        ProxyPreserveHost On
        
        # Headers críticos para que la app sepa que está detrás de HTTPS
        RequestHeader set X-Forwarded-Proto "https"
        RequestHeader set X-Forwarded-Host "petunia.apsagroup.com"
        RequestHeader set X-Forwarded-Port "443"
        RequestHeader set X-Forwarded-Prefix "/nicegui-demo"
        
        # WebSocket Support (CRÍTICO para NiceGUI/SocketIO)
        # Detecta headers de Upgrade y Connection para redirigir al protocolo ws://
        # IMPORTANTE: RewriteRule elimina el prefijo /nicegui-demo/ antes de conectar
        RewriteEngine On
        RewriteCond %{HTTP:Upgrade} =websocket [NC]
        RewriteCond %{HTTP:Connection} upgrade [NC]
        RewriteRule ^/nicegui-demo/(.*)$ ws://localhost:8080/$1 [P,L]
        
        # HTTP normal - ProxyPass también elimina el prefijo automáticamente
        ProxyPass http://localhost:8080/
        ProxyPassReverse http://localhost:8080/
        
    </Location>
</VirtualHost>
```

> [!NOTE]
> Ajusta `localhost:8080` a la IP/host correcto donde corre tu contenedor Docker (ej: `http://172.17.0.2:8080/` o el nombre del servicio en docker-compose si Apache está en la misma red).

### 4.2 Validar y Recargar Apache

```bash
# Validar sintaxis
sudo apachectl configtest

# Si está OK, recargar
sudo systemctl reload apache2
```

## 🐳 Paso 5: Construir y Ejecutar con Docker

### 5.1 Construir Imagen

```bash
# Construir imagen
docker compose build

# O si quieres forzar reconstrucción completa
docker compose build --no-cache
```

### 5.2 Ejecutar Contenedor

```bash
# Iniciar en background
docker compose up -d

# Ver logs en tiempo real
docker compose logs -f
```

### 5.3 Verificar Estado

```bash
# Ver estado del contenedor
docker compose ps

# Debería mostrar algo como:
# NAME                STATUS              PORTS
# nicegui-sso-demo    Up 10 seconds       0.0.0.0:8080->8080/tcp
```

### 5.4 Health Check

```bash
# Verificar health endpoint
curl http://localhost:8080/health

# Respuesta esperada:
{
  "status": "healthy",
  "app": "Mi Aplicación Cool",
  "audience": "mi-app-cool"
}
```

## ✅ Paso 6: Probar la Integración

### 6.1 Flujo Completo de Autenticación

1. **Ir al portal:** `https://petunia.apsagroup.com`

2. **Login con Google** (o administrador local)

3. **En el dashboard**, buscar tu aplicación en el menú lateral

4. **Click en "Mi Aplicación Cool"**

5. **Verificar que:**
   - ✅ La aplicación carga correctamente
   - ✅ Se muestra tu nombre e email
   - ✅ Se listan tus permisos
   - ✅ La información del token es correcta

### 6.2 Verificar Logs

```bash
# Ver logs de autenticación
docker compose logs | grep "Token validado"

# Debería mostrar algo como:
# ✓ Token validado para usuario: usuario@example.com
# ✓ Sesión establecida para: usuario@example.com
# ✓ Renovación automática iniciada (cada 240s)
```

### 6.3 Verificar Renovación Automática

Espera 4-5 minutos y verifica los logs:

```bash
docker compose logs | grep "renovado"

# Debería mostrar:
# ✓ Token auto-renovado (14:35:42)
```

## 🐛 Troubleshooting Común

### Problema 1: "Token inválido o expirado"

**Síntoma:** Error inmediato al cargar la aplicación

**Verificación:**
```bash
# 1. Verificar APP_AUDIENCE en .env
cat .env | grep APP_AUDIENCE

# 2. Verificar nombre en base de datos del portal
docker exec -it apsa-dashboard-db psql -U apsa_user -d apsa_dashboard \
  -c "SELECT id, name FROM webapps WHERE name LIKE '%mi-app%';"

# 3. Deben coincidir EXACTAMENTE
```

**Solución:**
```bash
# Si no coinciden, actualizar .env
nano .env
# Cambiar APP_AUDIENCE al valor correcto

# Reiniciar
docker compose restart
```

### Problema 2: "No se proporcionó token"

**Síntoma:** Error al acceder directamente a la URL

**Causa:** Acceso directo sin pasar por portal

**Solución:**
```
❌ NO: https://petunia.apsagroup.com/mi-app-cool/
✅ SÍ: https://petunia.apsagroup.com → Click en app
```

### Problema 3: WebSocket Connection Failed

**Síntoma:** Error en consola del navegador

**Verificación:**
```bash
# Verificar configuración de Apache
sudo apachectl -t

# Verificar log de errores
sudo tail -f /var/log/apache2/error.log
```

**Solución:**

Asegurar que Apache tenga los módulos cargados (`proxy_wstunnel`) y la RewriteRule correcta para WebSockets.

### Problema 4: "Error obteniendo clave pública"

**Síntoma:** Falla al validar token

**Verificación:**
```bash
# Verificar conectividad con portal
docker compose exec nicegui-demo curl https://petunia.apsagroup.com/internal/public-key
```

**Solución:**
```bash
# 1. Verificar PORTAL_URL en .env
cat .env | grep PORTAL_URL

# 2. Verificar que portal esté corriendo
curl https://petunia.apsagroup.com/health

# 3. Invalidar cache y reintentar
docker compose exec nicegui-demo rm -f cache/portal_public.pem
docker compose restart
```

## 🎨 Paso 7: Personalizar UI

### 7.1 Modificar main.py

```python
# Reemplazar las funciones create_*_card() con tu UI personalizada

@ui.page('/')
async def index_page():
    # Mantener autenticación
    await auth_middleware()
    
    auth_error = app.storage.user.get('auth_error')
    if auth_error:
        # Mostrar error (puedes personalizar)
        show_error_page(auth_error)
        return
    
    user_data = session_manager.get_current_user()
    if not user_data:
        show_loading()
        return
    
    # ============================================
    # TU UI PERSONALIZADA AQUÍ
    # ============================================
    create_header(user_data)
    
    with ui.column().classes('w-full p-8'):
        ui.label(f'¡Hola {user_data["name"]}!').classes('text-3xl')
        
        # Tu funcionalidad aquí
        with ui.card():
            ui.label('Mi Funcionalidad Cool')
            ui.button('Hacer algo', on_click=mi_funcion)
```

### 7.2 Agregar Nuevas Páginas

```python
@ui.page('/mi-pagina')
async def mi_pagina():
    # SIEMPRE incluir middleware primero
    await auth_middleware()
    
    user_data = session_manager.get_current_user()
    if not user_data:
        ui.navigate.to('/')
        return
    
    # Tu página aquí
    ui.label('Mi Página Protegida')
```

## 📦 Paso 8: Desplegar a Producción

### 8.1 Preparación

```bash
# 1. Revisar variables de entorno
cat .env

# 2. Asegurar que PORTAL_URL sea HTTPS
# PORTAL_URL=https://petunia.apsagroup.com  ✓

# 3. Construir imagen optimizada
docker compose build --no-cache
```

### 8.2 Iniciar en Producción

```bash
# Iniciar con restart policy
docker compose up -d

# Verificar logs
docker compose logs -f

# Debería ver:
# ✓ Clave pública descargada y cacheada
# ✓ Token validado para usuario: ...
```

### 8.3 Monitoreo Continuo

```bash
# Ver estado
docker compose ps

# Ver uso de recursos
docker stats nicegui-sso-demo

# Ver logs recientes
docker compose logs --tail=100 -f
```

## 🔄 Paso 9: Mantenimiento

### Actualizar Aplicación

```bash
# 1. Hacer backup de personalizaciones
cp main.py main.py.backup

# 2. Pull últimos cambios (si usas git)
git pull origin main

# 3. Reconstruir
docker compose down
docker compose build --no-cache
docker compose up -d
```

### Rotar Caché de Clave Pública

```bash
# Si la clave RSA del portal cambia
docker compose exec nicegui-demo rm -f cache/portal_public.pem
docker compose restart
```

### Ver Logs Históricos

```bash
# Logs de un periodo específico
docker compose logs --since 2024-01-10T10:00:00

# Logs con timestamp
docker compose logs -t
```

## ✨ Consejos Finales

### Seguridad

1. ✅ **NUNCA** almacenar tokens en localStorage del navegador
2. ✅ **SIEMPRE** usar `app.storage.user` de NiceGUI
3. ✅ **VALIDAR** token en cada request crítico
4. ✅ **RENOVAR** tokens automáticamente antes de expiración

### Performance

1. ✅ **Cache** de clave pública RSA (ya implementado)
2. ✅ **Lazy loading** de componentes pesados
3. ✅ **Optimizar** queries a la base de datos (si aplica)
4. ✅ **Comprimir** assets estáticos

### UX

1. ✅ **Indicadores de carga** mientras valida token
2. ✅ **Mensajes de error** claros y útiles
3. ✅ **Notificaciones** de renovación de sesión
4. ✅ **Logout** limpio que limpie sesión

## 📚 Recursos Adicionales

- [Documentación APSA Dashboard](../README.md)
- [NiceGUI Documentation](https://nicegui.io/)
- [JWT Best Practices](https://tools.ietf.org/html/rfc8725)
- [Docker Compose Reference](https://docs.docker.com/compose/)

## 🆘 Obtener Ayuda

Si encuentras problemas:

1. ✅ Revisar esta guía completa
2. ✅ Consultar logs: `docker compose logs -f`
3. ✅ Verificar configuración del portal
4. ✅ Consultar troubleshooting en README.md
5. ✅ Abrir issue en repositorio

---


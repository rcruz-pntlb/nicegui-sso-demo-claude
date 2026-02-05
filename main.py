"""
NiceGUI SSO Demo - Plantilla de referencia para integración con APSA Dashboard
Versión: 1.0.0
Autor: APSA Group
Fecha: 2025-01-10

Esta aplicación demuestra:
- Validación de tokens JWT del portal APSA Dashboard
- Manejo de sesiones de usuario con app.storage
- Renovación automática de tokens
- UI responsive y funcional
- Configuración para proxy reverso (https://petunia.apsagroup.com/nicegui-demo/)
"""

from nicegui import ui, app
import jwt
import httpx
import os
from datetime import datetime, timezone
from typing import Optional, Dict
import asyncio
from pathlib import Path
from fastapi import Request
from fastapi.responses import RedirectResponse
from starlette.middleware.base import BaseHTTPMiddleware



# ==========================================
# CONFIGURACIÓN
# ==========================================

class Config:
    """Configuración centralizada de la aplicación"""
    
    # Portal SSO
    PORTAL_URL = os.getenv('PORTAL_URL', 'https://petunia.apsagroup.com')
    # EL PORTAL INTERNAL PARA APSA-PORTAL FACILITA LA COMUNICACION CON APLICACION CLIENTE
    # al consumir la api internal de apsa-dashboard, utilizará la ip interna, ya que por 
    # motivos de seguridad, acceder a través de portal_url introduce limitaciones
    PORTAL_INTERNAL_URL = os.getenv('PORTAL_INTERNAL_URL', PORTAL_URL)
    PORTAL_PUBLIC_KEY_ENDPOINT = f'{PORTAL_INTERNAL_URL}/internal/public-key'
    PORTAL_VERIFY_ENDPOINT = f'{PORTAL_INTERNAL_URL}/internal/verify'
    PORTAL_REFRESH_ENDPOINT = f'{PORTAL_INTERNAL_URL}/internal/refresh'
    PORTAL_SESSION_DATA_ENDPOINT = f'{PORTAL_INTERNAL_URL}/internal/session-data'
    
    # Aplicación
    APP_NAME = os.getenv('APP_NAME', 'NiceGUI SSO Demo')
    APP_AUDIENCE = os.getenv('APP_AUDIENCE', 'nicegui-demo')
    
    # Tokens
    TOKEN_REFRESH_INTERVAL = int(os.getenv('TOKEN_REFRESH_INTERVAL', '240'))  # 4 minutos
    TOKEN_MIN_VALIDITY = int(os.getenv('TOKEN_MIN_VALIDITY', '60'))  # 1 minuto
    
    # Proxy
    BASE_PATH = os.getenv('BASE_PATH', '/nicegui-demo')
    
    # Cache
    PUBLIC_KEY_PATH = Path('cache/portal_public.pem')


# ==========================================
# GESTIÓN DE CLAVE PÚBLICA
# ==========================================

class PublicKeyManager:
    """Gestor de clave pública RSA del portal con cache"""
    
    def __init__(self):
        self._public_key: Optional[str] = None
        self._ensure_cache_dir()
    
    def _ensure_cache_dir(self):
        """Crear directorio de cache si no existe"""
        Config.PUBLIC_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    async def get_public_key(self, force_refresh: bool = False) -> str:
        """
        Obtener clave pública (desde cache o descargando)
        
        Args:
            force_refresh: Si es True, ignora el cache y fuerza descarga
        """
        if self._public_key and not force_refresh:
            return self._public_key
        
        # Intentar cargar desde cache (si no forzamos refresh)
        if not force_refresh and Config.PUBLIC_KEY_PATH.exists():
            try:
                self._public_key = Config.PUBLIC_KEY_PATH.read_text()
                print(f'✓ Clave pública cargada desde cache')
                return self._public_key
            except Exception as e:
                print(f'⚠ Error leyendo cache: {e}')
        
        # Descargar desde portal
        try:
            print(f'🔄 Intentando descargar clave pública de {Config.PORTAL_PUBLIC_KEY_ENDPOINT}...')
            async with httpx.AsyncClient(verify=True, timeout=10.0) as client:  # Disable verify for internal/dev issues
                response = await client.get(
                    Config.PORTAL_PUBLIC_KEY_ENDPOINT,
                    timeout=3.0  # Reduce timeout to fail fast
                )
                response.raise_for_status()
                self._public_key = response.text
                
                # Guardar en cache
                try:
                    Config.PUBLIC_KEY_PATH.write_text(self._public_key)
                    print(f'✓ Clave pública descargada y cacheada')
                except Exception as e:
                    print(f'⚠ No se pudo escribir cache: {e}')
                
                return self._public_key
        
        except Exception as e:
            error_msg = f'Error obteniendo clave pública: {e}'
            print(f'✗ {error_msg}')
            raise RuntimeError(error_msg)
    
    def invalidate_cache(self):
        """Invalidar cache de clave pública"""
        self._public_key = None
        if Config.PUBLIC_KEY_PATH.exists():
            Config.PUBLIC_KEY_PATH.unlink()
            print('✓ Cache de clave pública invalidado')


# Instancia global
public_key_manager = PublicKeyManager()


# ==========================================
# VALIDACIÓN DE TOKENS
# ==========================================

class TokenValidator:
    """Validador de tokens JWT del portal"""

    @classmethod
    async def validate_token(cls, token: str) -> Optional[Dict]:
        """
        Validar token JWT contra el portal usando estrategia Lazy SSO
        
        Args:
            token: Token JWT a validar
            
        Returns:
            Payload del token completo si es válido, None si es inválido
        """
        return await cls._validate_token_logic(token, force_refresh_key=False)

    @classmethod
    async def _validate_token_logic(cls, token: str, force_refresh_key: bool = False) -> Optional[Dict]:
        """Lógica interna de validación con soporte para reintento"""
        if not token:
            print('✗ Token vacío recibido')
            return None
        
        try:
            # ----------------------------------------
            # PASO 1: Validación Local del JWT Mínimo
            # ----------------------------------------
            print(f'🔐 PASO 1: Validando firma JWT localmente...')
            public_key = await public_key_manager.get_public_key(force_refresh=force_refresh_key)
            
            # Validar token localmente (firma y expiración)
            payload_min = jwt.decode(
                token,
                public_key,
                algorithms=['RS256'],
                audience=Config.APP_AUDIENCE,
                options={'verify_exp': True}
            )
            print(f'   ✓ JWT válido (sub={payload_min.get("sub")}, jti={payload_min.get("jti")[:10]}...)')
            
            # -----------------------------------------
            # PASO 2: Recuperación de Datos (Lazy Load)
            # -----------------------------------------
            print(f'🌐 PASO 2: Recuperando datos de sesión...')
            session_url = Config.PORTAL_SESSION_DATA_ENDPOINT
            request_data = {
                'jti': payload_min.get('jti'),
                'email': payload_min.get('email')
            }
            
            # Logging detallado
            print(f'   🔗 URL: {session_url}')
            print(f'   📦 Payload: jti={request_data["jti"][:10]}..., email={request_data["email"]}')
            print(f'   🔒 SSL Verify: False (desarrollo)')
            
            async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
                response = await client.post(
                    session_url,
                    json=request_data,
                    headers={
                        'Content-Type': 'application/json',
                        # Si el portal requiere CSRF (no debería), descomentar:
                        # 'X-CSRFToken': 'bypass',
                    }
                )
                
                # Logging de respuesta
                print(f'   📊 Status Code: {response.status_code}')
                print(f'   📄 Response Headers: {dict(response.headers)}')
                
                if response.status_code != 200:
                    print(f'   ✗ Error HTTP {response.status_code}')
                    print(f'   📝 Response Body (primeros 500 chars):')
                    print(f'      {response.text[:500]}')
                    return None
                
                # Parsear respuesta
                try:
                    full_payload = response.json()
                    print(f'   ✓ Datos recuperados exitosamente')
                    print(f'   👤 Usuario: {full_payload.get("email")} ({full_payload.get("name")})')
                    print(f'   🎭 Perfil: {full_payload.get("profile")}')
                    print(f'   🔑 Permisos: {len(full_payload.get("permissions", []))} apps')
                    
                    # IMPORTANTE: Combinar claims del JWT mínimo con datos completos
                    # El full_payload del portal NO incluye iss, aud, iat, exp, jti
                    # pero los necesitamos para mostrarlos en create_token_card()
                    full_payload.update({
                        'iss': payload_min.get('iss'),
                        'aud': payload_min.get('aud'),
                        'iat': payload_min.get('iat'),
                        'exp': payload_min.get('exp'),
                        'jti': payload_min.get('jti')
                    })
                    
                    print(f'   ✓ Claims JWT agregados: iss={payload_min.get("iss")}, aud={payload_min.get("aud")}')
                    return full_payload
                except Exception as e:
                    print(f'   ✗ Error parseando JSON: {e}')
                    print(f'   📝 Response: {response.text[:200]}')
                    return None
        
        except (jwt.InvalidSignatureError, jwt.DecodeError) as e:
            # Si falla la firma y NO hemos forzado ya el refresh, intentamos de nuevo
            if not force_refresh_key:
                print(f'⚠ Error de firma ({e}). Intentando actualizar clave pública...')
                return await cls._validate_token_logic(token, force_refresh_key=True)
            else:
                print(f'✗ Token con firma inválida (incluso tras actualizar clave): {e}')
                return None
                
        except jwt.ExpiredSignatureError:
            print('⚠ Token expirado')
            return None
        except jwt.InvalidAudienceError:
            print(f'✗ Audience inválido. Esperado: {Config.APP_AUDIENCE}')
            return None
        except jwt.InvalidTokenError as e:
            print(f'✗ Token inválido: {e}')
            return None
        except httpx.RequestError as e:
            print(f'✗ Error de red llamando al portal: {e}')
            print(f'   URL intentada: {session_url}')
            return None
        except Exception as e:
            print(f'✗ Error inesperado validando token: {e}')
            import traceback
            traceback.print_exc()
            return None
    
    @staticmethod
    async def refresh_token(current_token: str) -> Optional[str]:
        """
        Renovar token a través del portal
        
        Args:
            current_token: Token actual a renovar
            
        Returns:
            Nuevo token si se renovó exitosamente, None si falló
        """
        try:
            refresh_url = Config.PORTAL_REFRESH_ENDPOINT
            print(f'🔄 Renovando token...')
            print(f'   URL: {refresh_url}')
            
            async with httpx.AsyncClient(verify=False, timeout=10.0) as client:
                response = await client.post(
                    refresh_url,
                    json={'token': current_token},
                    headers={'Content-Type': 'application/json'}
                )
                
                print(f'   Status: {response.status_code}')
                
                if response.status_code != 200:
                    print(f'✗ Error renovando: {response.text[:200]}')
                    return None
                
                data = response.json()
                new_token = data.get('token')
                
                if new_token:
                    print('✓ Token renovado exitosamente')
                    return new_token
                else:
                    print('✗ Respuesta de refresh sin token')
                    return None
        
        except Exception as e:
            print(f'✗ Error renovando token: {e}')
            return None   
    
    @staticmethod
    async def refresh_token(current_token: str) -> Optional[str]:
        """
        Renovar token a través del portal
        
        Args:
            current_token: Token actual a renovar
            
        Returns:
            Nuevo token si se renovó exitosamente, None si falló
        """
        try:
            async with httpx.AsyncClient(verify=True, timeout=10.0) as client:
                response = await client.post(
                    Config.PORTAL_REFRESH_ENDPOINT,
                    json={'token': current_token},
                    timeout=10.0
                )
                response.raise_for_status()
                
                data = response.json()
                new_token = data.get('token')
                
                if new_token:
                    print('✓ Token renovado exitosamente')
                    return new_token
                else:
                    print('✗ Respuesta de refresh sin token')
                    return None
        
        except Exception as e:
            print(f'✗ Error renovando token: {e}')
            return None


# ==========================================
# GESTIÓN DE SESIÓN
# ==========================================

class SessionManager:
    """Gestor de sesión de usuario con renovación automática"""
    
    def __init__(self):
        self._refresh_task = None
    
    def get_current_user(self) -> Optional[Dict]:
        """Obtener datos del usuario actual"""
        return app.storage.user.get('user_data')
    
    def get_current_token(self) -> Optional[str]:
        """Obtener token actual"""
        return app.storage.user.get('sso_token')
    
    async def set_session(self, token: str, user_data: Dict):
        """
        Establecer sesión de usuario
        
        Args:
            token: Token JWT validado
            user_data: Datos del usuario del payload
        """
        app.storage.user['sso_token'] = token
        app.storage.user['user_data'] = user_data
        app.storage.user['login_time'] = datetime.now(timezone.utc).isoformat()
        
        print(f'✓ Sesión establecida para: {user_data.get("email")}')
        
        # Iniciar renovación automática
        await self.start_token_refresh()
    
    def clear_session(self):
        """Limpiar sesión de usuario"""
        if self._refresh_task:
            self._refresh_task.cancel()
            self._refresh_task = None
        
        app.storage.user.clear()
        print('✓ Sesión limpiada')
    
    async def start_token_refresh(self):
        """Iniciar tarea de renovación automática de token"""
        if self._refresh_task:
            self._refresh_task.cancel()
        
        async def refresh_loop():
            """Loop de renovación de token"""
            while True:
                try:
                    await asyncio.sleep(Config.TOKEN_REFRESH_INTERVAL)
                    
                    current_token = self.get_current_token()
                    if not current_token:
                        break
                    
                    # Renovar token
                    new_token = await TokenValidator.refresh_token(current_token)
                    
                    if new_token:
                        # Validar nuevo token
                        user_data = await TokenValidator.validate_token(new_token)
                        
                        if user_data:
                            app.storage.user['sso_token'] = new_token
                            app.storage.user['user_data'] = user_data
                            print(f'✓ Token auto-renovado ({datetime.now().strftime("%H:%M:%S")})')
                        else:
                            print('✗ Nuevo token inválido, cerrando sesión')
                            self.clear_session()
                            break
                    else:
                        print('✗ Fallo en renovación, cerrando sesión')
                        self.clear_session()
                        break
                
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    print(f'✗ Error en loop de renovación: {e}')
                    break
        
        self._refresh_task = asyncio.create_task(refresh_loop())
        print(f'✓ Renovación automática iniciada (cada {Config.TOKEN_REFRESH_INTERVAL}s)')


# Instancia global
session_manager = SessionManager()


# ==========================================
# MIDDLEWARE DE AUTENTICACIÓN
# ==========================================

@app.middleware("http")
async def debug_middleware(request: Request, call_next):
    try:
        # Solo loguear peticiones relevantes (excluir estáticos para reducir ruido)
        if not request.url.path.startswith('/_nicegui') and not request.url.path.startswith('/static'):
            print(f"🔍 DEBUG: {request.method} {request.url}")
            print(f"   Root: {request.scope.get('root_path')}")
            # print(f"   Headers: {dict(request.headers)}")
    except Exception:
        pass
    return await call_next(request)

# app.add_middleware(DebugMiddleware) eliminado a favor del decorador

@app.middleware("http")
async def sso_middleware(request: Request, call_next):
    # Interceptar POST a la raíz (callback del SSO)
    if request.method == "POST" and request.url.path == "/":
        try:
            print("🔄 SSO Middleware (ASGI): Interceptando POST /")
            # Consumir el form data
            form = await request.form()
            token = form.get('token')
            
            if token:
                # Usar redirección relativa para asegurar la ruta correcta
                target_url = f"./?token={token}"
                print(f"🔄 SSO Middleware: Redirigiendo a -> {target_url}")
                return RedirectResponse(url=target_url, status_code=303)
            else:
                print("⚠ SSO Middleware: No se encontró token en el POST")
                
        except Exception as e:
            print(f"⚠ Error en SSO Middleware: {e}")
            # En caso de error, podríamos dejar pasar o devolver error.
            # Si ya consumimos el body, call_next fallará. Mejor devolver respuesta de error.
            return RedirectResponse(url='./?error=sso_middleware_exception', status_code=303)

    return await call_next(request)

# Nota: app.add_middleware no es necesario con el decorador @app.middleware


async def auth_middleware(token_url: str = None):
    """Middleware para validar autenticación en cada request"""
    
    # Si viene un token nuevo, forzamos re-validación limpiando estados de error previos
    if token_url:
        print(f"🔄 Forzando re-validación con nuevo token recibido")
        app.storage.user['auth_checked'] = False
        app.storage.user['auth_error'] = None
    
    # Excluir rutas públicas (si ya fue chequeado y no estamos forzando re-validación)
    if app.storage.user.get('auth_checked'):
        return
    
    # Obtener token de URL o sesión
    token = None
    
    # Remove app.add_middleware(DebugMiddleware) if present nearby or just assume it's gone with previous edit
    
    # 1. Intentar obtener de query params (ARGUMENTO o REQUEST)
    if token_url:
        print(f"🔍 DEBUG: Token recibido como argumento: {token_url[:10]}...")
        token = token_url
    elif hasattr(ui.context.client, 'query'):
        print(f"🔍 DEBUG: Query Params disponibles: {ui.context.client.query}")
        token = ui.context.client.query.get('token')
    
    # 2. Si no hay en URL, intentar desde sesión
    if not token:
        token = session_manager.get_current_token()
        if token:
            print(f'✓ Token recuperado de sesión')
    
    # 3. Si no hay token, mostrar error
    if not token:
        print('✗ No se encontró token')
        app.storage.user['auth_checked'] = True
        app.storage.user['auth_error'] = 'No se proporcionó token de autenticación'
        return
    
    # 4. Validar token
    user_data = await TokenValidator.validate_token(token)
    
    if user_data:
        await session_manager.set_session(token, user_data)
        app.storage.user['auth_checked'] = True
        print(f'✓ Usuario autenticado: {user_data.get("email")}')
    else:
        app.storage.user['auth_checked'] = True
        app.storage.user['auth_error'] = 'Token inválido o expirado'
        print('✗ Autenticación fallida')


# ==========================================
# COMPONENTES UI
# ==========================================

def create_header(user_data: Dict):
    """Crear header de la aplicación"""
    with ui.header().classes('items-center justify-between bg-blue-600 text-white'):
        with ui.row().classes('items-center gap-4'):
            ui.icon('app_registration', size='2rem')
            ui.label(Config.APP_NAME).classes('text-xl font-bold')
        
        with ui.row().classes('items-center gap-2'):
            if user_data.get('picture'):
                ui.image(user_data['picture']).classes('w-10 h-10 rounded-full')
            ui.label(user_data.get('name', 'Usuario')).classes('font-semibold')
            #ui.button(icon='logout', on_click=logout).props('flat dense').classes('text-white')


def create_user_card(user_data: Dict):
    """Crear tarjeta de información del usuario"""
    with ui.card().classes('w-full max-w-2xl'):
        ui.label('Información del Usuario').classes('text-2xl font-bold mb-4')
        
        with ui.grid(columns=2).classes('gap-4 w-full'):
            # Nombre
            with ui.column().classes('gap-1'):
                ui.label('Nombre').classes('text-sm text-gray-600')
                ui.label(user_data.get('name', 'N/A')).classes('font-semibold')
            
            # Email
            with ui.column().classes('gap-1'):
                ui.label('Email').classes('text-sm text-gray-600')
                ui.label(user_data.get('email', 'N/A')).classes('font-semibold')
            
            # Perfil
            with ui.column().classes('gap-1'):
                ui.label('Perfil').classes('text-sm text-gray-600')
                with ui.row().classes('items-center gap-2'):
                    ui.icon('badge', size='sm').classes('text-blue-600')
                    ui.label(user_data.get('profile', 'N/A')).classes('font-semibold')
            
            # ID Usuario
            with ui.column().classes('gap-1'):
                ui.label('ID Usuario').classes('text-sm text-gray-600')
                ui.label(f"#{user_data.get('sub', 'N/A')}").classes('font-mono')


def create_permissions_card(user_data: Dict):
    """Crear tarjeta de permisos"""
    permissions = user_data.get('permissions', [])
    
    with ui.card().classes('w-full max-w-2xl'):
        ui.label('Permisos y Aplicaciones').classes('text-2xl font-bold mb-4')
        
        if permissions:
            with ui.column().classes('gap-2 w-full'):
                for perm in permissions:
                    with ui.row().classes('items-center gap-2 p-2 bg-gray-50 rounded'):
                        ui.icon('check_circle', size='sm').classes('text-green-600')
                        ui.label(perm).classes('font-semibold')
        else:
            ui.label('No hay permisos asignados').classes('text-gray-500 italic')


def create_token_card(user_data: Dict):
    """Crear tarjeta de información del token"""
    with ui.card().classes('w-full max-w-2xl'):
        ui.label('Información del Token').classes('text-2xl font-bold mb-4')
        
        with ui.grid(columns=2).classes('gap-4 w-full'):
            # Emisor
            with ui.column().classes('gap-1'):
                ui.label('Emisor (iss)').classes('text-sm text-gray-600')
                ui.label(user_data.get('iss', 'N/A')).classes('font-mono')
            
            # Audiencia
            with ui.column().classes('gap-1'):
                ui.label('Audiencia (aud)').classes('text-sm text-gray-600')
                ui.label(user_data.get('aud', 'N/A')).classes('font-mono')
            
            # Emisión
            with ui.column().classes('gap-1'):
                ui.label('Emitido (iat)').classes('text-sm text-gray-600')
                iat = user_data.get('iat')
                if iat:
                    dt = datetime.fromtimestamp(iat, tz=timezone.utc)
                    ui.label(dt.strftime('%Y-%m-%d %H:%M:%S UTC')).classes('font-mono')
                else:
                    ui.label('N/A').classes('font-mono')
            
            # Expiración
            with ui.column().classes('gap-1'):
                ui.label('Expira (exp)').classes('text-sm text-gray-600')
                exp = user_data.get('exp')
                if exp:
                    dt = datetime.fromtimestamp(exp, tz=timezone.utc)
                    now = datetime.now(timezone.utc)
                    remaining = dt - now
                    
                    ui.label(dt.strftime('%Y-%m-%d %H:%M:%S UTC')).classes('font-mono')
                    
                    if remaining.total_seconds() > 0:
                        mins = int(remaining.total_seconds() / 60)
                        ui.label(f'(Válido por {mins} minutos)').classes('text-xs text-green-600')
                    else:
                        ui.label('(Expirado)').classes('text-xs text-red-600')
                else:
                    ui.label('N/A').classes('font-mono')
            
            # JTI
            with ui.column().classes('gap-1 col-span-2'):
                ui.label('ID Token (jti)').classes('text-sm text-gray-600')
                ui.label(user_data.get('jti', 'N/A')).classes('font-mono text-xs')


def create_session_card():
    """Crear tarjeta de información de sesión"""
    login_time = app.storage.user.get('login_time')
    
    with ui.card().classes('w-full max-w-2xl'):
        ui.label('Información de Sesión').classes('text-2xl font-bold mb-4')
        
        with ui.column().classes('gap-2 w-full'):
            # Hora de login
            if login_time:
                with ui.row().classes('items-center gap-2'):
                    ui.icon('login', size='sm').classes('text-blue-600')
                    ui.label(f'Login: {login_time}').classes('font-mono text-sm')
            
            # Estado de renovación
            with ui.row().classes('items-center gap-2'):
                ui.icon('sync', size='sm').classes('text-green-600')
                ui.label(f'Auto-renovación: Cada {Config.TOKEN_REFRESH_INTERVAL}s').classes('text-sm')


# ==========================================
# PÁGINAS
# ==========================================

# @app.post('/') eliminado - Manejado por SSOMiddleware

@ui.page('/')
async def index_page(request: Request):  # ← Usar Request directamente es más robusto
    
    # Extraer token de query params del request
    token = request.query_params.get('token')
    
    # Ejecutar middleware de autenticación (solo en GET)
    await auth_middleware(token)
    
    # Verificar si hay error de autenticación
    auth_error = app.storage.user.get('auth_error')

    if (auth_error or token is None):
        with ui.column().classes('w-full h-screen items-center justify-center gap-4 p-8'):
            ui.icon('error', size='4rem').classes('text-red-600')
            ui.label('Error de Autenticación').classes('text-3xl font-bold text-red-600')
            ui.label(auth_error).classes('text-gray-600')
            ui.label('Esta aplicación debe ser accedida a través del portal APSA Dashboard').classes('text-sm text-gray-500')
            
            with ui.card().classes('mt-4 p-4 bg-blue-50'):
                ui.label('Información de Integración').classes('font-bold mb-2')
                ui.label(f'• Audiencia esperada: {Config.APP_AUDIENCE}').classes('text-sm')
                ui.label(f'• Portal URL: {Config.PORTAL_URL}').classes('text-sm')
                ui.label(f'• Base path: {Config.BASE_PATH}').classes('text-sm')
        return
    
    # Obtener datos del usuario
    user_data = session_manager.get_current_user()
    
    if not user_data:
        with ui.column().classes('w-full h-screen items-center justify-center gap-4 p-8'):
            ui.spinner(size='xl').classes('text-blue-600')
            ui.label('Validando autenticación...').classes('text-xl')
        return
    
    # UI Principal
    create_header(user_data)
    
    with ui.column().classes('w-full items-center p-8 gap-6'):
        # Título
        with ui.row().classes('items-center gap-2 mb-4'):
            ui.icon('verified_user', size='2rem').classes('text-green-600')
            ui.label('Autenticación Exitosa').classes('text-3xl font-bold text-green-600')
        
        ui.label('Integración SSO con APSA Dashboard funcionando correctamente').classes('text-gray-600 mb-4')
        
        # Tarjetas de información
        create_user_card(user_data)
        create_permissions_card(user_data)
        create_token_card(user_data)
        create_session_card()
        
        # Footer
        with ui.row().classes('gap-4 mt-8'):
            ui.link('Documentación', Config.PORTAL_URL).classes('text-blue-600')
            ui.link('GitHub', 'https://github.com/rcruz-pntlb/nicegui-sso-demo-claude').classes('text-blue-600')

@app.get('/health')
def health_check():
    """Health check endpoint"""
    return {
        'status': 'healthy',
        'app': Config.APP_NAME,
        'audience': Config.APP_AUDIENCE
    }


# ==========================================
# ACCIONES
# ==========================================

def logout():
    """Cerrar sesión del usuario"""
    session_manager.clear_session()
    ui.navigate.to('/')
    ui.notify('Sesión cerrada', type='positive')


# ==========================================
# CONFIGURACIÓN DE LA APLICACIÓN
# ==========================================

# Configurar título y favicon
ui.page_title = Config.APP_NAME

# Configurar storage
app.add_static_files('/static', 'static')

# Dark mode opcional
# ui.dark_mode().enable()


# ==========================================
# MAIN
# ==========================================

if __name__ in {"__main__", "__mp_main__"}:
    # Configurar puerto y host
    port = int(os.getenv('PORT', '8080'))
    host = os.getenv('HOST', '0.0.0.0')
    base_path = os.getenv('BASE_PATH', '/nicegui-demo')

    # Configurar límites de WebSocket via variables de entorno
    # Estas variables son leídas directamente por Uvicorn
    os.environ['WS_MAX_SIZE'] = os.getenv('WS_MAX_SIZE', str(20 * 1024 * 1024))  # 20MB
    os.environ['WS_PING_INTERVAL'] = os.getenv('WS_PING_INTERVAL', '20')
    os.environ['WS_PING_TIMEOUT'] = os.getenv('WS_PING_TIMEOUT', '20')    
    
    print('=' * 60)
    print(f'🚀 {Config.APP_NAME}')
    print('=' * 60)
    print(f'📍 URL Local: http://localhost:{port}')
    print(f'🌐 URL Pública: {Config.PORTAL_URL}{Config.BASE_PATH}')
    print(f'🎯 Audiencia: {Config.APP_AUDIENCE}')
    print(f'🔄 Auto-refresh: {Config.TOKEN_REFRESH_INTERVAL}s')
    print(f'📡 WS Max Size: {int(os.environ["WS_MAX_SIZE"]) / (1024*1024):.1f}MB')    
    print('=' * 60)
    
    ui.run(
        host=host,
        port=port,
        title=Config.APP_NAME,
        reload=False,
        show=False,
        favicon='🔐',
        storage_secret=os.getenv('STORAGE_SECRET', 'WLU-C1yWU7dhhFfXQatn4vzTsHFZj-FkWiggeydlmy4'),
        forwarded_allow_ips='*',
    )

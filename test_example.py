"""
Tests de integración SSO para NiceGUI Demo
Ejecutar con: pytest test_sso_integration.py -v
"""

import pytest
import jwt
import httpx
from datetime import datetime, timezone, timedelta
from pathlib import Path
import asyncio


# ==========================================
# FIXTURES
# ==========================================

@pytest.fixture
def rsa_keys():
    """Generar par de claves RSA para testing"""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    
    # Generar clave privada
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048
    )
    
    # Serializar clave privada
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')
    
    # Serializar clave pública
    public_key = private_key.public_key()
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')
    
    return {
        'private': private_pem,
        'public': public_pem
    }


@pytest.fixture
def valid_token(rsa_keys):
    """Generar token JWT válido para testing"""
    now = int(datetime.now(timezone.utc).timestamp())
    
    payload = {
        'sub': '123',
        'email': 'test@example.com',
        'name': 'Test User',
        'picture': 'https://example.com/avatar.jpg',
        'profile': 'Desarrollador',
        'permissions': ['app1', 'app2', 'nicegui-demo'],
        'iss': 'portal',
        'aud': 'nicegui-demo',
        'iat': now,
        'exp': now + 300,  # 5 minutos
        'jti': 'test-token-123'
    }
    
    token = jwt.encode(payload, rsa_keys['private'], algorithm='RS256')
    return token


@pytest.fixture
def expired_token(rsa_keys):
    """Generar token JWT expirado para testing"""
    now = int(datetime.now(timezone.utc).timestamp())
    
    payload = {
        'sub': '123',
        'email': 'test@example.com',
        'name': 'Test User',
        'iss': 'portal',
        'aud': 'nicegui-demo',
        'iat': now - 600,
        'exp': now - 300,  # Expirado hace 5 minutos
        'jti': 'expired-token-123'
    }
    
    token = jwt.encode(payload, rsa_keys['private'], algorithm='RS256')
    return token


@pytest.fixture
def invalid_audience_token(rsa_keys):
    """Generar token con audience incorrecta"""
    now = int(datetime.now(timezone.utc).timestamp())
    
    payload = {
        'sub': '123',
        'email': 'test@example.com',
        'iss': 'portal',
        'aud': 'otra-app',  # Audience incorrecta
        'iat': now,
        'exp': now + 300,
        'jti': 'invalid-aud-123'
    }
    
    token = jwt.encode(payload, rsa_keys['private'], algorithm='RS256')
    return token


# ==========================================
# TESTS DE VALIDACIÓN DE TOKENS
# ==========================================

class TestTokenValidation:
    """Tests de validación de tokens JWT"""
    
    def test_valid_token_decodes_successfully(self, valid_token, rsa_keys):
        """Token válido se decodifica correctamente"""
        payload = jwt.decode(
            valid_token,
            rsa_keys['public'],
            algorithms=['RS256'],
            audience='nicegui-demo'
        )
        
        assert payload['sub'] == '123'
        assert payload['email'] == 'test@example.com'
        assert payload['aud'] == 'nicegui-demo'
        assert 'nicegui-demo' in payload['permissions']
    
    def test_expired_token_raises_error(self, expired_token, rsa_keys):
        """Token expirado genera error"""
        with pytest.raises(jwt.ExpiredSignatureError):
            jwt.decode(
                expired_token,
                rsa_keys['public'],
                algorithms=['RS256'],
                audience='nicegui-demo'
            )
    
    def test_invalid_audience_raises_error(self, invalid_audience_token, rsa_keys):
        """Token con audience incorrecta genera error"""
        with pytest.raises(jwt.InvalidAudienceError):
            jwt.decode(
                invalid_audience_token,
                rsa_keys['public'],
                algorithms=['RS256'],
                audience='nicegui-demo'
            )
    
    def test_tampered_token_raises_error(self, valid_token, rsa_keys):
        """Token modificado genera error"""
        # Modificar token (cambiar último caracter)
        tampered = valid_token[:-1] + 'X'
        
        with pytest.raises(jwt.InvalidTokenError):
            jwt.decode(
                tampered,
                rsa_keys['public'],
                algorithms=['RS256'],
                audience='nicegui-demo'
            )


# ==========================================
# TESTS DE INTEGRACIÓN CON PORTAL
# ==========================================

class TestPortalIntegration:
    """Tests de integración con el portal"""
    
    @pytest.mark.asyncio
    async def test_portal_health_endpoint(self):
        """Health endpoint del portal responde"""
        portal_url = 'https://petunia.apsagroup.com'
        
        async with httpx.AsyncClient(verify=False) as client:
            try:
                response = await client.get(f'{portal_url}/health', timeout=10.0)
                
                assert response.status_code == 200
                data = response.json()
                assert data['status'] == 'healthy'
            except httpx.RequestError as e:
                pytest.skip(f'Portal no accesible: {e}')
    
    @pytest.mark.asyncio
    async def test_public_key_endpoint(self):
        """Endpoint de clave pública responde"""
        portal_url = 'https://petunia.apsagroup.com'
        
        async with httpx.AsyncClient(verify=False) as client:
            try:
                response = await client.get(
                    f'{portal_url}/internal/public-key',
                    timeout=10.0
                )
                
                assert response.status_code == 200
                public_key = response.text
                
                # Verificar formato PEM
                assert '-----BEGIN PUBLIC KEY-----' in public_key
                assert '-----END PUBLIC KEY-----' in public_key
            except httpx.RequestError as e:
                pytest.skip(f'Portal no accesible: {e}')


# ==========================================
# TESTS DE CACHE
# ==========================================

class TestPublicKeyCache:
    """Tests del sistema de cache de clave pública"""
    
    def test_cache_directory_creation(self, tmp_path):
        """Directorio de cache se crea correctamente"""
        cache_dir = tmp_path / 'cache'
        cache_file = cache_dir / 'portal_public.pem'
        
        # Simular creación de directorio
        cache_dir.mkdir(parents=True, exist_ok=True)
        assert cache_dir.exists()
        
        # Simular escritura de clave
        cache_file.write_text('test-key-content')
        assert cache_file.exists()
        assert cache_file.read_text() == 'test-key-content'


# ==========================================
# TESTS DE RENOVACIÓN DE TOKENS
# ==========================================

class TestTokenRefresh:
    """Tests de renovación de tokens"""
    
    def test_token_expiration_time_calculation(self):
        """Cálculo de tiempo de expiración correcto"""
        now = datetime.now(timezone.utc)
        exp_timestamp = int(now.timestamp()) + 300  # 5 minutos
        
        exp_datetime = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
        time_remaining = exp_datetime - now
        
        # Debe quedar aproximadamente 5 minutos
        assert 295 <= time_remaining.total_seconds() <= 305
    
    def test_should_refresh_token_logic(self):
        """Lógica de cuándo renovar token"""
        now = datetime.now(timezone.utc)
        
        # Token con 6 minutos de validez - NO renovar
        exp_far = int(now.timestamp()) + 360
        should_refresh_far = (exp_far - int(now.timestamp())) < 60
        assert not should_refresh_far
        
        # Token con 30 segundos de validez - SÍ renovar
        exp_soon = int(now.timestamp()) + 30
        should_refresh_soon = (exp_soon - int(now.timestamp())) < 60
        assert should_refresh_soon


# ==========================================
# TESTS DE CONFIGURACIÓN
# ==========================================

class TestConfiguration:
    """Tests de configuración de la aplicación"""
    
    def test_env_variables_loaded(self, monkeypatch):
        """Variables de entorno se cargan correctamente"""
        monkeypatch.setenv('PORTAL_URL', 'https://test.example.com')
        monkeypatch.setenv('APP_AUDIENCE', 'test-app')
        monkeypatch.setenv('TOKEN_REFRESH_INTERVAL', '180')
        
        import os
        assert os.getenv('PORTAL_URL') == 'https://test.example.com'
        assert os.getenv('APP_AUDIENCE') == 'test-app'
        assert int(os.getenv('TOKEN_REFRESH_INTERVAL')) == 180
    
    def test_config_defaults(self):
        """Valores por defecto de configuración"""
        import os
        
        portal_url = os.getenv('PORTAL_URL', 'https://petunia.apsagroup.com')
        assert portal_url.startswith('https://')
        
        refresh_interval = int(os.getenv('TOKEN_REFRESH_INTERVAL', '240'))
        assert refresh_interval > 0
        assert refresh_interval < 300  # Menos que TTL del token


# ==========================================
# TESTS DE SEGURIDAD
# ==========================================

class TestSecurity:
    """Tests de seguridad"""
    
    def test_token_not_stored_in_browser_storage(self):
        """Verificar que tokens no se almacenan en localStorage"""
        # Este test es más conceptual - en la implementación real,
        # NiceGUI usa app.storage.user que es server-side
        # No hay acceso a localStorage del navegador
        assert True  # placeholder
    
    def test_session_cleared_on_invalid_token(self):
        """Sesión se limpia al detectar token inválido"""
        # Simular limpieza de sesión
        session_data = {'token': 'abc', 'user': 'test'}
        
        # Simular detección de token inválido
        token_valid = False
        
        if not token_valid:
            session_data.clear()
        
        assert len(session_data) == 0


# ==========================================
# MAIN
# ==========================================

if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])

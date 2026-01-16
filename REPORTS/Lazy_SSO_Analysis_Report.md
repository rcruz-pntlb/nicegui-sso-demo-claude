# Informe de Análisis: Implementación Lazy SSO

**Fecha:** 16 de Enero de 2026
**Archivo Analizado:** `main.py`
**Referencia:** `IntegrationGuide.md`

## 1. Estado Actual

El análisis del código fuente actual (`main.py`) revela que la implementación del sistema SSO **NO** cumple con los requisitos del modelo "Lazy SSO" especificado en la guía de integración.

### Hallazgos Principales:

1.  **Validación Incompleta:** La función `TokenValidator.validate_token` (líneas 131-171) realiza únicamente la validación local del JWT (firma y expiración).
2.  **Falta de Recuperación de Datos:** El código asume que el token JWT contiene toda la información del usuario (`payload = jwt.decode(...)`). Según la documentación de Lazy SSO, el token "mínimo" ya no contiene permisos ni datos extendidos del perfil.
3.  **Ausencia de Llamada a `/internal/session-data`:** No existe ninguna lógica implementada para realizar la segunda fase de autenticación (la llamada HTTP POST al endpoint de datos de sesión) requerida para obtener el perfil completo y los permisos.

### Impacto:
Si se despliega la aplicación tal como está, la autenticación fallará funcionalmente porque:
- El objeto `user_data` tendrá información incompleta.
- Faltarán permisos y roles necesarios para la lógica de negocio.
- La aplicación podría comportarse de manera impredecible o mostrar datos vacíos al usuario.

---

## 2. Cambios Sugeridos

Para alinear el proyecto con la guía `IntegrationGuide.md`, se requieren las siguientes modificaciones en `main.py`.

### 2.1 Actualizar `Config`

Agregar el endpoint de session-data a la configuración.

```python
class Config:
    # ... otros endpoints ...
    PORTAL_SESSION_DATA_ENDPOINT = f'{PORTAL_URL}/internal/session-data'
```

### 2.2 Modificar `TokenValidator.validate_token`

Reescribir el método para implementar el flujo de dos pasos.

**Código Actual (Simplificado):**
```python
# INCORRECTO para Lazy SSO
payload = jwt.decode(token, public_key, ...)
return payload
```

**Código Sugerido:**
```python
    @staticmethod
    async def validate_token(token: str) -> Optional[Dict]:
        if not token:
            return None
        
        try:
            # ----------------------------------------
            # PASO 1: Validación Local del JWT Mínimo
            # ----------------------------------------
            public_key = await public_key_manager.get_public_key()
            
            payload_min = jwt.decode(
                token,
                public_key,
                algorithms=['RS256'],
                audience=Config.APP_AUDIENCE,
                options={'verify_exp': True}
            )
            
            # -----------------------------------------
            # PASO 2: Recuperación de Datos (Lazy Load)
            # -----------------------------------------
            # Usar httpx para ser consistente con el resto de la app (async)
            async with httpx.AsyncClient(verify=False) as client: # Ajustar verify según entorno
                response = await client.post(
                    Config.PORTAL_SESSION_DATA_ENDPOINT,
                    json={
                        'jti': payload_min['jti'],
                        'email': payload_min['email']  # o 'sub' dependiendo del claim usado para identificar
                    },
                    timeout=5.0
                )
                
                if response.status_code != 200:
                    print(f"✗ Error recuperando sesión remota: {response.text}")
                    return None
                
                full_payload = response.json()
                print(f'✓ Token validado y datos recuperados para: {full_payload.get("email")}')
                return full_payload

        except jwt.ExpiredSignatureError:
            print('⚠ Token expirado')
            return None
        # ... otros excepts ...
```

### 2.3 Revisar `session_manager`

Asegurarse de que `TokenValidator.refresh_token` también maneje adecuadamente la respuesta. Si el endpoint `/internal/refresh` devuelve un nuevo token "mínimo", la validación posterior (`TokenValidator.validate_token(new_token)`) invocada dentro del loop de refresco se encargará correctamente de obtener los datos completos gracias al cambio en el punto 2.2.

---

## 3. Plan de Acción

1.  Modificar `Config` en `main.py` para incluir `PORTAL_SESSION_DATA_ENDPOINT`.
2.  Refactorizar `TokenValidator.validate_token` para incluir la llamada remota.
3.  Verificar que `httpx` esté siendo importado (ya lo está).
4.  Realizar prueba de validación básica.

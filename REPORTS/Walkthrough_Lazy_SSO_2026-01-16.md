# Walkthrough - Implementación Lazy SSO

He actualizado la aplicación para cumplir con la arquitectura "Lazy SSO" definida en la guía de integración.

## Cambios Realizados

### `main.py`

#### 1. Configuración del Endpoint
Se agregó la configuración para el endpoint de recuperación de datos de sesión.

```python
PORTAL_SESSION_DATA_ENDPOINT = f'{PORTAL_URL}/internal/session-data'
```

#### 2. Implementación de Validación en Dos Pasos
Se refactorizó `TokenValidator.validate_token` para seguir el flujo requerido:

1.  **Validación Local (Paso 1):** Se verifica la firma RSA y expiración del JWT "mínimo" recibido.
2.  **Recuperación Remota (Paso 2):** Se utiliza el token validado para hacer un POST a `/internal/session-data` y obtener el perfil completo del usuario.

```python
# Lógica implementada
async with httpx.AsyncClient(verify=False) as client:
    response = await client.post(...)
    full_payload = response.json()
```

## Verificación

### Análisis de Código
*   **Sintaxis Python:** Verificada con `py_compile` sin errores.
*   **Compatibilidad de Renovación:** La lógica de `refresh_token` reutiliza `validate_token`, por lo que la renovación automática de tokens también se beneficia de la carga diferida de datos, asegurando que el perfil del usuario se mantenga actualizado.

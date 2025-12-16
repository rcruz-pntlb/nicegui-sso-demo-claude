# NiceGUI SSO Demo - Integración con APSA Dashboard

![Status](https://img.shields.io/badge/Status-Active-success)
![Python](https://img.shields.io/badge/Python-3.11+-blue)
![NiceGUI](https://img.shields.io/badge/NiceGUI-1.4+-orange)

Esta es una aplicación de demostración que implementa una integración completa de Single Sign-On (SSO) utilizando el portal **APSA Dashboard** como proveedor de identidad. Está diseñada para servir como plantilla base para nuevas aplicaciones internas.

> **Nota:** La guía de integración paso a paso original se ha movido a [`IntegrationGuide.md`](IntegrationGuide.md). Este README se enfoca en la arquitectura técnica y el despliegue del proyecto.

## ✨ Características Principales

- **Autenticación Robusta**: Validación de tokens JWT firmados por el portal central utilizando criptografía asimétrica (RS256).
- **Gestión de Sesiones**: Manejo seguro de sesiones de usuario con almacenamiento local cifrado (NiceGUI Storage).
- **Renovación Automática**: Sistema inteligente que renueva el token JWT automáticamente antes de que expire, sin interrumpir al usuario.
- **Caché Optimizado**: Descarga y cachea la clave pública del portal para minimizar latencia y tráfico de red.
- **Middleware de Seguridad**: Intercepta todas las peticiones para garantizar que solo usuarios autenticados accedan a las rutas protegidas.
- **UI Reactiva**: Interfaz moderna construida con NiceGUI (basado en Quasar/Vue) y TailwindCSS.

## 🏗️ Arquitectura

El sistema funciona mediante una arquitectura de Microservicios detrás de un Proxy Inverso (Traefik/Apache/Nginx).

```mermaid
graph TD
    User((Usuario))
    Proxy[Proxy Reverso\n(Traefik/Apache)]
    Portal[APSA Dashboard\n(Proveedor Identidad)]
    App[NiceGUI App\n(Este Proyecto)]
    
    User -->|HTTPS| Proxy
    Proxy -->|/nicegui-demo| App
    Proxy -->|/portal| Portal
    
    App -.->|Valida Token| Portal
    App -.->|Obtiene PubKey| Portal
```

1. **Usuario accede a la App**: La petición llega al Proxy.
2. **Validación**:
   - Si tiene token válido: Accede a la App.
   - Si no tiene token: La App redirige al Portal.
3. **Login en Portal**: Usuario se autentica en el Portal.
4. **Redirección**: Portal redirige de vuelta a la App con un token JWT en la URL.
5. **Establecimiento de Sesión**: La App valida el token y crea una sesión segura.

## 🚀 Instalación y Despliegue

### Requisitos Previos

- Python 3.11+
- Docker & Docker Compose (para despliegue en contenedor)
- Acceso a la red del Portal (para validar tokens)

### Opción A: Desarrollo Local (Recomendado)

Utilizamos `pyproject.toml` para gestionar dependencias.

1. **Instalar dependencias:**
   ```bash
   pip install .
   # O si usas pixi/poetry, las dependencias están en pyproject.toml
   ```

2. **Configurar variables de entorno:**
   ```bash
   cp .env.example .env
   # Editar .env con tus valores (PORTAL_URL, APP_AUDIENCE, etc.)
   ```

3. **Ejecutar tareas predefinidas:**
   ```bash
   # Modo desarrollo (auto-reload)
   task dev
   
   # Modo producción
   task start
   
   # Ver tareas disponibles
   task --list
   ```

### Opción B: Docker Compose

Ideal para despliegues estables o entornos de prueba.

1. **Construir y levantar:**
   ```bash
   docker compose up -d --build
   ```

3. **Verificar logs:**
   ```bash
   docker compose logs -f
   ```

## ⚙️ Configuración

Las principales configuraciones se realizan vía variables de entorno (ver `docker-compose.yml` o `.env`):

| Variable | Descripción | Valor por Defecto |
|----------|-------------|-------------------|
| `PORTAL_URL` | URL base del portal de identidad | `https://petunia.apsagroup.com` |
| `APP_AUDIENCE` | Nombre registrado de la app (field `name` en DB) | `nicegui-demo` |
| `BASE_PATH` | Sub-ruta donde se sirve la app | `/nicegui-demo` |
| `APP_NAME` | Nombre visible en la UI | `NiceGUI Demo` |

## 🔧 Troubleshooting

### 1. Error de Validación de Token (Signature Verification Failed)
**Causa:** La clave pública usada para validar no coincide con la clave privada que firmó el token.
**Solución:**
- Verifica que `PORTAL_URL` apunta al portal correcto.
- Borra el archivo de caché local: `rm cache/portal_public.pem`.
- Reinicia la aplicación para forzar la descarga de la nueva clave.

### 2. Bucle de Redirección Infinito
**Causa:** La aplicación no reconoce el token o no puede establecer la cookie de sesión.
**Solución:**
- Asegúrate de que `APP_AUDIENCE` coincide **exactamente** con el nombre de la app en el Portal.
- Verifica que el reloj del servidor esté sincronizado (NTP).

### 3. Error "Connection Lost" en NiceGUI
**Causa:** WebSocket desconectado, comúnmente por configuraciones de Proxy.
**Solución:**
- Si usas Nginx/Apache/Traefik, asegura los headers de `Upgrade` y `Connection`.
- Ver `IntegrationGuide.md` seccion Nginx/Proxy.

## 📚 Estructura del Proyecto

- `main.py`: Punto de entrada y lógica principal de la UI.
- `docker-compose.yml`: Orquestación de contenedores.
- `pyproject.toml`: Definición del proyecto y dependencias.
- `IntegrationGuide.md`: Guía detallada paso a paso para integrar desde cero.

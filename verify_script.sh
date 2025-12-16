#!/bin/bash

# ==========================================
# Script de Verificación de Integración SSO
# ==========================================

set -e

echo "=================================================="
echo "  Verificación de Integración SSO - NiceGUI"
echo "=================================================="
echo ""

# Colores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Función para imprimir con color
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_info() {
    echo -e "ℹ $1"
}

# ==========================================
# 1. VERIFICAR ARCHIVOS DE CONFIGURACIÓN
# ==========================================

echo "1. Verificando archivos de configuración..."
echo ""

if [ -f ".env" ]; then
    print_success ".env existe"
else
    print_error ".env no encontrado"
    print_info "Crear desde plantilla: cp .env.example .env"
    exit 1
fi

if [ -f "main.py" ]; then
    print_success "main.py existe"
else
    print_error "main.py no encontrado"
    exit 1
fi

if [ -f "Dockerfile" ]; then
    print_success "Dockerfile existe"
else
    print_error "Dockerfile no encontrado"
    exit 1
fi

if [ -f "docker-compose.yml" ]; then
    print_success "docker-compose.yml existe"
else
    print_error "docker-compose.yml no encontrado"
    exit 1
fi

echo ""

# ==========================================
# 2. VERIFICAR VARIABLES DE ENTORNO
# ==========================================

echo "2. Verificando variables de entorno..."
echo ""

# Cargar variables
source .env 2>/dev/null || true

# Verificar PORTAL_URL
if [ -z "$PORTAL_URL" ]; then
    print_error "PORTAL_URL no está configurada"
    exit 1
else
    print_success "PORTAL_URL: $PORTAL_URL"
    
    # Verificar que sea HTTPS en producción
    if [[ ! "$PORTAL_URL" =~ ^https:// ]]; then
        print_warning "PORTAL_URL no usa HTTPS (ok en desarrollo)"
    fi
fi

# Verificar APP_AUDIENCE
if [ -z "$APP_AUDIENCE" ]; then
    print_error "APP_AUDIENCE no está configurada"
    print_info "Esta variable debe coincidir con el nombre en APSA Dashboard"
    exit 1
else
    print_success "APP_AUDIENCE: $APP_AUDIENCE"
fi

# Verificar BASE_PATH
if [ -z "$BASE_PATH" ]; then
    print_warning "BASE_PATH no configurada (usando /)"
else
    print_success "BASE_PATH: $BASE_PATH"
fi

echo ""

# ==========================================
# 3. VERIFICAR DOCKER
# ==========================================

echo "3. Verificando Docker..."
echo ""

if ! command -v docker &> /dev/null; then
    print_error "Docker no está instalado"
    exit 1
else
    print_success "Docker instalado"
fi

if ! command -v docker compose &> /dev/null; then
    print_error "Docker Compose no está instalado"
    exit 1
else
    print_success "Docker Compose instalado"
fi

# Verificar daemon de Docker
if ! docker info &> /dev/null; then
    print_error "Docker daemon no está corriendo"
    print_info "Iniciar con: sudo systemctl start docker"
    exit 1
else
    print_success "Docker daemon corriendo"
fi

echo ""

# ==========================================
# 4. VERIFICAR CONECTIVIDAD CON PORTAL
# ==========================================

echo "4. Verificando conectividad con portal..."
echo ""

# Health check del portal
HEALTH_URL="${PORTAL_URL}/health"
if curl -s -f "$HEALTH_URL" &> /dev/null; then
    print_success "Portal accesible: $HEALTH_URL"
else
    print_error "Portal no accesible: $HEALTH_URL"
    print_info "Verificar que el portal APSA Dashboard esté corriendo"
    exit 1
fi

# Verificar endpoint de clave pública
PUBLIC_KEY_URL="${PORTAL_URL}/internal/public-key"
if curl -s -f "$PUBLIC_KEY_URL" &> /dev/null; then
    print_success "Endpoint de clave pública accesible"
    
    # Mostrar primeras líneas de la clave
    print_info "Primeras líneas de la clave pública:"
    curl -s "$PUBLIC_KEY_URL" | head -n 2
else
    print_error "Endpoint de clave pública no accesible"
    exit 1
fi

echo ""

# ==========================================
# 5. VERIFICAR APLICACIÓN EN PORTAL
# ==========================================

echo "5. Verificando registro en portal..."
echo ""

print_info "Verificación manual requerida:"
echo "   1. Acceder a: ${PORTAL_URL}/admin/webapps"
echo "   2. Buscar aplicación con nombre: ${APP_AUDIENCE}"
echo "   3. Verificar que:"
echo "      - Nombre = ${APP_AUDIENCE} (exacto)"
echo "      - Tipo (Origin) = internal"
echo "      - Estado = Activa"
echo "      - URL = ${PORTAL_URL}${BASE_PATH}/"

read -p "¿La aplicación está registrada correctamente? (s/n): " confirm
if [[ "$confirm" != "s" ]]; then
    print_error "Aplicación no registrada correctamente"
    print_info "Registrar en el portal antes de continuar"
    exit 1
else
    print_success "Aplicación registrada correctamente"
fi

echo ""

# ==========================================
# 6. VERIFICAR CONTENEDOR
# ==========================================

echo "6. Verificando contenedor Docker..."
echo ""

# Verificar si el contenedor está corriendo
if docker compose ps | grep -q "Up"; then
    print_success "Contenedor corriendo"
    
    # Verificar health
    if docker compose ps | grep -q "healthy"; then
        print_success "Health check OK"
    else
        print_warning "Health check no pasa (puede ser normal si recién inició)"
    fi
else
    print_warning "Contenedor no está corriendo"
    print_info "Iniciar con: docker compose up -d"
fi

# Verificar puerto
PORT=${PORT:-8080}
if lsof -i:$PORT &> /dev/null || netstat -tuln | grep -q ":$PORT "; then
    print_success "Puerto $PORT está en uso"
else
    print_warning "Puerto $PORT no está en uso"
fi

echo ""

# ==========================================
# 7. VERIFICAR HEALTH ENDPOINT LOCAL
# ==========================================

echo "7. Verificando health endpoint local..."
echo ""

HEALTH_LOCAL="http://localhost:${PORT}/health"
if curl -s -f "$HEALTH_LOCAL" &> /dev/null; then
    print_success "Health endpoint local accesible"
    
    # Mostrar respuesta
    print_info "Respuesta:"
    curl -s "$HEALTH_LOCAL" | python3 -m json.tool 2>/dev/null || curl -s "$HEALTH_LOCAL"
else
    print_error "Health endpoint local no accesible"
    print_info "Verificar logs: docker compose logs -f"
fi

echo ""

# ==========================================
# 8. VERIFICAR NGINX (si aplica)
# ==========================================

echo "8. Verificando configuración de Nginx..."
echo ""

if command -v nginx &> /dev/null; then
    if nginx -t &> /dev/null; then
        print_success "Configuración de Nginx OK"
    else
        print_error "Configuración de Nginx tiene errores"
        print_info "Verificar con: sudo nginx -t"
    fi
    
    # Verificar location block
    CONFIG_FILE="/etc/nginx/sites-enabled/petunia.apsagroup.com"
    if [ -f "$CONFIG_FILE" ]; then
        if grep -q "$BASE_PATH" "$CONFIG_FILE"; then
            print_success "Location block para $BASE_PATH encontrado"
        else
            print_warning "Location block para $BASE_PATH no encontrado"
            print_info "Agregar configuración para $BASE_PATH en Nginx"
        fi
    fi
else
    print_warning "Nginx no instalado (ok si solo testing local)"
fi

echo ""

# ==========================================
# 9. RESUMEN
# ==========================================

echo "=================================================="
echo "  Resumen de Verificación"
echo "=================================================="
echo ""

print_success "Verificación completada"
echo ""
print_info "Próximos pasos:"
echo "  1. Iniciar contenedor: docker compose up -d"
echo "  2. Ver logs: docker compose logs -f"
echo "  3. Acceder via portal: ${PORTAL_URL}"
echo "  4. Click en tu aplicación en el dashboard"
echo "  5. Verificar que la autenticación funcione"
echo ""
print_info "URLs de acceso:"
echo "  Local:   http://localhost:${PORT}/"
echo "  Público: ${PORTAL_URL}${BASE_PATH}/"
echo ""

exit 0

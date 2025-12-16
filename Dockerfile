FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar archivos de dependencias
COPY pyproject.toml pixi.lock* ./

# Instalar dependencias Python
RUN pip install --no-cache-dir \
    nicegui>=1.4.0 \
    pyjwt>=2.8.0 \
    httpx>=0.25.0 \
    python-dotenv>=1.0.0

# Copiar código de la aplicación
COPY main.py .
COPY .env* ./
COPY static ./static

# Crear directorio para cache
RUN mkdir -p cache && chmod 777 cache

# Crear usuario no-root
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Variables de entorno por defecto
ENV PORT=8080
ENV HOST=0.0.0.0
ENV PYTHONUNBUFFERED=1

# Exponer puerto
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=20s --retries=3 \
    CMD curl -f http://localhost:8080/health || exit 1

# Comando de inicio
CMD ["python", "main.py"]

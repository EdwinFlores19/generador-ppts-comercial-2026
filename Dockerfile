# Imagen base ligera de Python
FROM python:3.11-slim

# Directorio de trabajo en el contenedor
WORKDIR /app

# Instalar dependencias del sistema necesarias
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copiar archivo de requerimientos
COPY requirements.txt .

# Instalar dependencias de Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar el código de la aplicación y la plantilla base
COPY . .

# Inicializar la base de datos SQLite antes de arrancar
RUN python database_setup.py

# Exponer el puerto del servidor Flask
EXPOSE 5000

# Ejecutar el servidor web
CMD ["python", "app.py"]

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY run.py .

EXPOSE 8000
ENV HOST=0.0.0.0 PORT=8000

# Lee PORT (8000 por defecto). Forma shell para expandir la variable; `exec`
# deja a uvicorn como PID 1 para que reciba las senales de parada del contenedor.
CMD ["sh", "-c", "exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

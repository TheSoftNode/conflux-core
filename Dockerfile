FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py game_logic.py ./
COPY static ./static
RUN useradd --create-home --uid 10001 conflux
USER conflux
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=4s --start-period=10s CMD python -c "import os,urllib.request;urllib.request.urlopen(f'http://127.0.0.1:{os.environ.get(\"PORT\",\"8000\")}/health',timeout=3)"
# One worker only: rooms live in this process's memory.
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1 --ws-max-size 65536 --proxy-headers --forwarded-allow-ips '*'"]

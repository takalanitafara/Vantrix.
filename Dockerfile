FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY server ./server
COPY templates ./templates
COPY web ./web

# Persistent volume mount point: SQLite database lives here.
ENV QUANTVENUE_DATA_DIR=/app/data
ENV PORT=3000

EXPOSE 3000

# Honours $PORT so the same image upgrades on any platform without rebuilds.
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port ${PORT:-3000}"]

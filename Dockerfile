FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app
COPY pyproject.toml ./
COPY backend backend
COPY agents agents
COPY rag rag
COPY evals evals
COPY scripts scripts
RUN pip install --no-cache-dir -e .
COPY database database
COPY seed seed
COPY knowledge knowledge
COPY frontend frontend
EXPOSE 8000
# One image, two commands.
#   web:    the default below (migrates and seeds an empty database, then serves the API and the UI)
#   worker: python -m backend.worker
CMD ["sh", "-c", "python scripts/bootstrap.py && uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

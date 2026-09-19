FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
COPY backend backend
COPY agents agents
COPY rag rag
COPY evals evals
RUN pip install --no-cache-dir .
COPY database database
COPY seed seed
COPY knowledge knowledge
COPY frontend frontend
COPY scripts scripts
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
# web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
# worker: python -m backend.worker
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT:-8000}"]

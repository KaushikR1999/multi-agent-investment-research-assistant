FROM python:3.11-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY frontend ./frontend

RUN pip install --no-cache-dir .

EXPOSE 8501

CMD ["streamlit", "run", "frontend/app.py", "--server.address", "0.0.0.0"]

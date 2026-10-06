FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# libgl/glib are needed by OpenCV even in headless mode on slim images
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ARG INSTALL_AI=false
COPY requirements.txt requirements-ai.txt ./
RUN pip install -r requirements.txt \
    && if [ "$INSTALL_AI" = "true" ]; then pip install -r requirements-ai.txt; fi

COPY . .
RUN useradd --create-home shopmotion && mkdir -p instance && chown -R shopmotion /app
USER shopmotion

EXPOSE 8000
# One worker with threads: camera pipelines live in the worker process.
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "8", "--timeout", "120", "wsgi:app"]

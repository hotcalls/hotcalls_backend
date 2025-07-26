# Multi-stage build for production Django application
FROM python:3.12-slim as base

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create application directory
WORKDIR /app

# Install Python dependencies
COPY requirements/requirements.txt ./requirements/
RUN pip install --no-cache-dir -r requirements/requirements.txt

# Copy application code
COPY . .

# Development stage
FROM base as development

# Create static files directory
RUN mkdir -p /app/staticfiles

# Development doesn't need non-root user for simplicity
# Expose port
EXPOSE 8000

# Run Django development server
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# Production stage
FROM base as production

# Create non-root user
RUN groupadd -r django && useradd -r -g django django

# Set permissions
RUN mkdir -p /app/staticfiles && \
    chown -R django:django /app

# Switch to non-root user
USER django

# Collect static files
RUN ALLOWED_HOSTS=localhost python manage.py collectstatic --noinput --settings=hotcalls.settings.production

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health/ || exit 1

# Expose port
EXPOSE 8000

# Run application with Gunicorn
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "--workers", "3", "--worker-class", "gthread", "--threads", "2", "--worker-connections", "1000", "--max-requests", "1000", "--max-requests-jitter", "100", "--preload", "--access-logfile", "-", "--error-logfile", "-", "hotcalls.wsgi:application"] 
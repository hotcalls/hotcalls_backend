FROM python:3.12-slim

RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

WORKDIR /app

COPY . .

RUN uv venv .venv
RUN . .venv/bin/activate && uv pip install -e .

RUN groupadd -r mcp && useradd -r -g mcp mcp
RUN chown -R mcp:mcp /app && \
    mkdir -p /tmp /app/tmp && \
    chown -R mcp:mcp /tmp /app/tmp
USER mcp

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

CMD ["/bin/bash", "-c", "source .venv/bin/activate && python server.py"]



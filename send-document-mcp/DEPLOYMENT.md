# MCP Server Deployment Guide (Send Document MCP)

## Quick HTTP Deployment

```bash
python deploy.py
```

## Configure via .env.deployment

```env
MCP_HOST=0.0.0.0
MCP_PORT=8000
MCP_TRANSPORT=streamable-http
API_BASE_URL=http://localhost:8000
```

Then:

```bash
python deploy.py
```

## Development (stdio)

```bash
python deploy.py --dev
```

## Docker

```bash
docker build -t send-document-mcp .
docker run -p 8000:8000 send-document-mcp
```




# Knowledge MCP Deployment

## Quick HTTP Deployment

```bash
python deploy.py
```

## .env.deployment

```env
MCP_HOST=0.0.0.0
MCP_PORT=8000
MCP_TRANSPORT=streamable-http
API_BASE_URL=http://localhost:8000
```

## Docker

```bash
docker build -t knowledge-mcp .
docker run -p 8000:8000 knowledge-mcp
```



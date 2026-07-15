web: uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
consumer: python -m app.consumer
monitor: python -m app.run_monitor
mcp: python mcp_server.py

FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

EXPOSE 8000

ENV MCP_TRANSPORT=streamable-http
ENV FASTMCP_HOST=0.0.0.0
ENV FASTMCP_PORT=8000

CMD ["python", "src/server.py"]

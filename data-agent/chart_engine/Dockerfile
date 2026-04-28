FROM python:3.12.0-slim-bookworm

# 接收代理参数（云主机构建需要）
ARG HTTP_PROXY
ARG HTTPS_PROXY
ENV http_proxy=${HTTP_PROXY} \
    https_proxy=${HTTPS_PROXY}

WORKDIR /app

# 安装 Python 依赖
RUN pip install --no-cache-dir \
    litellm \
    fastapi \
    "uvicorn[standard]" \
    pydantic \
    python-dateutil \
    pyyaml \
    duckdb

# 清除代理（运行时不需要）
ENV http_proxy= \
    https_proxy=

# 复制应用代码
COPY . /app/chart_engine/

ENV PYTHONPATH="/app" \
    PYTHONUNBUFFERED=1

EXPOSE 8100

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8100/health')" || exit 1

CMD ["python", "-m", "uvicorn", "chart_engine.server.app:app", "--host", "0.0.0.0", "--port", "8100"]

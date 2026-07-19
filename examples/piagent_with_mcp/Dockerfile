FROM agentkit-prod-public-cn-beijing.cr.volces.com/base/py-simple:python3.12-bookworm-slim-latest

ARG PIAGENT_VERSION=0.80.6
ARG PIAGENT_SHA256=f7c383b3dbf336b97174249ef40baed86e295416af77a81ff5288ac17cb71839

ENV UV_SYSTEM_PYTHON=1
ENV PYTHONUNBUFFERED=1
ENV PIAGENT_INSTALL_DIR=/opt/piagent
ENV PIAGENT_AGENT_DIR=/tmp/veadk-piagent-home
ENV OTEL_SDK_DISABLED=true

WORKDIR /app

COPY vendor/veadk_python-*.whl /tmp/

RUN uv pip install --system /tmp/veadk_python-*.whl

RUN PIAGENT_BINARY_VERSION="${PIAGENT_VERSION}" \
    PIAGENT_BINARY_SHA256="${PIAGENT_SHA256}" \
    python - <<'PY'
from veadk.runtime.piagent.installer import resolve_or_install_piagent_binary

binary = resolve_or_install_piagent_binary()
print(f"Installed Pi binary to {binary}")
PY

ENV PIAGENT_BINARY=/opt/piagent/pi/pi

COPY requirements.txt ./
RUN uv pip install --system -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "-m", "app"]

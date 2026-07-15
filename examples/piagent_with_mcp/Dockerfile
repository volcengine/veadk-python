FROM agentkit-prod-public-cn-beijing.cr.volces.com/base/py-simple:python3.12-bookworm-slim-latest

ARG PIAGENT_VERSION=0.80.6
ARG PIAGENT_SHA256=f7c383b3dbf336b97174249ef40baed86e295416af77a81ff5288ac17cb71839

ENV UV_SYSTEM_PYTHON=1
ENV PYTHONUNBUFFERED=1
ENV PIAGENT_BINARY=/opt/piagent/pi/pi
ENV PIAGENT_INSTALL_DIR=/opt/piagent
ENV PIAGENT_AGENT_DIR=/tmp/veadk-piagent-home
ENV OTEL_SDK_DISABLED=true

WORKDIR /app

COPY vendor/pi-linux-x64.tar.gz /tmp/pi-linux-x64.tar.gz
COPY vendor/veadk_python-*.whl /tmp/

RUN PIAGENT_VERSION="${PIAGENT_VERSION}" PIAGENT_SHA256="${PIAGENT_SHA256}" python - <<'PY'
import hashlib
import os
import tarfile
from pathlib import Path

version = os.environ["PIAGENT_VERSION"]
sha256 = os.environ["PIAGENT_SHA256"]
archive = Path("/tmp/pi-linux-x64.tar.gz")
target = Path("/opt/piagent")

print(f"Installing vendored Pi binary archive for version {version}")
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
if digest != sha256:
    raise SystemExit(f"Pi binary sha256 mismatch: expected {sha256}, got {digest}")

target.mkdir(parents=True, exist_ok=True)
with tarfile.open(archive) as tar:
    for member in tar.getmembers():
        destination = (target / member.name).resolve()
        if not str(destination).startswith(str(target.resolve()) + "/"):
            raise SystemExit(f"Refusing unsafe tar member: {member.name}")
    tar.extractall(target)

binary = target / "pi" / "pi"
if not binary.exists():
    raise SystemExit(f"Pi binary not found after extraction: {binary}")
binary.chmod(0o755)
print(f"Installed Pi binary to {binary}")
PY

RUN uv pip install --system /tmp/veadk_python-*.whl

COPY requirements.txt ./
RUN uv pip install --system -r requirements.txt

COPY . .

EXPOSE 8000

CMD ["python", "-m", "app"]

FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PORT=8067

WORKDIR /app

# Install this checkout so the image contains the same VeADK implementation as
# the example. The sandbox extra supplies the Anthropic managed-session client.
COPY --from=ghcr.io/astral-sh/uv:0.11.28 /uv /uvx /bin/
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY veadk ./veadk
COPY frontend ./frontend
RUN uv sync --frozen --no-dev --extra sandbox

COPY examples/16_self_host_sandbox ./examples/16_self_host_sandbox
RUN chmod +x ./examples/16_self_host_sandbox/run.sh \
    && useradd --create-home --uid 10001 veadk \
    && chown -R veadk:veadk /app

USER veadk
EXPOSE 8067

CMD ["bash", "examples/16_self_host_sandbox/run.sh", "--web", "--host", "0.0.0.0", "--port", "8067"]


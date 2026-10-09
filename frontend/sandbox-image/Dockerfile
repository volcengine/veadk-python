ARG BASE_IMAGE
FROM ${BASE_IMAGE}

ARG APT_MIRROR_URL=https://mirrors.aliyun.com/ubuntu
ARG PIP_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/
ARG NPM_REGISTRY_URL=https://registry.npmmirror.com

# Keep the base runtime's root entrypoint; it starts the editor and terminals as gem
USER root
ENV WORKSPACE=/home/gem/Projects \
    DISABLE_CODE_SERVER=false \
    DISABLE_JUPYTER=false \
    PIP_INDEX_URL=${PIP_INDEX_URL} \
    UV_INDEX_URL=${PIP_INDEX_URL} \
    UV_HTTP_TIMEOUT=60 \
    UV_HTTP_RETRIES=3 \
    npm_config_registry=${NPM_REGISTRY_URL}

COPY runtime/ /opt/studio-sandbox/runtime/
COPY assets/ /opt/studio-sandbox/assets/
COPY assets.lock.json settings.json requirements.lock /opt/studio-sandbox/

# All browser extensions and fonts are local assets; Python uses an overridable domestic index
RUN /opt/agentkit-code-env/venv/bin/python /opt/studio-sandbox/runtime/configure-apt.py "${APT_MIRROR_URL}" \
    && /opt/agentkit-code-env/venv/bin/python /opt/studio-sandbox/runtime/install-image.py

# Preserve the base image ENTRYPOINT and CMD

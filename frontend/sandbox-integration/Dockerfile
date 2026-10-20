ARG STUDIO_SANDBOX_IMAGE
FROM ${STUDIO_SANDBOX_IMAGE}
USER root
# Preserve executable entrypoints after the final runtime source copy
RUN chmod 755 /opt/studio-sandbox/runtime/code-server-wrapper \
    /opt/studio-sandbox/runtime/studio-project-create \
    /opt/studio-sandbox/runtime/studio-vscode-upgrade

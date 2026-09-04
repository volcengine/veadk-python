# VeADK Studio on VeStack

This image runs the Studio FastAPI BFF and React UI directly on port 8000. It is
intended for VeStack environments where the public-cloud VeFaaS Application/BFF
workflow is unavailable and a prebuilt image must be attached to a Function.

Build for the VeFaaS data plane:

```bash
docker build --platform linux/amd64 \
  -f docker/Dockerfile.vestack \
  --build-arg PYTHON_IMAGE=<reachable-python-3.12-image> \
  -t <vestack-registry>/<namespace>/veadk-studio:<tag> .
```

If the selected VeStack base image already contains the VEADK runtime
dependencies, also pass `--build-arg VEADK_INSTALL_DEPENDENCIES=0`. This avoids
resolving the entire dependency graph against an incomplete private PyPI mirror;
the current repository and wheels staged under `docker/vendor/` are still
installed.

Stage the wheels absent from the VeStack mirror before using that mode:

```bash
python -m pip download --no-deps \
  'openviking-sdk>=0.1.3' 'fastmcp==3.4.7' 'fastmcp-slim==3.4.7' \
  -d docker/vendor
```

The runtime defaults to the VeStack TOP endpoint and `gateway` authentication,
which expects the AgentKit/APIG gateway to authenticate requests. For a direct
browser route, set `VEADK_STUDIO_AUTH_MODE=frontend` and configure the Identity
user pool/client.
Long-lived AK/SK values must not be placed in the image or Function environment;
bind an IAM role and let VeFaaS mount rotating STS credentials instead.

# Copyright (c) 2025 Beijing Volcano Engine Technology Co., Ltd. and/or its affiliates.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

FROM python:3.12-slim

WORKDIR /app

# `[extensions]` pulls llama-index / redis / opensearch, required when the
# KNOWLEDGEBASE_TYPE or LONG_TERM_MEMORY_TYPE env vars enable those components.
# (Viking / MySQL / PostgreSQL backends are already in the base dependencies.)
RUN apt-get update && apt-get install -y --no-install-recommends git && \
    pip3 install --no-cache-dir "veadk-python[extensions] @ git+https://github.com/volcengine/veadk-python.git" && \
    apt-get purge -y git && apt-get autoremove -y && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# The harness advertises `runtime: codex` in harness.yaml and also honours a
# per-request runtime override, so the image must be able to serve it. Installed
# unconditionally: a missing extra would otherwise surface as an ImportError on
# the first request of an already-deployed runtime.
ARG INSTALL_CODEX=1
RUN if [ "$INSTALL_CODEX" = "1" ]; then \
        pip3 install --no-cache-dir "openai-codex==0.1.0b3" "openai-codex-cli-bin==0.137.0a4"; \
    fi

COPY agent.py app.py ./

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]

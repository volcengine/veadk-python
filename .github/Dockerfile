FROM python:3.12-slim

# # Install git and install veadk-python via git
RUN apt-get update && apt-get install -y git && \
    pip3 install --no-cache-dir git+https://github.com/volcengine/veadk-python.git && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

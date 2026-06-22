FROM mcr.microsoft.com/devcontainers/python:3.12-trixie

COPY pyproject.toml /tmp/kond-test-py-svc/pyproject.toml
COPY app /tmp/kond-test-py-svc/app

WORKDIR /tmp/kond-test-py-svc
RUN pip install --no-cache-dir ".[dev]"

WORKDIR /pvc/workspace

# Image used ONLY to run untrusted repository tests. Contains Python + pytest, nothing else.
# Build:  docker build -t codepilotx-sandbox sandbox/
# To support repos with third-party dependencies, extend this file with the packages you trust
# (e.g. RUN pip install --no-cache-dir numpy requests) and rebuild. The container has no network
# at run time, so dependencies must be baked in here.
FROM python:3.12-slim
RUN pip install --no-cache-dir pytest
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /work

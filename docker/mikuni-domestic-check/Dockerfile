# BOAT LAB / official Mikuni replay access diagnostic only.
# The container inherits the host's normal, permitted network; no VPN/proxy.
# This image is NOT an automated video downloader.
FROM mcr.microsoft.com/playwright/python:v1.55.0-noble
RUN python -m pip install --no-cache-dir playwright==1.55.0
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /opt/boatlabs
COPY scripts/mikuni_replay_transport_probe.py scripts/mikuni_replay_transport_probe.py
COPY scripts/mikuni_domestic_access_check.py scripts/mikuni_domestic_access_check.py
# The official Playwright image includes a non-root "pwuser".
USER pwuser
ENTRYPOINT ["python", "-m", "scripts.mikuni_domestic_access_check"]

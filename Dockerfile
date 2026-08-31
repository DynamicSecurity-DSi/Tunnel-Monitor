FROM python:3.12-slim

LABEL maintainer="DSi <support@dsits.tech>"
LABEL org.opencontainers.image.title="tunnel-monitor"
LABEL org.opencontainers.image.description="Tunnel monitor — keepalive, alerting, and health reporting via Slack"
LABEL org.opencontainers.image.source="https://github.com/DynamicSecurity-DSi/Tunnel-Monitor"
LABEL org.opencontainers.image.licenses="MIT"

# iputils-ping needed for the ping command
RUN apt-get update && \
    apt-get install -y --no-install-recommends iputils-ping && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY tunnel-monitor-slack.py .

# Log directory (mount a volume here in production)
RUN mkdir -p /var/log

ENV CONFIG_PATH=/app/config.json
ENV LOG_FILE=/var/log/tunnel-monitor.log

# ENTRYPOINT (not CMD) so `docker run <image> <subcommand>` passes args to the
# script — e.g. `check-config`, `print-example-config`, `add-connector`.
# No args => runs the monitor loop.
ENTRYPOINT ["python", "-u", "tunnel-monitor-slack.py"]
CMD []

FROM python:3.12-slim

LABEL maintainer="DSi <support@dsits.tech>"
LABEL description="Tunnel monitor — keepalive, alerting, and health reporting via Slack"

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

CMD ["python", "-u", "tunnel-monitor-slack.py"]

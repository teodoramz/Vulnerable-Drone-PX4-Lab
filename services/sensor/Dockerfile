# Network sensor: Suricata on the OT segments plus a FastAPI sidecar (:9200)
# that tails eve.json and republishes alerts.
# Needs network_mode: host and NET_ADMIN/NET_RAW to capture on the docker bridges.
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        suricata \
        python3 \
        python3-pip \
        python3-venv \
        iproute2 \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Drop the packaged config and rules so only drone-ot.rules is loaded.
RUN rm -f /etc/suricata/suricata.yaml /etc/suricata/rules/*.rules || true

WORKDIR /app

# PEP 668: system Python is externally managed on Ubuntu 24.04.
ENV VIRTUAL_ENV=/opt/venv
RUN python3 -m venv "$VIRTUAL_ENV"
ENV PATH="$VIRTUAL_ENV/bin:$PATH"

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY suricata.yaml /etc/suricata/suricata.yaml
COPY rules/ /etc/suricata/rules/
COPY app/ /app/app/
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh && mkdir -p /var/log/suricata

EXPOSE 9200

HEALTHCHECK --interval=15s --timeout=3s --start-period=30s --retries=3 \
    CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:9200/health', timeout=2).status==200 else 1)"

ENTRYPOINT ["/app/entrypoint.sh"]

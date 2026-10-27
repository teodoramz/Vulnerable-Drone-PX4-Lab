# PX4 SITL drone image (Linux/WSL2 only). Build context is the repo root.
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

# Core build tools (no GUI packages - headless).
RUN apt-get update && apt-get install -y \
    ca-certificates gnupg lsb-release sudo wget curl git \
    build-essential cmake python3-pip python-is-python3 ninja-build \
    && rm -rf /var/lib/apt/lists/*

# PX4 build deps plus the lifecycle agent's web deps.
RUN pip3 install --no-cache-dir --upgrade pip && pip3 install --no-cache-dir \
    empy==3.3.4 pyros-genmsg kconfiglib jsonschema jinja2 pyserial pyyaml packaging toml numpy \
    pandas future pymavlink \
    fastapi==0.115.6 "uvicorn[standard]==0.34.0" pydantic==2.10.4 pydantic-settings==2.7.1

# Gazebo Garden.
RUN wget https://packages.osrfoundation.org/gazebo.gpg -O /usr/share/keyrings/pkgs-osrf-archive-keyring.gpg && \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/pkgs-osrf-archive-keyring.gpg] http://packages.osrfoundation.org/gazebo/ubuntu-stable $(lsb_release -cs) main" \
      | tee /etc/apt/sources.list.d/gazebo-stable.list > /dev/null && \
    apt-get update && apt-get install -y gz-garden && rm -rf /var/lib/apt/lists/*

# Micro-XRCE-DDS Agent (DDS attack surface, no full ROS2).
RUN cd /tmp && git clone https://github.com/eProsima/Micro-XRCE-DDS-Agent.git && \
    cd Micro-XRCE-DDS-Agent && mkdir build && cd build && cmake .. && \
    make && make install && ldconfig /usr/local/lib/ && \
    cd / && rm -rf /tmp/Micro-XRCE-DDS-Agent

WORKDIR /app
COPY services/drone/ /app/
RUN chmod +x /app/px4/entrypoint.sh /app/px4/start_relays.sh

EXPOSE 9100
EXPOSE 14550/udp
ENTRYPOINT ["/app/px4/entrypoint.sh"]

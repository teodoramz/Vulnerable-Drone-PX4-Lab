FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Core deps always. MAVSDK (px4 backend) is only pulled in when INSTALL_PX4=true,
# so the default mock image stays lean and never depends on MAVSDK.
ARG INSTALL_PX4=false
COPY requirements.txt requirements-px4.txt ./
RUN pip install --no-cache-dir -r requirements.txt && \
    if [ "$INSTALL_PX4" = "true" ]; then pip install --no-cache-dir -r requirements-px4.txt; fi

COPY . .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

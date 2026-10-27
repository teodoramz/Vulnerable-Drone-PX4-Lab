# Mock simulator image (no PX4/Gazebo).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 9100

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9100"]

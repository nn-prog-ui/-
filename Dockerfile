FROM python:3.11-slim

ENV TZ=Asia/Tokyo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

ENV TRADING_MODE=demo_only
ENV APP_ENV=production
ENV DB_PATH=/app/data/fx_monitor.db
ENV DATA_DIR=/app/data/raw

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

COPY ai-fx-monitor/requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && pip install --no-cache-dir -r requirements.txt

COPY ai-fx-monitor/app/ ./app/
COPY ai-fx-monitor/data/ ./data/

RUN mkdir -p /app/data/raw /app/data/processed /app/logs

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

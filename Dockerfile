FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      postgresql-client \
      build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY random_coffee_bot/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

COPY wait-for-db.sh /app/wait-for-db.sh
RUN chmod +x /app/wait-for-db.sh

ENTRYPOINT ["/app/wait-for-db.sh"]

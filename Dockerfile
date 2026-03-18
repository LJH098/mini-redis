FROM python:3.11-slim

WORKDIR /app

COPY . /app

EXPOSE 6379

CMD ["python", "-m", "mini_redis.main"]

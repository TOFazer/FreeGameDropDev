# FreeGameDrop — image de production pour l'auto-hébergement.
# Build :  docker build -t freegamedrop .
# Run :    docker run --env-file .env -v freegamedrop-data:/app/data freegamedrop
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py config.py database.py ./
COPY cogs/ cogs/
COPY services/ services/
COPY utils/ utils/
COPY web/ web/

# La base SQLite vit dans /app/data pour survivre aux mises à jour de l'image.
RUN mkdir -p /app/data
ENV DB_PATH=/app/data/bot.db

CMD ["python", "main.py"]

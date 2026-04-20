FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY configs ./configs
COPY templates ./templates
COPY static ./static
COPY gunicorn_config.py .

EXPOSE 8000

CMD ["gunicorn", "app.wsgi:app", "--config", "gunicorn_config.py"]

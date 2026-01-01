FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY voetbal_scheduler.py .

CMD ["python", "voetbal_scheduler.py"]

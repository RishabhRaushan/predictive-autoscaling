FROM python:3.12-slim

WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY main.py .

RUN useradd --system --uid 10001 app
USER 10001

EXPOSE 8080
# One process with many threads: requests queue on the GIL, so latency rises smoothly under overload.
CMD ["gunicorn", "-b", "0.0.0.0:8080", "-w", "1", "--worker-class", "gthread", "--threads", "256", "main:app"]

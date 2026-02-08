FROM python:3.11-slim

# Install OS dependencies required by Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    wget \
    gnupg \
    build-essential \
    gcc \
    python3-dev \
    libffi-dev \
    libnss3 \
    libxss1 \
    libasound2 \
    fonts-liberation \
    fonts-unifont \
    fonts-dejavu \
    libatk1.0-0 \
    libatk-bridge2.0-0 \
    libcups2 \
    libxcomposite1 \
    libxrandr2 \
    libgtk-3-0 \
    libgbm1 \
    libpangocairo-1.0-0 \
    libx11-6 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project
COPY . /app


RUN python -m pip install --upgrade pip setuptools wheel
RUN pip install -r requirements.txt


# Instalar solo el navegador Chromium de Playwright (las dependencias ya están satisfechas)
RUN python -m playwright install chromium


ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM python:3.11-slim

# Install system dependencies for Playwright/Chromium
RUN apt-get update && apt-get install -y \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libasound2 libpango-1.0-0 \
    libcairo2 libnspr4 libx11-6 libxext6 \
    wget ca-certificates fonts-liberation \
    --no-install-recommends && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright Chromium
RUN playwright install chromium

COPY . .

EXPOSE 8501

CMD streamlit run dashboard.py \
    --server.port=8501 \
    --server.address=0.0.0.0 \
    --server.headless=true

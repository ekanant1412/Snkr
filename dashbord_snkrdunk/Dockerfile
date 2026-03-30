FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ให้ Playwright จัดการ dependencies เองตาม OS — ไม่ต้อง list package มือ
RUN playwright install chromium --with-deps

COPY . .

EXPOSE 8501

CMD streamlit run dashboard.py \
    --server.port=$PORT \
    --server.address=0.0.0.0 \
    --server.headless=true

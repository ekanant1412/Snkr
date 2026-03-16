# 👟 SNKRDUNK Price Tracker — Setup Guide

## วิธีติดตั้งและรัน

### 1. ติดตั้ง Python packages
```bash
pip install streamlit requests beautifulsoup4
```

### 2. วางไฟล์ทั้งสองในโฟลเดอร์เดียวกัน
```
snkrdunk-tracker/
├── snkrdunk_scraper.py
└── dashboard.py
```

### 3. รัน Dashboard
```bash
streamlit run dashboard.py
```

จากนั้นเปิด browser ที่ → **http://localhost:8501**

---

## ฟีเจอร์

| ฟีเจอร์ | รายละเอียด |
|---|---|
| 💱 Exchange Rate | ดึง JPY→THB realtime จาก exchangerate-api.com (ฟรี) |
| 📊 Dashboard | Cards view + Table view |
| 🔍 Search | ค้นหาชื่อรองเท้า |
| 🏷️ Filter | กรองตาม Brand และ ช่วงราคา THB |
| 🔄 Auto Refresh | ตั้งให้ refresh อัตโนมัติทุก 5–60 นาที |
| 📈 Stats | Average price, min/max, จำนวนรองเท้า |

---

## หมายเหตุสำคัญ

- **Demo Mode**: ถ้า SNKRDUNK บล็อก scraping จะแสดงข้อมูลตัวอย่าง แต่ exchange rate ยังเป็นของจริง
- **Exchange Rate**: อัปเดตทุกครั้งที่ refresh
- **Anti-bot**: SNKRDUNK อาจบล็อก IP ถ้า refresh บ่อยเกินไป แนะนำ 15–30 นาทีต่อครั้ง

---

## แก้ไขปัญหา

**Error: Module not found**
```bash
pip install streamlit requests beautifulsoup4 lxml
```

**Dashboard ไม่แสดงข้อมูลจริง (Demo Mode)**
→ ปกติครับ SNKRDUNK มี anti-bot protection ข้อมูล mock จะแสดงแทน

**Port 8501 ใช้งานไม่ได้**
```bash
streamlit run dashboard.py --server.port 8502
```

import streamlit as st
import json
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from snkrdunk_scraper import run_search, save_cookies, load_cookies, normalize_cookies, get_suggestions

st.set_page_config(page_title="SNKRDUNK Search", page_icon="👟", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@400;500;600;700&family=DM+Mono:wght@400;500&display=swap');
html,body,[class*="css"]{font-family:'DM Sans',sans-serif;}
.stApp{background:#080810;color:#e8e8f0;}
.hero{background:linear-gradient(135deg,#0d0d1a,#1a0a2e,#0d1a2e);border:1px solid #2a2a4a;border-radius:16px;padding:1.5rem 2rem;margin-bottom:1.2rem;}
.hero-title{font-family:'Bebas Neue',sans-serif;font-size:2.8rem;letter-spacing:.05em;background:linear-gradient(90deg,#fff,#a78bfa,#60a5fa);-webkit-background-clip:text;-webkit-text-fill-color:transparent;}
.hero-sub{color:#6b7280;font-size:.82rem;font-family:'DM Mono',monospace;}
.stat-box{background:#111120;border:1px solid #1e1e3a;border-radius:12px;padding:.9rem;text-align:center;}
.stat-label{font-size:.65rem;color:#6b7280;text-transform:uppercase;letter-spacing:.1em;font-family:'DM Mono',monospace;}
.stat-value{font-size:1.35rem;font-weight:700;color:#a78bfa;}
.stat-sub{font-size:.65rem;color:#4b5563;font-family:'DM Mono',monospace;}
.result-wrap{background:#0f0f1e;border:1px solid #1a1a30;border-radius:14px;padding:1.2rem 1.4rem;margin-bottom:.8rem;}
.result-wrap:hover{border-color:#3730a3;transition:border-color .2s;}
.rank-badge{background:#1e1e3a;color:#a78bfa;font-size:.62rem;font-weight:700;font-family:'DM Mono',monospace;padding:2px 8px;border-radius:4px;}
.cat-tag{font-size:.62rem;font-weight:600;font-family:'DM Mono',monospace;padding:2px 8px;border-radius:4px;margin-left:.4rem;background:#172554;color:#93c5fd;}
.item-name{font-size:.95rem;font-weight:700;color:#e8e8f0;margin:.4rem 0 .2rem;}
.price-from{font-family:'DM Mono',monospace;font-size:.75rem;color:#9ca3af;margin-bottom:.8rem;}
.sz-table{width:100%;border-collapse:collapse;margin-top:.4rem;}
.sz-table thead tr{background:#0a0a14;}
.sz-table th{font-size:.62rem;font-family:'DM Mono',monospace;color:#6b7280;text-transform:uppercase;letter-spacing:.08em;padding:.4rem .6rem;border-bottom:1px solid #1a1a30;text-align:right;white-space:nowrap;}
.sz-table th:first-child{text-align:left;}
.sz-table td{font-size:.78rem;font-family:'DM Mono',monospace;padding:.38rem .6rem;border-bottom:1px solid #0a0a14;text-align:right;color:#c4c4d4;}
.sz-table td:first-child{text-align:left;color:#c4b5fd;font-weight:700;}
.sz-table tr:hover td{background:#111120;}
.col-thb{color:#34d399 !important;font-weight:700;font-size:.85rem !important;}
.col-total{color:#e8e8f0 !important;font-weight:600;}
.no-login{background:#1a0d0d;border:1px solid #7f1d1d;border-radius:8px;padding:.5rem .9rem;color:#fca5a5;font-size:.76rem;margin:.4rem 0;}
.ok-box{background:#0d1a0d;border:1px solid #14532d;border-radius:8px;padding:.5rem .9rem;color:#86efac;font-size:.76rem;margin-bottom:.8rem;}
.suggest-chip{display:inline-block;background:#1e1e3a;color:#a78bfa;border:1px solid #2e2e5a;border-radius:20px;padding:3px 12px;font-size:.72rem;font-family:'DM Mono',monospace;cursor:pointer;margin:2px;}
.empty-state{text-align:center;padding:4rem 0;color:#4b5563;}
[data-testid="stSidebar"]{background:#0a0a14 !important;border-right:1px solid #1a1a30;}
.stButton>button{background:linear-gradient(135deg,#4f46e5,#7c3aed)!important;color:white!important;border:none!important;border-radius:8px!important;font-weight:600!important;}
div[data-testid="stTextInput"] input{background:#111120!important;border:1px solid #2a2a4a!important;color:#e8e8f0!important;border-radius:10px!important;font-size:1.05rem!important;padding:.6rem 1rem!important;}
</style>
""", unsafe_allow_html=True)

# ─── Session state ────────────────────────────────────────────────────
for k, v in [("results", None), ("active_query", ""), ("suggestions", [])]:
    if k not in st.session_state:
        st.session_state[k] = v

# ─── Sidebar ──────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Settings")
    st.markdown("**🔐 Login Session**")
    existing = load_cookies()
    if existing:
        st.markdown(f'<div class="ok-box">✅ พร้อมใช้งาน</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="no-login">⚠️ ยังไม่มี cookies</div>', unsafe_allow_html=True)
    st.divider()
    max_results = st.slider("จำนวนผลลัพธ์", 5, 30, 15)
    st.divider()
    price_min, price_max = st.slider("กรองราคา ฿", 0, 500000, (0, 500000), 500)
    size_filter = st.text_input("กรอง Size (cm)", placeholder="เช่น 27, 27.5")
    # sidebar — แสดง cookie input เฉพาะ admin
ADMIN_KEY = st.secrets.get("ADMIN_KEY", "")
with st.sidebar:
    admin_input = st.text_input("Admin key", type="password", label_visibility="collapsed",
                                 placeholder="admin key...")
    if admin_input == ADMIN_KEY and ADMIN_KEY:
        st.markdown("**🔐 Admin: Update Cookies**")
        cookie_input = st.text_area("Paste cookies JSON", height=70)
        if cookie_input and st.button("💾 Save Cookies"):
            # บันทึกลง secrets ไม่ได้ตรงๆ — บอก admin ให้ไปอัปเดตใน Streamlit dashboard
            st.warning("ไปอัปเดต SNKRDUNK_COOKIES ใน Streamlit Cloud Secrets แทนครับ")

# ─── Hero ─────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero">
  <div class="hero-title">SNKRDUNK SEARCH</div>
  <div class="hero-sub">ค้นหาจากสินค้าทั้งหมดบน SNKRDUNK · ราคาทุกไซส์มือ 1 · ค่าส่ง + ค่าธรรมเนียม → บาท</div>
</div>
""", unsafe_allow_html=True)

# ─── Search box ───────────────────────────────────────────────────────
col_q, col_btn = st.columns([5, 1])
with col_q:
    query_input = st.text_input("", placeholder="🔍  พิมพ์ชื่อสินค้า เช่น  Jordan 4, Yeezy 350, Dunk Low Panda...",
                                label_visibility="collapsed", key="query_input")
with col_btn:
    do_search = st.button("Search", use_container_width=True)

# Suggestions (ใช้ API จริงของ SNKRDUNK)
if query_input and len(query_input) >= 2 and not do_search:
    suggs = get_suggestions(query_input)
    if suggs:
        chips = "".join([f'<span class="suggest-chip">{s}</span>' for s in suggs[:8]])
        st.markdown(f"<div style='margin-bottom:.5rem;'>{chips}</div>", unsafe_allow_html=True)

# Trigger search
if do_search and query_input:
    st.session_state.results = None
    st.session_state.active_query = query_input

# ─── Run search ───────────────────────────────────────────────────────
if st.session_state.active_query and st.session_state.results is None:
    with st.spinner(f'🔍 ค้นหา "{st.session_state.active_query}" จาก SNKRDUNK ทั้งหมด...'):
        data = run_search(st.session_state.active_query, max_results=max_results)
        st.session_state.results = data

# ─── Results ──────────────────────────────────────────────────────────
if st.session_state.results:
    data = st.session_state.results
    results = data["results"]
    rate = data["rate"]

    if data.get("is_logged_in"):
        st.markdown('<div class="ok-box">✅ Login สำเร็จ — แสดงราคาทุกไซส์พร้อมค่าส่ง</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="no-login">⚠️ ยังไม่ได้ Login — ไม่มีข้อมูลไซส์ / รัน get_cookies.py แล้ว paste ใน sidebar</div>', unsafe_allow_html=True)

    # Stats
    total_sizes = sum(len(r.get("sizes", [])) for r in results)
    c1, c2, c3, c4 = st.columns(4)
    for col, label, val, sub in [
        (c1, "Rate", f"฿{rate:.4f}", "per ¥1 JPY"),
        (c2, "ผลลัพธ์", str(len(results)), f'จาก "{data["query"]}"'),
        (c3, "ไซส์ทั้งหมด", str(total_sizes), "มือ 1"),
        (c4, "Updated", data["updated_at"].split()[1], ""),
    ]:
        col.markdown(f'<div class="stat-box"><div class="stat-label">{label}</div><div class="stat-value">{val}</div><div class="stat-sub">{sub}</div></div>', unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)

    # Items
    for item in results:
        img_col, info_col = st.columns([1, 4])
        with img_col:
            if item.get("image_url"):
                try:
                    st.image(item["image_url"], use_container_width=True)
                except Exception:
                    pass
        with info_col:
            cat_icon = {"products": "👟", "apparels": "👕", "hobbies": "🃏", "luxuries": "💎"}.get(item.get("category", ""), "📦")
            price_from = f"เริ่มต้น ¥{item['price_from_jpy']:,} = ฿{item.get('price_from_thb', 0):,}" if item.get("price_from_jpy") else ""
            st.markdown(f"""<div class="result-wrap">
              <span class="rank-badge">#{item['rank']}</span>
              <span class="cat-tag">{cat_icon} {item.get('category','').upper()}</span>
              <div class="item-name">{item['name']}</div>
              <div class="price-from">{price_from}&nbsp;&nbsp;<a href="{item['url']}" target="_blank" style="color:#818cf8;font-size:.75rem;">🔗 ดูใน SNKRDUNK</a></div>
            """, unsafe_allow_html=True)

            sizes = item.get("sizes", [])
            if size_filter:
                sf = size_filter.strip().upper()
                sizes = [s for s in sizes if sf in s.get("size_label", s.get("size_cm","")).upper()]
            sizes = [s for s in sizes if price_min <= s.get("total_thb", 0) <= price_max]

            if sizes:
                rows = "".join([f"""<tr>
                  <td>{s.get('size_label', s.get('size_cm','?'))}</td>
                  <td>¥{s['price_jpy']:,}</td>
                  <td>+¥{s['shipping_jpy']:,}</td>
                  <td>+¥{s['fee_jpy']:,}</td>
                  <td>+¥{s.get('auth_jpy',0):,}</td>
                  <td class="col-total">¥{s['total_jpy']:,}</td>
                  <td class="col-thb">฿{s['total_thb']:,}</td>
                </tr>""" for s in sizes])
                st.markdown(f"""<table class="sz-table">
                  <thead><tr><th>ไซส์</th><th>ราคา ¥</th><th>ค่าส่ง ¥</th><th>ค่าธรรมเนียม ¥</th><th>鑑定料 ¥</th><th>รวม ¥</th><th>รวม ฿</th></tr></thead>
                  <tbody>{rows}</tbody></table>""", unsafe_allow_html=True)
            elif not data.get("is_logged_in"):
                st.markdown('<div class="no-login">ต้อง login เพื่อดูราคาต่อไซส์</div>', unsafe_allow_html=True)
            else:
                st.markdown('<div style="color:#374151;font-size:.75rem;font-family:DM Mono,monospace;padding:.3rem 0;">ไม่มีไซส์ในเงื่อนไขที่เลือก</div>', unsafe_allow_html=True)

            st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<hr style='border-color:#0a0a14;margin:.3rem 0;'>", unsafe_allow_html=True)

elif not st.session_state.active_query:
    st.markdown("""<div class="empty-state">
      <div style="font-size:3rem;">👟</div>
      <div style="font-size:1.1rem;font-weight:600;color:#6b7280;margin:.5rem 0;">ค้นหาจากสินค้าทั้งหมดบน SNKRDUNK</div>
      <div style="font-size:.85rem;color:#4b5563;">ผลลัพธ์ตรงกับที่เว็บแสดงจริง · ไซส์มือ 1 · ราคาบาท</div>
      <div style="font-size:.75rem;color:#1f2937;margin-top:1.5rem;">Jordan 4 · Yeezy 350 · Nike Dunk Low Panda · KAWS</div>
    </div>""", unsafe_allow_html=True)

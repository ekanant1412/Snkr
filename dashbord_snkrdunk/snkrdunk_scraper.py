import os, json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import quote

import requests


COOKIE_FILE = Path(__file__).parent / "snkrdunk_cookies.json"

SIZE_PATTERN = re.compile(
    r'^(\d{2}(?:\.\d)?cm|(?:[2-9]|10)?XL|[SML]|ONE\s*SIZE|FREE\s*SIZE|\d{1,3}(?:\.\d+)?)$',
    re.IGNORECASE,
)

# ── ติดตั้ง Playwright แค่ครั้งเดียวต่อ process ──────────────────────────
_PLAYWRIGHT_READY = False

# ── Cache อัตราแลกเปลี่ยน 1 ชั่วโมง ──────────────────────────────────────
_rate_cache: dict = {"value": None, "ts": 0.0}
_RATE_TTL = 3600


PARSE_CONFIRM_JS = r"""() => {
    function parseYen(text) {
        if (!text) return 0;
        const m = String(text).replace(/,/g, '').match(/[¥￥]\s*(\d+)/);
        return m ? parseInt(m[1], 10) : 0;
    }

    function clean(s) {
        return String(s || '').replace(/\s+/g, ' ').trim();
    }

    const result = { product: 0, shipping: 0, fee: 0, auth: 0, total: 0, debug_rows: [] };

    // 1) Try to read row-by-row from common containers first
    const rowSelectors = [
        '.amount-breakdown-item',
        '[class*="breakdown"] > div',
        '[class*="price"] > div',
        '[class*="detail"] > div',
        'section div',
        'main div'
    ];

    const visited = new Set();
    const rows = [];

    for (const sel of rowSelectors) {
        for (const el of document.querySelectorAll(sel)) {
            if (visited.has(el)) continue;
            visited.add(el);
            const txt = clean(el.innerText);
            if (!txt) continue;
            if (txt.includes('送料') || txt.includes('購入手数料') || txt.includes('鑑定料') || txt.includes('支払い金額')) {
                rows.push(txt);
            }
        }
    }

    for (const txt of rows) {
        result.debug_rows.push(txt);
        const amount = parseYen(txt);
        if (!amount) continue;
        if (!result.shipping && txt.includes('送料')) result.shipping = amount;
        else if (!result.fee && txt.includes('購入手数料')) result.fee = amount;
        else if (!result.auth && txt.includes('鑑定料')) result.auth = amount;
        else if (!result.total && txt.includes('支払い金額')) result.total = amount;
    }

    // 2) Fallback: use lines, but only the number on the same line / next line of the label
    if (!result.shipping || !result.fee || !result.auth || !result.total) {
        const body = document.body ? (document.body.innerText || '') : '';
        const lines = body.split(/\n+/).map(s => clean(s)).filter(Boolean);

        function findNearLabel(label) {
            for (let i = 0; i < lines.length; i++) {
                if (!lines[i].includes(label)) continue;
                const window = [lines[i], lines[i + 1] || '', lines[i + 2] || ''].join(' ');
                const m = window.match(/[¥￥]\s*([\d,]+)/);
                if (m) return parseInt(m[1].replace(/,/g, ''), 10);
            }
            return 0;
        }

        if (!result.shipping) result.shipping = findNearLabel('送料');
        if (!result.fee) result.fee = findNearLabel('購入手数料');
        if (!result.auth) result.auth = findNearLabel('鑑定料');
        if (!result.total) result.total = findNearLabel('支払い金額');

        // product line: ¥16,390 / 25.5cm × 1
        for (const line of lines) {
            const m = line.match(/[¥￥]\s*([\d,]+)\s*\/\s*.+?[x×]\s*1/i);
            if (m) {
                result.product = parseInt(m[1].replace(/,/g, ''), 10);
                break;
            }
        }
    }

    // 3) More DOM-based fallbacks for total and product
    if (!result.total) {
        const all = Array.from(document.querySelectorAll('*'));
        for (const el of all) {
            const txt = clean(el.innerText);
            if (!txt || !txt.includes('支払い金額')) continue;
            const amount = parseYen(txt);
            if (amount) {
                result.total = amount;
                break;
            }
        }
    }

    if (!result.product) {
        const body = document.body ? (document.body.innerText || '') : '';
        const m = body.match(/[¥￥]\s*([\d,]+)\s*\/\s*.+?[x×]\s*1/i);
        if (m) result.product = parseInt(m[1].replace(/,/g, ''), 10);
    }

    if (!result.total && result.product) {
        result.total = result.product + result.shipping + result.fee + result.auth;
    }

    return result;
}"""


# ─────────────────────────────────────────────────────────────────────────────
# ensure_playwright: ติดตั้งแค่ครั้งแรกต่อ process (ไม่ติดตั้งซ้ำทุก search)
# ─────────────────────────────────────────────────────────────────────────────
def ensure_playwright():
    global _PLAYWRIGHT_READY
    if _PLAYWRIGHT_READY:
        return

    # ตรวจว่า chromium ถูกติดตั้งไปแล้วหรือยัง
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            if os.path.exists(p.chromium.executable_path):
                _PLAYWRIGHT_READY = True
                return
    except Exception:
        pass

    # ติดตั้งเฉพาะเมื่อยังไม่มี
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "playwright", "-q"])

    subprocess.check_call(
        [sys.executable, "-m", "playwright", "install", "chromium"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _PLAYWRIGHT_READY = True


# ─────────────────────────────────────────────────────────────────────────────
# get_exchange_rate: cache 1 ชั่วโมง ไม่ดึงซ้ำทุก search
# ─────────────────────────────────────────────────────────────────────────────
def get_exchange_rate():
    now = time.time()
    if _rate_cache["value"] is not None and now - _rate_cache["ts"] < _RATE_TTL:
        return _rate_cache["value"]
    try:
        r = requests.get("https://api.exchangerate-api.com/v4/latest/JPY", timeout=10)
        rate = r.json()["rates"].get("THB", 0.24)
        _rate_cache.update({"value": rate, "ts": now})
        return rate
    except Exception:
        return _rate_cache["value"] or 0.24


def load_cookies():
    try:
        import streamlit as st
        raw = st.secrets.get("SNKRDUNK_COOKIES")
        if raw:
            return json.loads(raw)
    except Exception:
        pass

    cookie_file = Path(__file__).parent / "snkrdunk_cookies.json"
    if cookie_file.exists():
        with open(cookie_file) as f:
            return json.load(f)

    return []


def save_cookies(cookies):
    with open(COOKIE_FILE, "w", encoding="utf-8") as f:
        json.dump(cookies, f, indent=2, ensure_ascii=False)


def normalize_cookies(raw):
    result = []
    for c in raw:
        cookie = {
            "name": c.get("name", ""),
            "value": c.get("value", ""),
            "domain": c.get("domain", ".snkrdunk.com"),
            "path": c.get("path", "/"),
            "secure": c.get("secure", True),
            "httpOnly": c.get("httpOnly", False),
            "sameSite": c.get("sameSite", "Lax") if c.get("sameSite") in ("Strict", "Lax", "None") else "Lax",
        }
        if "expirationDate" in c:
            cookie["expires"] = int(c["expirationDate"])
        if cookie["name"] and cookie["value"]:
            result.append(cookie)
    return result


def get_suggestions(keyword):
    try:
        r = requests.get(
            f"https://snkrdunk.com/v3/search/suggestions?keyword={quote(keyword)}&limit=10",
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=8,
        )
        return [s["keyword"] for s in r.json().get("suggestions", [])]
    except Exception:
        return []


def get_size_list_url(category, product_id):
    if category == "products":
        return f"https://snkrdunk.com/buy/{product_id}/size/"
    return f"https://snkrdunk.com/{category}/{product_id}/sizes/"


def extract_size_label(text):
    candidates = re.findall(
        r'(\d{2}(?:\.\d)?cm|(?:[2-9]|10)?XL|\bONE\s*SIZE\b|\bFREE\s*SIZE\b|\b[SML]\b|\b\d{1,3}(?:\.\d+)?\b)',
        text,
        re.IGNORECASE,
    )
    for c in candidates:
        c = c.strip()
        if re.match(r'^\d+$', c) and int(c) > 50:
            continue
        if SIZE_PATTERN.match(c):
            return c.upper() if c.upper() in ("S", "M", "L") else c
    return None


def parse_yen_from_text(text: str) -> int:
    if not text:
        return 0
    m = re.search(r'[¥￥]\s*([\d,]+)', text.replace('\xa0', ' '))
    if m:
        return int(m.group(1).replace(',', ''))
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# get_breakdown_from_confirm_page: เอา fixed 1500ms wait ออก ใช้ element wait
# ─────────────────────────────────────────────────────────────────────────────
def get_breakdown_from_confirm_page(page, fallback_price=0):
    parsed = {"product": 0, "shipping": 0, "fee": 0, "auth": 0, "total": 0}

    # รอ element จริง ไม่ใช่ sleep ตาย
    for keyword in ["送料", "購入手数料", "鑑定料", "支払い金額", "内訳"]:
        try:
            page.locator(f"text={keyword}").first.wait_for(timeout=5000)
            break
        except Exception:
            pass

    # ลบ wait_for_timeout(1500) ออก — ไม่จำเป็นแล้ว

    try:
        js_result = page.evaluate(PARSE_CONFIRM_JS)
        for k in ("product", "shipping", "fee", "auth", "total"):
            parsed[k] = int(js_result.get(k, 0) or 0)
    except Exception:
        js_result = {}

    try:
        body_text = page.locator("body").inner_text(timeout=5000)
    except Exception:
        body_text = ""

    lines = [re.sub(r'\s+', ' ', ln).strip() for ln in re.split(r'\n+', body_text) if ln.strip()]

    def find_near_label(label: str) -> int:
        for i, line in enumerate(lines):
            if label not in line:
                continue
            window = " ".join(lines[i:i+3])
            m = re.search(r'[¥￥]\s*([\d,]+)', window)
            if m:
                return int(m.group(1).replace(',', ''))
        return 0

    if not parsed["shipping"]:
        parsed["shipping"] = find_near_label("送料")
    if not parsed["fee"]:
        parsed["fee"] = find_near_label("購入手数料")
    if not parsed["auth"]:
        parsed["auth"] = find_near_label("鑑定料")
    if not parsed["total"]:
        parsed["total"] = find_near_label("支払い金額")

    if not parsed["product"]:
        for line in lines:
            m = re.search(r'[¥￥]\s*([\d,]+)\s*/\s*.+?[x×]\s*1', line, re.I)
            if m:
                parsed["product"] = int(m.group(1).replace(',', ''))
                break

    if not parsed["product"]:
        parsed["product"] = fallback_price
    if not parsed["total"]:
        parsed["total"] = parsed["product"] + parsed["shipping"] + parsed["fee"] + parsed["auth"]

    for k in ("shipping", "fee", "auth"):
        if parsed[k] == parsed["product"] and parsed["product"] > 0:
            parsed[k] = 0

    return parsed


# ─────────────────────────────────────────────────────────────────────────────
# search_products: รอ networkidle เพื่อให้ SPA โหลด API results ครบก่อน
# ─────────────────────────────────────────────────────────────────────────────
def search_products(page, query, max_results=15):
    results = []
    try:
        url = f"https://snkrdunk.com/search?keywords={quote(query)}"
        # networkidle = รอจน network หยุด request — ครอบคลุม SPA ที่โหลด results ผ่าน API
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
        except Exception:
            # fallback กรณี networkidle timeout (เช่น ads ที่ poll ตลอด)
            page.wait_for_timeout(4000)

        items = page.evaluate(
            """() => {
                var links = [...document.querySelectorAll(
                    'a[href*="/products/"], a[href*="/apparels/"], a[href*="/hobbies/"], a[href*="/luxuries/"]'
                )];
                var seen = {}, out = [];
                links.forEach(function(a) {
                    var img = a.querySelector('img');
                    if (!img || !img.alt || seen[a.href]) return;
                    seen[a.href] = 1;
                    var pm = (a.innerText||'').match(/[¥￥]([\\d,]+)/);
                    var pidM = a.pathname.match(/\\/(products|apparels|hobbies|luxuries)\\/([^/?#]+)/);
                    if (!pidM) return;
                    out.push({
                        href: a.href,
                        name: img.alt,
                        image_url: img.src || img.dataset.src || '',
                        price_from_jpy: pm ? parseInt(pm[1].replace(/,/g,'')) : null,
                        category: pidM[1],
                        product_id: pidM[2]
                    });
                });
                return out;
            }"""
        )
        for i, item in enumerate(items[:max_results]):
            item["rank"] = i + 1
            item["url"] = item["href"]
            item["sizes"] = []
            results.append(item)
    except Exception as e:
        print(f"  Search error: {e}")
    return results


def get_size_rows(page):
    raw_list = page.evaluate(
        """() => {
            var result = [];
            document.querySelectorAll('li').forEach(function(li) {
                var text = (li.innerText || '').trim();
                var pm = text.match(/[¥￥]([\\d,]+)/);
                if (!pm) return;
                if (!li.querySelector('.size-price-buy-button')) return;
                var price = parseInt(pm[1].replace(/,/g,''));
                if (price < 500) return;
                result.push({ text: text, price_jpy: price });
            });
            return result;
        }"""
    )

    size_rows = []
    for row in raw_list:
        label = extract_size_label(row["text"])
        if label:
            size_rows.append({"size_label": label, "price_jpy": int(row["price_jpy"])})
    return size_rows


# ─────────────────────────────────────────────────────────────────────────────
# scrape_sizes: ใช้ go_back() แทน goto() ซ้ำทุก size → เร็วขึ้นมาก
# ─────────────────────────────────────────────────────────────────────────────
def scrape_sizes(page, category, product_id):
    sizes = []
    size_list_url = get_size_list_url(category, product_id)

    try:
        page.goto(size_list_url, wait_until="domcontentloaded", timeout=20000)

        # รอ size button ขึ้นจริง ไม่ sleep ตาย
        try:
            page.locator(".size-price-buy-button").first.wait_for(timeout=6000)
        except Exception:
            page.wait_for_timeout(1500)

        if "login" in page.url or "signup" in page.url:
            return []

        size_rows = get_size_rows(page)
        if not size_rows:
            return []

        print(f"    sizes found: {[s['size_label'] for s in size_rows]}")

        for i in range(len(size_rows)):
            # size แรก: อยู่หน้า size list แล้ว
            # size ถัดไป: ใช้ go_back() แทน goto() — เร็วกว่า 2-3x
            if i > 0:
                try:
                    page.go_back(wait_until="domcontentloaded", timeout=12000)
                except Exception:
                    page.goto(size_list_url, wait_until="domcontentloaded", timeout=20000)
                try:
                    page.locator(".size-price-buy-button").first.wait_for(timeout=4000)
                except Exception:
                    page.wait_for_timeout(800)

            li_locator = page.locator("li").filter(has=page.locator(".size-price-buy-button"))
            count = li_locator.count()
            if i >= count:
                break

            li = li_locator.nth(i)
            text = li.inner_text(timeout=5000).strip()
            size_label = extract_size_label(text) or size_rows[i]["size_label"]
            price_jpy = parse_yen_from_text(text) or size_rows[i]["price_jpy"]

            btn = li.locator(".size-price-buy-button").first

            try:
                before_url = page.url
                btn.scroll_into_view_if_needed(timeout=3000)

                navigation_done = False
                try:
                    with page.expect_navigation(wait_until="domcontentloaded", timeout=12000):
                        btn.click()
                    navigation_done = True
                except Exception:
                    try:
                        btn.click(force=True)
                    except Exception:
                        li.click(force=True)

                if not navigation_done:
                    for _ in range(20):
                        page.wait_for_timeout(400)
                        if page.url != before_url and (
                            "/size/" in page.url or "/sizes/" in page.url or "slide=right" in page.url
                        ):
                            break

                parsed = get_breakdown_from_confirm_page(page, fallback_price=price_jpy)

                product_jpy = parsed["product"] or price_jpy
                shipping_jpy = parsed["shipping"]
                fee_jpy = parsed["fee"]
                auth_jpy = parsed["auth"]
                total_jpy = parsed["total"] or (product_jpy + shipping_jpy + fee_jpy + auth_jpy)

                print(
                    f"      {size_label}: ¥{product_jpy} +ship¥{shipping_jpy} +fee¥{fee_jpy} +auth¥{auth_jpy} = ¥{total_jpy}"
                )

                sizes.append(
                    {
                        "size_label": size_label,
                        "price_jpy": product_jpy,
                        "shipping_jpy": shipping_jpy,
                        "fee_jpy": fee_jpy,
                        "auth_jpy": auth_jpy,
                        "total_jpy": total_jpy,
                    }
                )
            except Exception as e:
                print(f"      {size_label} error: {e}")
                sizes.append(
                    {
                        "size_label": size_label,
                        "price_jpy": price_jpy,
                        "shipping_jpy": 0,
                        "fee_jpy": 0,
                        "auth_jpy": 0,
                        "total_jpy": price_jpy,
                    }
                )

    except Exception as e:
        print(f"  Sizes error {product_id}: {e}")

    return sizes


def run_search(query, max_results=15, cookies=None):
    ensure_playwright()
    from playwright.sync_api import sync_playwright

    rate = get_exchange_rate()
    raw_cookies = cookies or load_cookies()
    cookie_list = normalize_cookies(raw_cookies) if raw_cookies else []
    is_logged_in = False

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox", "--disable-dev-shm-usage"])
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            locale="ja-JP",
        )
        if cookie_list:
            try:
                context.add_cookies(cookie_list)
            except Exception:
                pass

        page = context.new_page()
        page.goto("https://snkrdunk.com/buy/HM4740-001/size/", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(1000)
        is_logged_in = "login" not in page.url and "signup" not in page.url

        items = search_products(page, query, max_results)
        print(f"  Found {len(items)} results for '{query}'")

        if is_logged_in:
            for i, item in enumerate(items):
                print(f"  [{i + 1}/{len(items)}] {item['name'][:50]}...")
                szs = scrape_sizes(page, item["category"], item["product_id"])
                for s in szs:
                    s["total_thb"] = round(s["total_jpy"] * rate)
                    s["price_thb"] = round(s["price_jpy"] * rate)
                    s["shipping_thb"] = round(s["shipping_jpy"] * rate)
                    s["fee_thb"] = round(s["fee_jpy"] * rate)
                    s["auth_thb"] = round(s["auth_jpy"] * rate)
                item["sizes"] = szs
                print(f"    → {len(szs)} sizes scraped")

        for item in items:
            if item.get("price_from_jpy"):
                item["price_from_thb"] = round(item["price_from_jpy"] * rate)
            item["rate"] = rate

        browser.close()

    return {
        "query": query,
        "results": items,
        "rate": rate,
        "is_logged_in": is_logged_in,
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

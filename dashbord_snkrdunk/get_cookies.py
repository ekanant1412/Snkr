#!/usr/bin/env python3
"""
รัน script นี้บน Mac เพื่อดึง cookies จาก Chrome แล้วบันทึกลงไฟล์
ใช้: python3 get_cookies.py
"""
import subprocess, json, sys, os, time
from pathlib import Path

OUTPUT = Path(__file__).parent / "snkrdunk_cookies.json"

def get_via_applescript():
    """ใช้ AppleScript ดึง cookie จาก Chrome DevTools"""
    script = '''
    tell application "Google Chrome"
        set tab_list to every tab of every window
        repeat with win_tabs in tab_list
            repeat with t in win_tabs
                if URL of t contains "snkrdunk" then
                    set result to execute t javascript "
                        JSON.stringify(document.cookie.split(';').map(c => {
                            const eq = c.indexOf('=');
                            return {
                                name: c.substring(0, eq).trim(),
                                value: c.substring(eq+1).trim(),
                                domain: '.snkrdunk.com',
                                path: '/',
                                secure: true,
                                httpOnly: false,
                                sameSite: 'Lax'
                            };
                        }).filter(c => c.name && c.value))
                    "
                    return result
                end if
            end repeat
        end repeat
        return "[]"
    end tell
    '''
    result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True)
    if result.returncode == 0 and result.stdout.strip():
        return json.loads(result.stdout.strip())
    return []

def main():
    print("🍪 กำลังดึง cookies จาก Chrome...")
    
    cookies = get_via_applescript()
    
    if not cookies:
        print("❌ ดึงไม่ได้ — ตรวจสอบว่า Chrome เปิดและ login snkrdunk.com อยู่")
        sys.exit(1)
    
    # กรองเฉพาะที่จำเป็น
    keep = {'ch-session', 'ch-veil-id', 'aws-waf-token', 'session', '_dd_s', 'forterToken'}
    important = [c for c in cookies if any(k in c['name'] for k in keep)]
    all_cookies = cookies  # เอาทั้งหมดก็ได้
    
    with open(OUTPUT, 'w') as f:
        json.dump(all_cookies, f, indent=2)
    
    print(f"✅ บันทึก {len(all_cookies)} cookies → {OUTPUT}")
    print(f"   Session cookies: {[c['name'] for c in important]}")

if __name__ == "__main__":
    main()

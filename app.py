from flask import Flask, request, jsonify, render_template_string, redirect, session
import sqlite3
import secrets
import time
import os
import traceback
from datetime import datetime

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

ADMIN_PASSWORD = "MySecretPass2026" # كلمة السر الخاصة بك

# استخدام مسار مؤقت مضمون على Render
DB_PATH = "/tmp/licenses.db"

def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS licenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                days INTEGER NOT NULL,
                note TEXT DEFAULT '',
                created_at REAL NOT NULL,
                expire_at REAL NOT NULL,
                used_count INTEGER DEFAULT 0,
                max_uses INTEGER DEFAULT 1,
                banned INTEGER DEFAULT 0
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT,
                serial TEXT,
                game TEXT,
                ip TEXT,
                result TEXT,
                timestamp REAL
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB INIT ERROR: {e}")

# تهيئة قاعدة البيانات فوراً عند التشغيل
init_db()

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.errorhandler(500)
def internal_error(error):
    error_msg = traceback.format_exc()
    return f"<h1>حدث خطأ داخلي</h1><pre>{error_msg}</pre>", 500

@app.route("/connect", methods=["POST"])
@app.route("/api/verify", methods=["POST"])
def verify():
    try:
        game = request.form.get("game", "pubg")
        user_key = (request.form.get("user_key", "") or "").strip().upper()
        serial = request.form.get("serial", "")
        ip = request.remote_addr or "unknown"

        if not user_key:
            log_attempt(user_key, serial, game, ip, "empty_key")
            return jsonify({"status": False, "message": "Missing key"}), 400

        conn = db()
        row = conn.execute("SELECT * FROM licenses WHERE key = ?", (user_key,)).fetchone()

        if not row:
            log_attempt(user_key, serial, game, ip, "not_found")
            conn.close()
            return jsonify({"status": False, "message": "Invalid key"})

        if row["banned"] == 1:
            log_attempt(user_key, serial, game, ip, "banned")
            conn.close()
            return jsonify({"status": False, "message": "Key banned"})

        if row["expire_at"] < time.time():
            log_attempt(user_key, serial, game, ip, "expired")
            conn.close()
            return jsonify({"status": False, "message": "Key expired"})

        if row["used_count"] >= row["max_uses"]:
            log_attempt(user_key, serial, game, ip, "max_uses")
            conn.close()
            return jsonify({"status": False, "message": "Max uses reached"})

        conn.execute("UPDATE licenses SET used_count = used_count + 1 WHERE key = ?", (user_key,))
        conn.commit()
        log_attempt(user_key, serial, game, ip, "success")
        conn.close()

        days_left = int((row["expire_at"] - time.time()) / 86400)
        return jsonify({
            "status": True,
            "message": "OK",
            "days_left": days_left,
            "expire_at": row["expire_at"],
        })
    except Exception as e:
        return jsonify({"status": False, "message": f"Server error: {str(e)}"}), 500

def log_attempt(key, serial, game, ip, result):
    try:
        conn = db()
        conn.execute(
            "INSERT INTO logs (key, serial, game, ip, result, timestamp) VALUES (?,?,?,?,?,?)",
            (key, serial, game, ip, result, time.time())
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

def generate_key(prefix="MW"):
    parts = [prefix]
    for _ in range(3):
        parts.append(secrets.token_hex(2).upper())
    return "-".join(parts)

ADMIN_HTML = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
<meta charset="UTF-8">
<title>لوحة تحكم المفاتيح</title>
<style>
    body { font-family: 'Segoe UI', Tahoma; background: #0a0a0f; color: #e0e0e0; padding: 20px; margin: 0; }
    h1 { color: #ff3355; border-bottom: 2px solid #ff3355; padding-bottom: 10px; }
    h2 { color: #ff6677; margin-top: 30px; }
    table { width: 100%; border-collapse: collapse; margin-top: 15px; background: #151520; }
    th, td { padding: 10px; text-align: right; border-bottom: 1px solid #333; font-size: 14px; }
    th { background: #1a1a25; color: #ff3355; }
    tr:hover { background: #202030; }
    input, button { padding: 10px 14px; margin: 5px 3px; border-radius: 5px; border: 1px solid #444; background: #1a1a25; color: #fff; font-family: inherit; }
    button { background: #ff3355; cursor: pointer; border: none; font-weight: bold; }
    button:hover { background: #ff5566; }
    button.danger { background: #aa0000; }
    .success { color: #00ff66; }
    .error { color: #ff3355; }
    .box { background: #151520; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
    .expired { color: #ff6666; }
    .active { color: #00ff66; }
    .key-cell { font-family: monospace; font-size: 15px; color: #ffd700; }
</style>
</head>
<body>
<h1>🔑 لوحة تحكم المفاتيح</h1>

<div class="box">
    <h2>➕ توليد مفتاح جديد</h2>
    <form method="POST" action="/admin/generate">
        <input name="prefix" placeholder="بادئة" value="VIP" required>
        <input name="days" type="number" placeholder="عدد الأيام" value="30" required>
        <input name="note" placeholder="ملاحظة" value="">
        <input name="max_uses" type="number" placeholder="حد الاستخدامات" value="1" required>
        <button type="submit">🎲 توليد</button>
    </form>
</div>

<div class="box">
    <h2>📋 قائمة المفاتيح ({{ licenses|length }})</h2>
    <table>
        <tr>
            <th>المفتاح</th>
            <th>الأيام</th>
            <th>ملاحظة</th>
            <th>الاستخدامات</th>
            <th>ينتهي في</th>
            <th>الحالة</th>
            <th>إجراءات</th>
        </tr>
        {% for l in licenses %}
        <tr>
            <td class="key-cell">{{ l.key }}</td>
            <td>{{ l.days }}</td>
            <td>{{ l.note }}</td>
            <td>{{ l.used_count }}/{{ l.max_uses }}</td>
            <td>{{ l.expire_str }}</td>
            <td class="{{ 'active' if l.is_active else 'expired' }}">
                {{ '✅ نشط' if l.is_active else '❌ منتهي' }}
            </td>
            <td>
                <form method="POST" action="/admin/delete" style="display:inline">
                    <input type="hidden" name="key" value="{{ l.key }}">
                    <button class="danger" type="submit" onclick="return confirm('حذف المفتاح؟')">🗑️</button>
                </form>
                <form method="POST" action="/admin/ban" style="display:inline">
                    <input type="hidden" name="key" value="{{ l.key }}">
                    <button type="submit">{{ '🔓' if l.banned else '🚫' }}</button>
                </form>
            </td>
        </tr>
        {% endfor %}
    </table>
</div>

<div class="box">
    <h2>📊 آخر 50 محاولة دخول</h2>
    <table>
        <tr><th>المفتاح</th><th>Serial</th><th>IP</th><th>النتيجة</th><th>الوقت</th></tr>
        {% for log in logs %}
        <tr>
            <td>{{ log.key }}</td>
            <td>{{ log.serial[:20] }}...</td>
            <td>{{ log.ip }}</td>
            <td class="{{ 'active' if log.result == 'success' else 'expired' }}">{{ log.result }}</td>
            <td>{{ log.time_str }}</td>
        </tr>
        {% endfor %}
    </table>
</div>

</body>
</html>
"""

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        pw = request.form.get("password", "")
        if pw == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/admin")
        else:
            return "<h1 style='color:red'>كلمة سر خاطئة</h1><a href='/admin'>عودة</a>"

    if not session.get("admin"):
        return render_template_string("""
            <body style="background:#0a0a0f;color:#fff;font-family:Tahoma;display:flex;justify-content:center;align-items:center;height:100vh;margin:0">
            <form method="POST" style="background:#151520;padding:40px;border-radius:10px;border:2px solid #ff3355">
                <h1 style="color:#ff3355;text-align:center">🔐 دخول الأدمن</h1>
                <input name="password" type="password" placeholder="كلمة السر" style="width:100%;padding:12px;border-radius:5px;border:1px solid #444;background:#1a1a25;color:#fff;margin-bottom:10px;box-sizing:border-box">
                <button type="submit" style="width:100%;padding:12px;background:#ff3355;border:none;border-radius:5px;color:#fff;cursor:pointer;font-size:16px">دخول</button>
            </form>
            </body>
        """)

    try:
        conn = db()
        rows = conn.execute("SELECT * FROM licenses ORDER BY id DESC").fetchall()
        logs_rows = conn.execute("SELECT * FROM logs ORDER BY id DESC LIMIT 50").fetchall()
        conn.close()

        now = time.time()
        licenses = []
        for r in rows:
            d = dict(r)
            d["expire_str"] = datetime.fromtimestamp(r["expire_at"]).strftime("%Y-%m-%d %H:%M")
            d["is_active"] = r["expire_at"] > now and r["banned"] == 0
            licenses.append(d)

        logs = []
        for l in logs_rows:
            logs.append({
                "key": l["key"] or "",
                "serial": l["serial"] or "",
                "ip": l["ip"] or "",
                "result": l["result"] or "",
                "time_str": datetime.fromtimestamp(l["timestamp"]).strftime("%m-%d %H:%M") if l["timestamp"] else "",
            })

        return render_template_string(ADMIN_HTML, licenses=licenses, logs=logs)
    except Exception as e:
        return f"<h1>خطأ في قاعدة البيانات</h1><pre>{traceback.format_exc()}</pre>"

@app.route("/admin/generate", methods=["POST"])
def admin_generate():
    if not session.get("admin"):
        return redirect("/admin")
    try:
        prefix = request.form.get("prefix", "MW").upper().strip()
        days = int(request.form.get("days", 30))
        note = request.form.get("note", "")
        max_uses = int(request.form.get("max_uses", 1))

        key = generate_key(prefix)
        now = time.time()
        expire_at = now + days * 86400

        conn = db()
        conn.execute(
            "INSERT INTO licenses (key, days, note, created_at, expire_at, max_uses) VALUES (?,?,?,?,?,?)",
            (key, days, note, now, expire_at, max_uses)
        )
        conn.commit()
        conn.close()
    except Exception:
        pass
    return redirect("/admin")

@app.route("/admin/delete", methods=["POST"])
def admin_delete():
    if not session.get("admin"):
        return redirect("/admin")
    key = request.form.get("key", "")
    conn = db()
    conn.execute("DELETE FROM licenses WHERE key = ?", (key,))
    conn.commit()
    conn.close()
    return redirect("/admin")

@app.route("/admin/ban", methods=["POST"])
def admin_ban():
    if not session.get("admin"):
        return redirect("/admin")
    key = request.form.get("key", "")
    conn = db()
    conn.execute("UPDATE licenses SET banned = 1 - banned WHERE key = ?", (key,))
    conn.commit()
    conn.close()
    return redirect("/admin")

@app.route("/")
def home():
    return """
    <body style="background:#0a0a0f;color:#ff3355;font-family:Tahoma;text-align:center;padding:50px">
        <h1>🔑 MW License Server</h1>
        <p style="color:#00ff66">✅ السيرفر شغال</p>
        <p><a href="/admin" style="color:#ff6677">لوحة التحكم</a></p>
    </body>
    """

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)

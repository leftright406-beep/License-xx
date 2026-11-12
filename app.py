from flask import Flask, request, redirect, session, render_template_string
import sqlite3
import secrets
import time
import os

app = Flask(__name__)
app.secret_key = secrets.token_hex(32)

# 🔑 كلمة سر لوحة التحكم (غيرها للي تبي)
ADMIN_PASSWORD = "MySecretPass2026"

# 💾 مسار قاعدة البيانات الآمن في Render
DB_PATH = "/tmp/vawzen_license.db"

# ============================================================
# إعداد قاعدة البيانات (تشتغل تلقائياً عند تشغيل السيرفر)
# ============================================================
def init_db():
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS licenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                key TEXT UNIQUE NOT NULL,
                days INTEGER NOT NULL,
                max_uses INTEGER DEFAULT 1,
                used_count INTEGER DEFAULT 0,
                created_at REAL NOT NULL,
                expire_at REAL NOT NULL,
                banned INTEGER DEFAULT 0
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Init Error: {e}")

init_db()

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ============================================================
# 🌐 API للتحقق من المفتاح (اللعبة تتصل هنا)
# ============================================================
@app.route("/connect", methods=["POST", "GET"])
@app.route("/api/verify", methods=["POST", "GET"])
def verify():
    try:
        # استقبال البيانات من اللعبة
        user_key = (request.values.get("user_key") or "").strip().upper()
        
        if not user_key:
            return "INVALID"

        conn = db()
        row = conn.execute("SELECT * FROM licenses WHERE key = ?", (user_key,)).fetchone()

        # التحقق من المفتاح
        if not row:
            conn.close()
            return "INVALID"

        if row["banned"] == 1:
            conn.close()
            return "BANNED"

        if row["expire_at"] < time.time():
            conn.close()
            return "EXPIRED"

        if row["used_count"] >= row["max_uses"]:
            conn.close()
            return "MAX_USES"

        # تحديث عدد الاستخدامات
        conn.execute("UPDATE licenses SET used_count = used_count + 1 WHERE key = ?", (user_key,))
        conn.commit()
        conn.close()

        # ✅ الرد الذي تفهمه اللعبة ويفتح القائمة (مهم جداً)
        return "OK"
        
    except Exception as e:
        return f"ERROR: {str(e)}", 500

# ============================================================
# 💻 لوحة التحكم (توليد وإدارة المفاتيح)
# ============================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
<meta charset="UTF-8">
<title>لوحة تحكم VAWZEN</title>
<style>
    body { font-family: 'Segoe UI', Tahoma; background: #0a0a0f; color: #e0e0e0; padding: 20px; margin: 0; }
    h1 { color: #ff3355; border-bottom: 2px solid #ff3355; padding-bottom: 10px; }
    table { width: 100%; border-collapse: collapse; margin-top: 15px; background: #151520; }
    th, td { padding: 12px; text-align: right; border-bottom: 1px solid #333; }
    th { background: #1a1a25; color: #ff3355; }
    tr:hover { background: #202030; }
    input, button { padding: 10px; margin: 5px; border-radius: 5px; border: 1px solid #444; background: #1a1a25; color: #fff; }
    button { background: #ff3355; cursor: pointer; border: none; font-weight: bold; }
    button:hover { background: #ff5566; }
    button.danger { background: #aa0000; }
    .box { background: #151520; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
    .key-cell { font-family: monospace; color: #ffd700; font-size: 16px; }
    .active { color: #00ff66; }
    .expired { color: #ff6666; }
</style>
</head>
<body>
<h1>🔑 لوحة تحكم VAWZEN</h1>

<div class="box">
    <h2>➕ توليد مفتاح</h2>
    <form method="POST" action="/admin/generate">
        <input name="prefix" value="VWZ" placeholder="بادئة" required>
        <input name="days" type="number" value="30" placeholder="الأيام" required>
        <input name="max_uses" type="number" value="1" placeholder="حد الاستخدام" required>
        <button type="submit">🎲 توليد المفتاح</button>
    </form>
</div>

<div class="box">
    <h2>📋 المفاتيح</h2>
    <table>
        <tr><th>المفتاح</th><th>الأيام</th><th>الاستخدام</th><th>الحالة</th><th>إجراء</th></tr>
        {% for l in licenses %}
        <tr>
            <td class="key-cell">{{ l.key }}</td>
            <td>{{ l.days }}</td>
            <td>{{ l.used_count }}/{{ l.max_uses }}</td>
            <td class="{{ 'active' if l.is_active else 'expired' }}">{{ '✅ نشط' if l.is_active else '❌ منتهي' }}</td>
            <td>
                <form method="POST" action="/admin/delete" style="display:inline">
                    <input type="hidden" name="key" value="{{ l.key }}">
                    <button class="danger" type="submit">🗑️ حذف</button>
                </form>
            </td>
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
        if request.form.get("password") == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/admin")
        return "<h1 style='color:red;text-align:center'>كلمة سر خاطئة</h1>"

    if not session.get("admin"):
        return """
        <body style="background:#0a0a0f;color:#fff;font-family:Tahoma;display:flex;justify-content:center;align-items:center;height:100vh;margin:0">
        <form method="POST" style="background:#151520;padding:40px;border-radius:10px;border:2px solid #ff3355">
            <h1 style="color:#ff3355;text-align:center">🔐 دخول الأدمن</h1>
            <input name="password" type="password" placeholder="كلمة السر" style="width:100%;padding:12px;margin-bottom:10px;box-sizing:border-box">
            <button type="submit" style="width:100%;padding:12px;background:#ff3355;color:#fff;border:none;font-size:16px">دخول</button>
        </form>
        </body>
        """

    conn = db()
    rows = conn.execute("SELECT * FROM licenses ORDER BY id DESC").fetchall()
    conn.close()
    
    now = time.time()
    licenses = []
    for r in rows:
        d = dict(r)
        d["is_active"] = r["expire_at"] > now and r["banned"] == 0
        licenses.append(d)

    return render_template_string(HTML_TEMPLATE, licenses=licenses)

@app.route("/admin/generate", methods=["POST"])
def admin_generate():
    if not session.get("admin"): return redirect("/admin")
    
    prefix = request.form.get("prefix", "VWZ").upper()
    days = int(request.form.get("days", 30))
    max_uses = int(request.form.get("max_uses", 1))
    
    new_key = f"{prefix}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"
    now = time.time()
    
    conn = db()
    try:
        conn.execute(
            "INSERT INTO licenses (key, days, created_at, expire_at, max_uses) VALUES (?,?,?,?,?)",
            (new_key, days, now, now + (days * 86400), max_uses)
        )
        conn.commit()
    except:
        pass
    conn.close()
    return redirect("/admin")

@app.route("/admin/delete", methods=["POST"])
def admin_delete():
    if not session.get("admin"): return redirect("/admin")
    conn = db()
    conn.execute("DELETE FROM licenses WHERE key = ?", (request.form.get("key"),))
    conn.commit()
    conn.close()
    return redirect("/admin")

@app.route("/")
def home():
    return "<h1 style='text-align:center;color:#00ff66;margin-top:50px'>✅ سيرفر VAWZEN شغال</h1>"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

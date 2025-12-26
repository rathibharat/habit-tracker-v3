import os, sqlite3, calendar, datetime
from flask import Flask, render_template, request, redirect, url_for, session, g, jsonify, send_file
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps
from io import BytesIO
from openpyxl import Workbook

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "streakly-secret")

# Rate limiter
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)
limiter.init_app(app)

DB = "streakly.db"

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB)
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(e=None):
    db = g.pop("db", None)
    if db:
        db.close()

def init_db():
    db = get_db()
    db.executescript("""
    CREATE TABLE IF NOT EXISTS user (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE,
        password TEXT
    );

    CREATE TABLE IF NOT EXISTS habit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        name TEXT,
        frequency TEXT,
        created_on TEXT
    );

    CREATE TABLE IF NOT EXISTS habit_entry (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        habit_id INTEGER,
        date TEXT,
        completed INTEGER DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS day_reason (
        user_id INTEGER,
        date TEXT,
        reason TEXT,
        PRIMARY KEY(user_id, date)
    );
    """)
    db.commit()

with app.app_context():
    init_db()

def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapped

# Jinja filter: habit_id -> habit name
@app.template_filter("habit_name")
def habit_name(habit_id):
    db = get_db()
    h = db.execute("SELECT name FROM habit WHERE id=?", (habit_id,)).fetchone()
    return h["name"] if h else "Unknown"

# ---------------- Auth ----------------
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
@limiter.limit("20/hour")
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not email or not password:
            return render_template("login.html", error="Email and password required")

        db = get_db()
        user = db.execute("SELECT * FROM user WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            return redirect("/home")

        return render_template("login.html", error="Invalid credentials")

    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
@limiter.limit("10/hour")
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        if not email or not password:
            return render_template("register.html", error="Email and password required")

        db = get_db()
        try:
            db.execute(
                "INSERT INTO user (email, password) VALUES (?,?)",
                (email, generate_password_hash(password))
            )
            db.commit()
            return redirect("/login")
        except sqlite3.IntegrityError:
            return render_template("register.html", error="Email already registered")

    return render_template("register.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ---------------- Home ----------------
@app.route("/home", methods=["GET", "POST"])
@login_required
def home():
    db = get_db()
    user_id = session["user_id"]
    today = datetime.date.today()

    # Month navigation
    month_param = request.args.get("month")
    if month_param:
        year, month = map(int, month_param.split("-"))
        current_month = datetime.date(year, month, 1)
    else:
        current_month = today.replace(day=1)

    prev_month = (current_month - datetime.timedelta(days=1)).replace(day=1)
    next_month = (current_month + datetime.timedelta(days=32)).replace(day=1)

    # Add / Remove Habit
    if request.method == "POST":
        action = request.form.get("action")

        if action == "add":
            name = request.form.get("habit_name", "").strip()
            freq = request.form.get("frequency", "daily")
            if name:
                db.execute(
                    "INSERT INTO habit (user_id,name,frequency,created_on) VALUES (?,?,?,?)",
                    (user_id, name, freq, today.isoformat())
                )
                habit_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

                # create entries only from today onward in the current view month (no backfill)
                month_last = calendar.monthrange(current_month.year, current_month.month)[1]
                start_day = 1

                if current_month.year == today.year and current_month.month == today.month:
                    start_day = today.day
                elif current_month < today.replace(day=1):
                    start_day = month_last + 1  # don't create in past month view

                for d in range(start_day, month_last + 1):
                    date = datetime.date(current_month.year, current_month.month, d)
                    if date < today:
                        continue

                    should_exist = (
                        freq == "daily" or
                        (freq == "weekly" and date.weekday() == 5) or
                        (freq == "monthly" and d == month_last - 1)
                    )
                    if should_exist:
                        db.execute(
                            "INSERT INTO habit_entry (habit_id,date) VALUES (?,?)",
                            (habit_id, date.isoformat())
                        )

        elif action == "remove":
            hid = request.form.get("habit_id")
            if hid:
                db.execute(
                    "DELETE FROM habit_entry WHERE habit_id=? AND date>=?",
                    (hid, today.isoformat())
                )
                db.execute(
                    "DELETE FROM habit WHERE id=? AND user_id=?",
                    (hid, user_id)
                )

        db.commit()
        return redirect(request.url)

    # Load habits
    habits = db.execute(
        "SELECT * FROM habit WHERE user_id=? ORDER BY id DESC",
        (user_id,)
    ).fetchall()

    # Ensure future entries exist for this month (never create past entries)
    month_last = calendar.monthrange(current_month.year, current_month.month)[1]
    for d in range(1, month_last + 1):
        date = datetime.date(current_month.year, current_month.month, d)

        if date >= today:
            for h in habits:
                should_exist = (
                    h["frequency"] == "daily" or
                    (h["frequency"] == "weekly" and date.weekday() == 5) or
                    (h["frequency"] == "monthly" and d == month_last - 1)
                )
                if should_exist:
                    existing = db.execute(
                        "SELECT 1 FROM habit_entry WHERE habit_id=? AND date=?",
                        (h["id"], date.isoformat())
                    ).fetchone()
                    if not existing:
                        db.execute(
                            "INSERT INTO habit_entry (habit_id,date) VALUES (?,?)",
                            (h["id"], date.isoformat())
                        )
            db.commit()

    # Build real calendar grid: Mon..Sun headers + leading blanks
    # calendar.monthrange => (weekday_of_first_day Mon=0..Sun=6, num_days)
    first_weekday, num_days = calendar.monthrange(current_month.year, current_month.month)

    month_cells = []
    # Add leading blanks (Mon=0 means no blanks; Tue=1 means 1 blank, etc.)
    for _ in range(first_weekday):
        month_cells.append(None)

    # Add day objects
    for d in range(1, num_days + 1):
        date = datetime.date(current_month.year, current_month.month, d)

        entries = db.execute("""
            SELECT * FROM habit_entry
            WHERE date=? AND habit_id IN (SELECT id FROM habit WHERE user_id=?)
            ORDER BY habit_id ASC
        """, (date.isoformat(), user_id)).fetchall()

        reason_row = db.execute(
            "SELECT reason FROM day_reason WHERE user_id=? AND date=?",
            (user_id, date.isoformat())
        ).fetchone()

        month_cells.append({
            "date": date,
            "entries": entries,
            "reason": reason_row["reason"] if reason_row else ""
        })

    # ---- Per-habit current streak (show on Home) ----
       # ---- Per-habit: current streak + consistency % for the viewed month ----
    habit_stats = []

    month_start = current_month.isoformat()
    month_end = datetime.date(
        current_month.year,
        current_month.month,
        calendar.monthrange(current_month.year, current_month.month)[1]
    ).isoformat()

    for h in habits:
        # All entries for the habit (for streak calc)
        rows_all = db.execute(
            "SELECT date, completed FROM habit_entry WHERE habit_id=? ORDER BY date ASC",
            (h["id"],)
        ).fetchall()

        # Current streak (ending at latest <= today)
        current_streak = 0
        for r in reversed(rows_all):
            d = datetime.date.fromisoformat(r["date"])
            if d > today:
                continue
            if r["completed"] == 1:
                current_streak += 1
            else:
                break

        # Month consistency (viewed month)
        rows_month = db.execute("""
            SELECT completed
            FROM habit_entry
            WHERE habit_id=? AND date>=? AND date<=?
        """, (h["id"], month_start, month_end)).fetchall()

        m_total = len(rows_month)
        m_done = sum(1 for r in rows_month if r["completed"] == 1)
        m_consistency = int((m_done / m_total) * 100) if m_total else 0

        # Simple status bucket for icon
        if m_total == 0:
            vibe = "🌱"   # no scheduled days this month
        elif m_consistency >= 85:
            vibe = "🔥"
        elif m_consistency >= 60:
            vibe = "✨"
        else:
            vibe = "🧠"

        habit_stats.append({
            "name": h["name"],
            "frequency": h["frequency"],
            "streak": current_streak,
            "m_total": m_total,
            "m_done": m_done,
            "m_consistency": m_consistency,
            "vibe": vibe
        })
        
    def month_range(d: datetime.date):
        first = d.replace(day=1)
        last_day = calendar.monthrange(d.year, d.month)[1]
        last = d.replace(day=last_day)
        return first.isoformat(), last.isoformat()

    # Overall consistency for viewed month and previous month (2 numbers, no charts)
    this_start, this_end = month_range(current_month)
    prev_month_first = (current_month - datetime.timedelta(days=1)).replace(day=1)
    last_start, last_end = month_range(prev_month_first)

    this_rows = db.execute("""
        SELECT he.completed
        FROM habit_entry he
        JOIN habit h ON h.id = he.habit_id
        WHERE h.user_id=? AND he.date>=? AND he.date<=?
    """, (user_id, this_start, this_end)).fetchall()

    last_rows = db.execute("""
        SELECT he.completed
        FROM habit_entry he
        JOIN habit h ON h.id = he.habit_id
        WHERE h.user_id=? AND he.date>=? AND he.date<=?
    """, (user_id, last_start, last_end)).fetchall()

    this_total = len(this_rows)
    this_done = sum(1 for r in this_rows if r["completed"] == 1)
    this_pct = int((this_done / this_total) * 100) if this_total else 0

    last_total = len(last_rows)
    last_done = sum(1 for r in last_rows if r["completed"] == 1)
    last_pct = int((last_done / last_total) * 100) if last_total else 0


    return render_template(
        "home.html",
        habits=habits,
       habit_stats=habit_stats,
        month_cells=month_cells,
        today=today,
        current_month=current_month,
        prev_month=prev_month,
        next_month=next_month,
        this_pct=this_pct,
        last_pct=last_pct,

    )


# ---------------- AJAX ----------------
@app.route("/update_completion", methods=["POST"])
@login_required
def update_completion():
    data = request.get_json()
    entry_id = data.get("entry_id")
    completed = data.get("completed")
    if entry_id is None:
        return jsonify(success=False), 400
    db = get_db()
    db.execute("UPDATE habit_entry SET completed=? WHERE id=?", (completed, entry_id))
    db.commit()
    return jsonify(success=True)

@app.route("/update_reason", methods=["POST"])
@login_required
def update_reason():
    data = request.get_json()
    date = data.get("date")
    reason = data.get("reason", "")
    if not date:
        return jsonify(success=False), 400
    db = get_db()
    db.execute("""
        INSERT INTO day_reason (user_id,date,reason)
        VALUES (?,?,?)
        ON CONFLICT(user_id,date)
        DO UPDATE SET reason=excluded.reason
    """, (session["user_id"], date, reason))
    db.commit()
    return jsonify(success=True)

@app.route("/mark_all_done_today", methods=["POST"])
@login_required
def mark_all_done_today():
    db = get_db()
    user_id = session["user_id"]
    today = datetime.date.today().isoformat()

    db.execute("""
        UPDATE habit_entry
        SET completed=1
        WHERE date=?
          AND habit_id IN (SELECT id FROM habit WHERE user_id=?)
    """, (today, user_id))
    db.commit()
    return jsonify(success=True)


# ---------------- Analytics ----------------
@app.route("/analytics")
@login_required
def analytics():
    db = get_db()
    user_id = session["user_id"]
    today = datetime.date.today()

    habits = db.execute(
        "SELECT id, name, frequency FROM habit WHERE user_id=? ORDER BY id DESC",
        (user_id,)
    ).fetchall()

    habit_cards = []
    for h in habits:
        rows = db.execute(
            "SELECT date, completed FROM habit_entry WHERE habit_id=? ORDER BY date ASC",
            (h["id"],)
        ).fetchall()

        total = len(rows)
        done = sum(1 for r in rows if r["completed"] == 1)
        consistency = int((done / total) * 100) if total else 0

        # current streak (ending at latest <= today)
        current_streak = 0
        for r in reversed(rows):
            d = datetime.date.fromisoformat(r["date"])
            if d > today:
                continue
            if r["completed"] == 1:
                current_streak += 1
            else:
                break

        # longest streak
        longest_streak = 0
        run = 0
        for r in rows:
            if r["completed"] == 1:
                run += 1
                longest_streak = max(longest_streak, run)
            else:
                run = 0

        habit_cards.append({
            "name": h["name"],
            "frequency": h["frequency"],
            "total": total,
            "done": done,
            "consistency": consistency,
            "current_streak": current_streak,
            "longest_streak": longest_streak
        })

    # Top reasons on missed days
    missed_days = db.execute("""
        SELECT he.date
        FROM habit_entry he
        JOIN habit h ON h.id = he.habit_id
        WHERE h.user_id=?
        GROUP BY he.date
        HAVING SUM(CASE WHEN he.completed=0 THEN 1 ELSE 0 END) > 0
        ORDER BY he.date DESC
        LIMIT 90
    """, (user_id,)).fetchall()

    reason_counts = {}
    for md in missed_days:
        rr = db.execute(
            "SELECT reason FROM day_reason WHERE user_id=? AND date=?",
            (user_id, md["date"])
        ).fetchone()
        if rr and (rr["reason"] or "").strip():
            txt = rr["reason"].strip()
            reason_counts[txt] = reason_counts.get(txt, 0) + 1

    top_reasons = sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:10]

    return render_template("analytics.html", habit_cards=habit_cards, top_reasons=top_reasons)

# ---------------- Export ----------------
@app.route("/export")
@login_required
def export_page():
    return render_template("export.html")

@app.route("/export_excel")
@login_required
def export_excel():
    db = get_db()
    user_id = session["user_id"]

    rows = db.execute("""
        SELECT
          h.name AS habit_name,
          h.frequency AS frequency,
          he.date AS date,
          he.completed AS completed,
          COALESCE(dr.reason, '') AS day_reason
        FROM habit_entry he
        JOIN habit h ON h.id = he.habit_id
        LEFT JOIN day_reason dr ON dr.user_id = h.user_id AND dr.date = he.date
        WHERE h.user_id=?
        ORDER BY he.date ASC, h.name ASC
    """, (user_id,)).fetchall()

    wb = Workbook()
    ws = wb.active
    ws.title = "Streakly Export"

    ws.append(["Habit", "Frequency", "Date", "Completed", "Day Reason"])
    for r in rows:
        ws.append([
            r["habit_name"],
            r["frequency"],
            r["date"],
            "Yes" if r["completed"] == 1 else "No",
            r["day_reason"]
        ])

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)

    filename = f"streakly_export_{datetime.date.today().isoformat()}.xlsx"
    return send_file(
        bio,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename
    )

if __name__ == "__main__":
 with app.app_context():
        app.run(host="0.0.0.0", port=5000)

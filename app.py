import os, sqlite3, calendar, datetime
from flask import Flask, render_template, request, redirect, url_for, session, g, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# ------------------ App Setup ------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "streakly-secret")

# ------------------ Rate Limiter (Safe) ------------------
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)
limiter.init_app(app)

# ------------------ Database ------------------
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

# ------------------ Auth ------------------
def login_required(f):
    @wraps(f)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapped

# ------------------ Jinja Filter ------------------
@app.template_filter("habit_name")
def habit_name(habit_id):
    db = get_db()
    h = db.execute("SELECT name FROM habit WHERE id=?", (habit_id,)).fetchone()
    return h["name"] if h else "Unknown"

# ------------------ Routes ------------------
@app.route("/", methods=["GET", "POST"])
@app.route("/login", methods=["GET", "POST"])
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

# ------------------ Home ------------------
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
        action = request.form["action"]

        if action == "add":
            name = request.form["habit_name"]
            freq = request.form["frequency"]
            db.execute(
                "INSERT INTO habit (user_id,name,frequency,created_on) VALUES (?,?,?,?)",
                (user_id, name, freq, today.isoformat())
            )
            habit_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

            last_day = calendar.monthrange(current_month.year, current_month.month)[1]
            for d in range(today.day, last_day + 1):
                date = datetime.date(current_month.year, current_month.month, d)
                if freq == "daily" or \
                   (freq == "weekly" and date.weekday() == 5) or \
                   (freq == "monthly" and d == last_day - 1):
                    db.execute(
                        "INSERT INTO habit_entry (habit_id,date) VALUES (?,?)",
                        (habit_id, date.isoformat())
                    )

        if action == "remove":
            hid = request.form["habit_id"]
            db.execute(
                "DELETE FROM habit_entry WHERE habit_id=? AND date>=?",
                (hid, today.isoformat())
            )
            db.execute("DELETE FROM habit WHERE id=?", (hid,))
        db.commit()
        return redirect(request.url)

    habits = db.execute("SELECT * FROM habit WHERE user_id=?", (user_id,)).fetchall()

    # Build calendar
    month_days = []
    last_day = calendar.monthrange(current_month.year, current_month.month)[1]

    for d in range(1, last_day + 1):
        date = datetime.date(current_month.year, current_month.month, d)
        entries = db.execute("""
            SELECT * FROM habit_entry
            WHERE date=? AND habit_id IN
            (SELECT id FROM habit WHERE user_id=?)
        """, (date.isoformat(), user_id)).fetchall()

        reason_row = db.execute(
            "SELECT reason FROM day_reason WHERE user_id=? AND date=?",
            (user_id, date.isoformat())
        ).fetchone()

        month_days.append({
            "date": date,
            "entries": entries,
            "reason": reason_row["reason"] if reason_row else ""
        })

    return render_template(
        "home.html",
        habits=habits,
        month_days=month_days,
        today=today,
        current_month=current_month,
        prev_month=prev_month,
        next_month=next_month,
        consistency=0,
        streak=0
    )

# ------------------ AJAX ------------------
@app.route("/update_completion", methods=["POST"])
@login_required
def update_completion():
    data = request.get_json()
    db = get_db()
    db.execute(
        "UPDATE habit_entry SET completed=? WHERE id=?",
        (data["completed"], data["entry_id"])
    )
    db.commit()
    return jsonify(success=True)

@app.route("/update_reason", methods=["POST"])
@login_required
def update_reason():
    data = request.get_json()
    db = get_db()
    db.execute("""
        INSERT INTO day_reason (user_id,date,reason)
        VALUES (?,?,?)
        ON CONFLICT(user_id,date)
        DO UPDATE SET reason=excluded.reason
    """, (session["user_id"], data["date"], data["reason"]))
    db.commit()
    return jsonify(success=True)

if __name__ == "__main__":
    with app.app_context():
        app.run(host="0.0.0.0", port=5000)

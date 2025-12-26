import os
import sqlite3
import datetime
import io
import csv
from flask import Flask, render_template, request, redirect, url_for, session, g, send_file, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

# ---- App Setup ----
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "supersecretkey")

# ---- Flask-Limiter with optional Redis ----
REDIS_URL = os.environ.get("REDIS_URL", None)

if REDIS_URL:
    try:
        import redis  # make sure 'redis' package is installed
        limiter = Limiter(
            key_func=get_remote_address,
            storage_uri=REDIS_URL,
            default_limits=["200 per day", "50 per hour"]
        )
        limiter.init_app(app)
        print("Using Redis for rate limiting")
    except ImportError:
        print("Redis package not installed. Falling back to in-memory limiter")
        limiter = Limiter(
            key_func=get_remote_address,
            default_limits=["200 per day", "50 per hour"]
        )
        limiter.init_app(app)
else:
    print("REDIS_URL not set. Using in-memory limiter")
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=["200 per day", "50 per hour"]
    )
    limiter.init_app(app)



# ---- Admin Email from environment ----
ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@example.com")

# ---- Database helpers ----
def get_db():
    if "db" not in g:
        g.db = sqlite3.connect("streakly.db")
        g.db.row_factory = sqlite3.Row
    return g.db

def close_db(e=None):
    db = g.pop("db", None)
    if db:
        db.close()

app.teardown_appcontext(close_db)

def init_db():
    db = get_db()
    db.execute('''
        CREATE TABLE IF NOT EXISTS user(
            id INTEGER PRIMARY KEY, username TEXT UNIQUE, password TEXT
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS habit(
            id INTEGER PRIMARY KEY, user_id INTEGER, name TEXT, frequency TEXT
        )
    ''')
    db.execute('''
        CREATE TABLE IF NOT EXISTS habit_entry(
            id INTEGER PRIMARY KEY, habit_id INTEGER, date TEXT, completed INTEGER DEFAULT 0, reason TEXT
        )
    ''')
    db.commit()

# ---- Login Required Decorator ----
def login_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

# ---- Auth Routes ----
@app.route("/register", methods=["GET","POST"])
@limiter.limit("10/hour")
def register():
    if request.method=="POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])
        db = get_db()
        try:
            db.execute("INSERT INTO user(username,password) VALUES(?,?)", (username,password))
            db.commit()
            return redirect(url_for("login"))
        except:
            return "Username exists"
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
@limiter.limit("20/hour")
def login():
    if request.method=="POST":
        username = request.form["username"]
        password = request.form["password"]
        db = get_db()
        user = db.execute("SELECT * FROM user WHERE username=?", (username,)).fetchone()
        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            return redirect(url_for("home"))
        return "Invalid credentials"
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    session.clear()
    return redirect(url_for("login"))

# ---- Home / Calendar ----
@app.route("/", methods=["GET","POST"])
@app.route("/home", methods=["GET","POST"])
@login_required
def home():
    db = get_db()
    user_id = session["user_id"]

    # Add habit
    if request.method=="POST" and request.form.get("habit_name"):
        db.execute("INSERT INTO habit(user_id,name,frequency) VALUES(?,?,?)",
                   (user_id, request.form["habit_name"], request.form["frequency"]))
        db.commit()

    # Save reason
    if request.method=="POST" and request.form.get("reason") and request.form.get("entry_id"):
        db.execute("UPDATE habit_entry SET reason=? WHERE id=?",
                   (request.form["reason"], request.form["entry_id"]))
        db.commit()

    habits = db.execute("SELECT * FROM habit WHERE user_id=?", (user_id,)).fetchall()

    # Calendar setup
    today = datetime.date.today()
    first_day = today.replace(day=1)
    month_days = []
    for i in range(31):
        try:
            day = first_day + datetime.timedelta(days=i)
            if day.month != first_day.month:
                break
            day_entries = []
            for h in habits:
                entry = db.execute("SELECT * FROM habit_entry WHERE habit_id=? AND date=?",
                                   (h["id"], day.isoformat())).fetchone()
                if not entry:
                    add_entry = False
                    if h["frequency"]=="daily":
                        add_entry = True
                    elif h["frequency"]=="weekly" and day.weekday()==5:
                        add_entry = True
                    elif h["frequency"]=="monthly" and day.day==(last_day_of_month(day)-1):
                        add_entry = True
                    if add_entry:
                        db.execute("INSERT INTO habit_entry(habit_id,date) VALUES(?,?)", (h["id"], day.isoformat()))
                        db.commit()
                        entry = db.execute("SELECT * FROM habit_entry WHERE habit_id=? AND date=?",
                                           (h["id"], day.isoformat())).fetchone()
                day_entries.append(entry)
            month_days.append({"date": day, "entries": day_entries})
        except:
            break

    total_entries = sum([len(d["entries"]) for d in month_days])
    completed_entries = sum([sum([1 for e in d["entries"] if e["completed"]==1]) for d in month_days])
    consistency = int((completed_entries/total_entries)*100) if total_entries>0 else 0
    streak = calculate_streak(month_days)

    return render_template("home.html", habits=habits, month_days=month_days, today=today,
                           consistency=consistency, streak=streak)

# ---- Analytics ----
@app.route("/analytics")
@login_required
def analytics():
    db = get_db()
    user_id = session["user_id"]
    habits = db.execute("SELECT * FROM habit WHERE user_id=?", (user_id,)).fetchall()
    analytics_data = []
    for h in habits:
        entries = db.execute("SELECT * FROM habit_entry WHERE habit_id=?", (h["id"],)).fetchall()
        total = len(entries)
        completed = sum([1 for e in entries if e["completed"]==1])
        streak = calculate_habit_streak(entries)
        consistency = int((completed/total)*100) if total>0 else 0
        analytics_data.append({"name":h["name"], "consistency":consistency, "streak":streak})
    return render_template("analytics.html", data=analytics_data)

# ---- CSV Export ----
@app.route("/export_csv")
@login_required
def export_csv():
    db = get_db()
    user_id = session["user_id"]
    habits = db.execute("SELECT * FROM habit WHERE user_id=?", (user_id,)).fetchall()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(["Habit","Date","Completed","Reason"])
    for h in habits:
        entries = db.execute("SELECT * FROM habit_entry WHERE habit_id=?", (h["id"],)).fetchall()
        for e in entries:
            cw.writerow([h["name"], e["date"], e["completed"], e["reason"]])
    output = io.BytesIO()
    output.write(si.getvalue().encode())
    output.seek(0)
    return send_file(output, mimetype="text/csv", as_attachment=True, download_name="streakly.csv")

# ---- AJAX completion update ----
@app.route("/update_completion", methods=["POST"])
@login_required
def update_completion():
    data = request.get_json()
    entry_id = data.get("entry_id")
    completed = data.get("completed")
    db = get_db()
    db.execute("UPDATE habit_entry SET completed=? WHERE id=?", (completed, entry_id))
    db.commit()
    return jsonify({"status":"success"})

# ---- Admin Panel ----
@app.route("/admin")
@login_required
def admin_panel():
    db = get_db()
    user_id = session["user_id"]
    user = db.execute("SELECT * FROM user WHERE id=?", (user_id,)).fetchone()
    if user["username"] != ADMIN_EMAIL:
        return "Unauthorized", 403
    return "Welcome Admin"

# ---- Helper Functions ----
def last_day_of_month(date):
    next_month = date.replace(day=28) + datetime.timedelta(days=4)
    return (next_month - datetime.timedelta(days=next_month.day)).day

def calculate_streak(month_days):
    streak=0
    max_streak=0
    for d in month_days:
        if all(e["completed"]==1 for e in d["entries"]) and d["date"]<=datetime.date.today():
            streak+=1
            max_streak=max(max_streak, streak)
        else:
            streak=0
    return max_streak

def calculate_habit_streak(entries):
    streak=0
    max_streak=0
    for e in entries:
        if e["completed"]==1:
            streak+=1
            max_streak=max(max_streak, streak)
        else:
            streak=0
    return max_streak

# ---- Run App ----
if __name__=="__main__":
    with app.app_context():
        init_db()
    app.run(host="0.0.0.0", port=5000)

import os
import calendar
from datetime import date, datetime, timedelta
from flask import Flask, request, redirect, session, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

# ------------------ APP SETUP ------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")
PORT = int(os.environ.get("PORT", 5000))

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///streakly.db"
).replace("postgres://", "postgresql://")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ------------------ MODELS ------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

class Habit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    name = db.Column(db.String(120))

class HabitLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer)
    user_id = db.Column(db.Integer)
    day = db.Column(db.String(10))
    completed = db.Column(db.Boolean, default=False)

class DayNote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    day = db.Column(db.String(10))
    reason = db.Column(db.String(300))

with app.app_context():
    db.create_all()

# ------------------ HELPERS ------------------
def current_user():
    return User.query.get(session["user_id"]) if "user_id" in session else None

def calculate_streak(logs):
    days = sorted({l.day for l in logs if l.completed})
    streak = best = 0
    prev = None
    for d in days:
        cur = datetime.strptime(d, "%Y-%m-%d").date()
        if prev and cur == prev + timedelta(days=1):
            streak += 1
        else:
            streak = 1
        best = max(best, streak)
        prev = cur
    return streak, best

# ------------------ AUTH ------------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        user = User(
            email=request.form["email"],
            password_hash=generate_password_hash(request.form["password"])
        )
        db.session.add(user)
        db.session.commit()
        return redirect("/login")

    return auth_page("Register", "/register", "Register")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(email=request.form["email"]).first()
        if user and check_password_hash(user.password_hash, request.form["password"]):
            session["user_id"] = user.id
            return redirect("/")
        return "Invalid login"
    return auth_page("Login", "/login", "Login")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

def auth_page(title, action, button):
    return f"""
<html><head>
<script src="https://cdn.tailwindcss.com"></script>
<meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body class="bg-gray-100 flex items-center justify-center min-h-screen">
<div class="bg-white p-6 rounded-xl shadow w-full max-w-sm">
<h1 class="text-2xl font-bold text-center mb-4">Streakly</h1>
<form method="post" action="{action}" class="space-y-3">
<input name="email" placeholder="Email" class="w-full border p-3 rounded">
<input name="password" type="password" placeholder="Password" class="w-full border p-3 rounded">
<button class="w-full bg-blue-600 text-white py-3 rounded">{button}</button>
</form>
<p class="text-center mt-4 text-sm">
<a href="/{'register' if title=='Login' else 'login'}" class="text-blue-600">
{'Create account' if title=='Login' else 'Already have an account?'}
</a>
</p>
</div></body></html>
"""

# ------------------ LAYOUT ------------------
def layout(content, active="home"):
    return f"""
<!DOCTYPE html>
<html>
<head>
<script src="https://cdn.tailwindcss.com"></script>
<meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body class="bg-gray-50 min-h-screen flex">

<!-- Sidebar -->
<aside class="w-48 bg-white shadow hidden sm:block">
  <div class="p-4 font-bold text-xl">Streakly</div>
  <nav class="px-4 space-y-2">
    <a href="/" class="block p-2 rounded {'bg-blue-100' if active=='home' else ''}">Home</a>
    <a href="/analytics" class="block p-2 rounded {'bg-blue-100' if active=='analytics' else ''}">Analytics</a>
    <a href="/logout" class="block p-2 text-red-500">Logout</a>
  </nav>
</aside>

<!-- Main -->
<main class="flex-1 p-4 max-w-4xl mx-auto">
{content}
</main>

</body>
</html>
"""

# ------------------ HOME (CALENDAR) ------------------
@app.route("/")
def home():
    user = current_user()
    if not user:
        return redirect("/login")

    today = date.today()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))

    habits = Habit.query.filter_by(user_id=user.id).all()
    logs = HabitLog.query.filter_by(user_id=user.id).all()
    streak, best = calculate_streak(logs)
    consistency = round(len([l for l in logs if l.completed]) / len(logs) * 100, 1) if logs else 0

    prev_m, prev_y = (12, year-1) if month == 1 else (month-1, year)
    next_m, next_y = (1, year+1) if month == 12 else (month+1, year)

    cal = calendar.monthcalendar(year, month)

    content = f"""
<div class="mb-4">
  <div class="grid grid-cols-3 gap-2 text-center">
    <div class="bg-green-100 p-3 rounded">🔥 {streak}</div>
    <div class="bg-blue-100 p-3 rounded">🏆 {best}</div>
    <div class="bg-yellow-100 p-3 rounded">📈 {consistency}%</div>
  </div>
</div>

<div class="flex justify-between items-center mb-3">
  <a href="/?year={prev_y}&month={prev_m}" class="text-blue-600">← Prev</a>
  <div class="font-bold">{calendar.month_name[month]} {year}</div>
  <a href="/?year={next_y}&month={next_m}" class="text-blue-600">Next →</a>
</div>

<div class="space-y-3">
{"".join(f'''
<div class="bg-white p-3 rounded shadow">
<div class="font-bold mb-2">{day}</div>
{"".join(f'''
<form method="post" action="/toggle" class="flex items-center justify-between mb-1">
<input type="hidden" name="habit_id" value="{h.id}">
<input type="hidden" name="day" value="{year}-{month:02d}-{day:02d}">
<button class="flex-1 text-left px-3 py-3 rounded bg-gray-100">{h.name}</button>
</form>
''' for h in habits)}
</div>
''' for week in cal for day in week if day)}
</div>

<form method="post" action="/add_habit" class="mt-4 flex gap-2">
<input name="name" placeholder="New habit" class="flex-1 border p-3 rounded">
<button class="bg-blue-600 text-white px-4 rounded">Add</button>
</form>

<div class="mt-4">
<a href="/export_csv" class="text-blue-600">Export CSV</a>
</div>
"""
    return layout(content, "home")

# ------------------ ANALYTICS ------------------
@app.route("/analytics")
def analytics():
    user = current_user()
    habits = Habit.query.filter_by(user_id=user.id).all()
    rows = ""

    for h in habits:
        logs = HabitLog.query.filter_by(user_id=user.id, habit_id=h.id).all()
        streak, best = calculate_streak(logs)
        pct = round(len([l for l in logs if l.completed]) / len(logs) * 100, 1) if logs else 0
        rows += f"<tr><td class='p-2'>{h.name}</td><td class='p-2'>{best}</td><td class='p-2'>{pct}%</td></tr>"

    return layout(f"""
<h2 class="text-xl font-bold mb-3">Insights</h2>
<table class="w-full bg-white shadow rounded">
<tr class="font-bold bg-gray-100">
<td class="p-2">Habit</td><td class="p-2">Best Streak</td><td class="p-2">Consistency</td>
</tr>
{rows}
</table>
""", "analytics")

# ------------------ ACTIONS ------------------
@app.route("/add_habit", methods=["POST"])
def add_habit():
    user = current_user()
    db.session.add(Habit(user_id=user.id, name=request.form["name"]))
    db.session.commit()
    return redirect("/")

@app.route("/toggle", methods=["POST"])
def toggle():
    user = current_user()
    log = HabitLog.query.filter_by(
        user_id=user.id,
        habit_id=request.form["habit_id"],
        day=request.form["day"]
    ).first()

    if log:
        log.completed = not log.completed
    else:
        db.session.add(HabitLog(
            user_id=user.id,
            habit_id=request.form["habit_id"],
            day=request.form["day"],
            completed=True
        ))
    db.session.commit()
    return redirect(request.referrer)

@app.route("/export_csv")
def export_csv():
    user = current_user()
    rows = db.session.query(Habit.name, HabitLog.day, HabitLog.completed)\
        .join(Habit, Habit.id == HabitLog.habit_id)\
        .filter(HabitLog.user_id == user.id).all()

    csv = "habit,day,completed\n" + "\n".join(f"{r[0]},{r[1]},{r[2]}" for r in rows)
    return Response(csv, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=streakly.csv"})

# ------------------ RUN ------------------
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)

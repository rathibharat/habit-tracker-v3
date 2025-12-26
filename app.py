from flask import Flask, request, redirect, session, url_for, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, datetime, timedelta
import calendar, os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "streakly-secret")

PORT = int(os.environ.get("PORT", 5000))

app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
    "DATABASE_URL", "sqlite:///streakly.db"
)
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

db = SQLAlchemy(app)

# ================= MODELS =================
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True)
    password_hash = db.Column(db.String(200))

class Habit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    name = db.Column(db.String(120))

class Log(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer)
    habit_id = db.Column(db.Integer)
    day = db.Column(db.String(10))
    completed = db.Column(db.Integer, default=0)
    reason = db.Column(db.String(300))

with app.app_context():
    db.create_all()

# ================= HELPERS =================
def user():
    return User.query.get(session["uid"]) if "uid" in session else None

def streak(habit_id):
    logs = Log.query.filter_by(habit_id=habit_id, completed=1).order_by(Log.day).all()
    s = b = 0
    prev = None
    for l in logs:
        d = datetime.strptime(l.day, "%Y-%m-%d").date()
        s = s + 1 if prev and d == prev + timedelta(days=1) else 1
        b = max(b, s)
        prev = d
    return s, b

# ================= AUTH =================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = User.query.filter_by(email=request.form["email"]).first()
        if u and check_password_hash(u.password_hash, request.form["password"]):
            session["uid"] = u.id
            return redirect("/")
        return "Invalid credentials"

    return """
<!DOCTYPE html>
<html>
<head><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-gradient-to-br from-indigo-100 to-purple-100 min-h-screen flex items-center justify-center">
<div class="bg-white shadow-xl rounded-xl p-8 w-full max-w-sm">
<h1 class="text-3xl font-bold text-center text-indigo-600 mb-2">Streakly</h1>
<p class="text-center text-gray-500 mb-6">Build habits. Stay consistent.</p>
<form method="post" class="space-y-4">
<input name="email" placeholder="Email" class="w-full border p-2 rounded">
<input type="password" name="password" placeholder="Password" class="w-full border p-2 rounded">
<button class="w-full bg-indigo-600 text-white py-2 rounded">Login</button>
</form>
<p class="text-center mt-4 text-sm">
<a href="/register" class="text-indigo-600">Create account</a>
</p>
</div>
</body>
</html>
"""

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        if User.query.filter_by(email=request.form["email"]).first():
            return "User exists"
        u = User(
            email=request.form["email"],
            password_hash=generate_password_hash(request.form["password"]),
        )
        db.session.add(u)
        db.session.commit()
        return redirect("/login")

    return """
<!DOCTYPE html>
<html>
<head><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-gradient-to-br from-indigo-100 to-purple-100 min-h-screen flex items-center justify-center">
<div class="bg-white shadow-xl rounded-xl p-8 w-full max-w-sm">
<h1 class="text-3xl font-bold text-center text-indigo-600 mb-2">Streakly</h1>
<p class="text-center text-gray-500 mb-6">Start your consistency journey</p>
<form method="post" class="space-y-4">
<input name="email" placeholder="Email" class="w-full border p-2 rounded">
<input type="password" name="password" placeholder="Password" class="w-full border p-2 rounded">
<button class="w-full bg-indigo-600 text-white py-2 rounded">Register</button>
</form>
<p class="text-center mt-4 text-sm">
<a href="/login" class="text-indigo-600">Already have an account?</a>
</p>
</div>
</body>
</html>
"""

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")

# ================= DASHBOARD =================
@app.route("/")
def dashboard():
    u = user()
    if not u:
        return redirect("/login")

    today = date.today()
    y = int(request.args.get("year", today.year))
    m = int(request.args.get("month", today.month))

    habits = Habit.query.filter_by(user_id=u.id).all()
    logs = Log.query.filter_by(user_id=u.id).all()

    cal = calendar.monthcalendar(y, m)
    log_map = {}
    for l in logs:
        log_map.setdefault(l.day, []).append(l)

    return f"""
<!DOCTYPE html>
<html>
<head><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-gray-100">
<div class="max-w-7xl mx-auto p-4">

<h1 class="text-3xl font-bold text-indigo-600 mb-4">Streakly</h1>

<div class="flex gap-4 mb-4">
<a href="/?year={y if m>1 else y-1}&month={m-1 if m>1 else 12}" class="px-3 py-1 bg-gray-200 rounded">◀ Prev</a>
<a href="/?year={y if m<12 else y+1}&month={m+1 if m<12 else 1}" class="px-3 py-1 bg-gray-200 rounded">Next ▶</a>
</div>

<form method="post" action="/add_habit" class="mb-4 flex gap-2">
<input name="name" placeholder="New habit" class="border p-2 rounded w-64">
<button class="bg-indigo-600 text-white px-4 rounded">Add</button>
</form>

<div class="grid grid-cols-7 gap-2">
{''.join('<div class="font-semibold text-center">'+d+'</div>' for d in ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'])}
{''.join(self for self in [
''.join(
'<div class="bg-white p-2 rounded shadow">'+
'<div class="font-bold">'+str(day)+'</div>'+
''.join(
f'<form method="post" action="/toggle"><input type="hidden" name="day" value="{y}-{m:02d}-{day:02d}"><input type="hidden" name="habit_id" value="{h.id}"><label class="flex items-center gap-1"><input type="checkbox" name="done" onchange="this.form.submit()"> {h.name}</label></form>'
for h in habits
)+'</div>' if day else '<div></div>'
for day in week
)
for week in cal
])}
</div>

<a href="/export" class="mt-6 inline-block bg-green-600 text-white px-4 py-2 rounded">Export CSV</a>

</div>
</body>
</html>
"""

# ================= ACTIONS =================
@app.route("/add_habit", methods=["POST"])
def add_habit():
    u = user()
    db.session.add(Habit(user_id=u.id, name=request.form["name"]))
    db.session.commit()
    return redirect("/")

@app.route("/toggle", methods=["POST"])
def toggle():
    u = user()
    day = request.form["day"]
    hid = request.form["habit_id"]
    log = Log.query.filter_by(user_id=u.id, habit_id=hid, day=day).first()
    if not log:
        log = Log(user_id=u.id, habit_id=hid, day=day, completed=1)
        db.session.add(log)
    else:
        log.completed = 1 - log.completed
    db.session.commit()
    return redirect("/")

@app.route("/export")
def export():
    u = user()
    rows = db.session.query(Log.day, Habit.name, Log.completed, Log.reason)\
        .join(Habit, Habit.id == Log.habit_id)\
        .filter(Log.user_id == u.id).all()

    csv = "date,habit,completed,reason\n"
    for r in rows:
        csv += f"{r[0]},{r[1]},{r[2]},{r[3] or ''}\n"

    return Response(csv, mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=streakly.csv"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)

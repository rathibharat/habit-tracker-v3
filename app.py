from flask import Flask, request, redirect, url_for, render_template_string, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime, timedelta, date
import csv
import io

app = Flask(__name__)
app.secret_key = "supersecretkey"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///streakly.db"
db = SQLAlchemy(app)

limiter = Limiter(key_func=get_remote_address)
limiter.init_app(app)

# ---------- Database Models ----------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(80), nullable=False)

class Habit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    frequency = db.Column(db.String(10), nullable=False)  # daily, weekly, monthly
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class HabitLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey('habit.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    completed = db.Column(db.Boolean, default=False)
    reason = db.Column(db.String(255), default='')

db.create_all()

# ---------- HTML Templates ----------
BASE_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Streakly</title>
<style>
body {{ font-family: Arial, sans-serif; margin:0; padding:0; background:#f5f5f5; }}
header {{ display:flex; align-items:center; background:#2c3e50; color:white; padding:10px; }}
header h1 {{ margin:0 10px; font-size:24px; }}
.logo {{
    width:40px; height:40px; background:#e74c3c; border-radius:50%;
    display:flex; align-items:center; justify-content:center; color:white; font-weight:bold; font-size:20px;
}}
.container {{ display:flex; flex-direction:row; min-height:90vh; }}
nav {{ width:150px; background:#34495e; color:white; display:flex; flex-direction:column; }}
nav a {{ color:white; padding:10px; text-decoration:none; }}
nav a:hover {{ background:#1abc9c; }}
main {{ flex:1; padding:10px; }}
.calendar {{ display:grid; grid-template-columns: repeat(7, 1fr); gap:5px; }}
.day {{ padding:10px; border-radius:5px; min-height:60px; position:relative; }}
.day-header {{ font-weight:bold; margin-bottom:5px; }}
.completed {{ background:#2ecc71; }}
.partial {{ background:#f1c40f; }}
.incomplete {{ background:#e74c3c; }}
.future {{ background:#bdc3c7; }}
button {{ padding:5px 10px; margin:2px; cursor:pointer; }}
input[type=text] {{ width:90%; padding:3px; }}
form {{ display:flex; flex-direction:column; }}
@media(max-width:600px) {{
    .container {{ flex-direction:column; }}
    nav {{ width:100%; flex-direction:row; overflow-x:auto; }}
    nav a {{ flex:1; text-align:center; }}
}}
</style>
<script>
function toggleHabit(checkbox, habit_id, day) {{
    fetch("/toggle_habit", {{
        method:"POST",
        headers:{{'Content-Type':'application/x-www-form-urlencoded'}},
        body:`habit_id=${{habit_id}}&day=${{day}}`
    }}).then(res=>res.json()).then(data=> {{
        var dayDiv = document.getElementById("day-"+day);
        dayDiv.className="day "+data.color_class;
    }});
}}

function updateReason(habit_day, reason) {{
    fetch("/update_reason", {{
        method:"POST",
        headers:{{'Content-Type':'application/x-www-form-urlencoded'}},
        body:`day=${{habit_day}}&reason=${{encodeURIComponent(reason)}}`
    }});
}}

function gotoToday() {{
    window.location.href = "/";
}}
</script>
</head>
<body>
<header>
<div class="logo">S</div>
<h1>Streakly</h1>
</header>
<div class="container">
<nav>
<a href="/">Home</a>
<a href="/analytics">Analytics</a>
</nav>
<main>
{{ content }}
</main>
</div>
</body>
</html>
"""

LOGIN_HTML = """
<form method="POST">
<h2>Login</h2>
<label>Username:</label>
<input type="text" name="username" required>
<label>Password:</label>
<input type="password" name="password" required>
<button type="submit">Login</button>
<p>Or <a href="/register">Register</a></p>
</form>
"""

REGISTER_HTML = """
<form method="POST">
<h2>Register</h2>
<label>Username:</label>
<input type="text" name="username" required>
<label>Password:</label>
<input type="password" name="password" required>
<button type="submit">Register</button>
<p>Or <a href="/login">Login</a></p>
</form>
"""

# ---------- Helper Functions ----------
def get_user():
    if "user_id" in session:
        return User.query.get(session["user_id"])
    return None

def month_calendar(year, month, user):
    first_day = date(year, month, 1)
    last_day = date(year, month+1, 1) - timedelta(days=1) if month<12 else date(year,12,31)
    cal = []
    day = first_day
    while day <= last_day:
        logs = HabitLog.query.join(Habit).filter(Habit.user_id==user.id, HabitLog.date==day).all()
        total = Habit.query.filter_by(user_id=user.id).count()
        completed = sum(1 for l in logs if l.completed)
        if day>date.today():
            color_class = "future"
        elif total==0:
            color_class="incomplete"
        elif completed==total:
            color_class="completed"
        elif completed>=total/2:
            color_class="partial"
        else:
            color_class="incomplete"
        cal.append({"day":day, "color_class":color_class, "completed":completed, "total":total})
        day += timedelta(days=1)
    return cal

# ---------- Routes ----------
@app.route("/login", methods=["GET","POST"])
def login():
    if request.method=="POST":
        user = User.query.filter_by(username=request.form["username"], password=request.form["password"]).first()
        if user:
            session["user_id"]=user.id
            return redirect(url_for("dashboard"))
    return render_template_string(BASE_HTML, content=LOGIN_HTML)

@app.route("/register", methods=["GET","POST"])
def register():
    if request.method=="POST":
        new_user = User(username=request.form["username"], password=request.form["password"])
        db.session.add(new_user)
        db.session.commit()
        session["user_id"]=new_user.id
        return redirect(url_for("dashboard"))
    return render_template_string(BASE_HTML, content=REGISTER_HTML)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/", methods=["GET","POST"])
def dashboard():
    user = get_user()
    if not user: return redirect(url_for("login"))
    year = int(request.args.get("year", datetime.now().year))
    month = int(request.args.get("month", datetime.now().month))
    if request.method=="POST":
        habit_name = request.form["habit_name"]
        freq = request.form["frequency"]
        new_habit = Habit(name=habit_name, frequency=freq, user_id=user.id)
        db.session.add(new_habit)
        db.session.commit()
    cal = month_calendar(year, month, user)
    cal_html = f"""
    <div>
    <button onclick="window.location.href='/?month={month-1 if month>1 else 12}&year={year if month>1 else year-1}'">Prev</button>
    {year} - {month}
    <button onclick="window.location.href='/?month={month+1 if month<12 else 1}&year={year if month<12 else year+1}'">Next</button>
    <button onclick="gotoToday()">Today</button>
    </div>
    <form method='POST'>
    <input type='text' name='habit_name' placeholder='Add habit'>
    <select name='frequency'>
        <option value='daily'>Daily</option>
        <option value='weekly'>Weekly</option>
        <option value='monthly'>Monthly</option>
    </select>
    <button type='submit'>Add</button>
    </form>
    <div class='calendar'>
    """
    for d in cal:
        cal_html += f"<div id='day-{d['day']}' class='day {d['color_class']}'><div class='day-header'>{d['day'].day}</div>"
        habits = Habit.query.filter_by(user_id=user.id).all()
        for h in habits:
            log = HabitLog.query.filter_by(habit_id=h.id, date=d['day']).first()
            checked = "checked" if log and log.completed else ""
            cal_html += f"<div><input type='checkbox' {checked} onchange='toggleHabit(this,{h.id},\"{d['day']}\")'> {h.name}</div>"
        if any(log.completed==False for log in HabitLog.query.filter(HabitLog.date==d['day']).all()):
            reason = HabitLog.query.filter_by(date=d['day']).first()
            reason_val = reason.reason if reason else ""
            cal_html += f"<input type='text' placeholder='Reason' value='{reason_val}' onblur='updateReason(\"{d['day']}\",this.value)'>"
        cal_html += "</div>"
    cal_html += "</div>"
    return render_template_string(BASE_HTML, content=cal_html)

@app.route("/toggle_habit", methods=["POST"])
def toggle_habit():
    habit_id = int(request.form["habit_id"])
    day = datetime.strptime(request.form["day"], "%Y-%m-%d").date()
    log = HabitLog.query.filter_by(habit_id=habit_id, date=day).first()
    if not log:
        log = HabitLog(habit_id=habit_id, date=day, completed=True)
        db.session.add(log)
    else:
        log.completed = not log.completed
    db.session.commit()
    user = get_user()
    # update color_class
    logs = HabitLog.query.join(Habit).filter(Habit.user_id==user.id, HabitLog.date==day).all()
    total = Habit.query.filter_by(user_id=user.id).count()
    completed = sum(1 for l in logs if l.completed)
    if day>date.today():
        color_class = "future"
    elif total==0:
        color_class="incomplete"
    elif completed==total:
        color_class="completed"
    elif completed>=total/2:
        color_class="partial"
    else:
        color_class="incomplete"
    return {"color_class":color_class}

@app.route("/update_reason", methods=["POST"])
def update_reason():
    day = datetime.strptime(request.form["day"], "%Y-%m-%d").date()
    reason = request.form["reason"]
    log = HabitLog.query.filter_by(date=day).first()
    if log:
        log.reason = reason
        db.session.commit()
    return "OK"

@app.route("/analytics")
def analytics():
    user = get_user()
    if not user: return redirect(url_for("login"))
    habits = Habit.query.filter_by(user_id=user.id).all()
    html = "<h2>Analytics</h2>"
    for h in habits:
        logs = HabitLog.query.filter_by(habit_id=h.id).all()
        streak = best = current = 0
        sorted_logs = sorted(logs, key=lambda x:x.date)
        for l in sorted_logs:
            if l.completed:
                current +=1
                best = max(best, current)
            else:
                current=0
        consistency = (sum(1 for l in logs if l.completed)/len(logs)*100) if logs else 0
        html += f"<p>{h.name}: Best Streak={best}, Consistency={consistency:.1f}%</p>"
    return render_template_string(BASE_HTML, content=html)

@app.route("/export_csv")
def export_csv():
    user = get_user()
    if not user: return redirect(url_for("login"))
    output = io.StringIO()
    writer = csv.writer(output)
    habits = Habit.query.filter_by(user_id=user.id).all()
    writer.writerow(["Habit","Date","Completed","Reason"])
    for h in habits:
        logs = HabitLog.query.filter_by(habit_id=h.id).all()
        for l in logs:
            writer.writerow([h.name,l.date,l.completed,l.reason])
    output.seek(0)
    return send_file(io.BytesIO(output.read().encode()), mimetype="text/csv", as_attachment=True, download_name="streakly.csv")

if __name__=="__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

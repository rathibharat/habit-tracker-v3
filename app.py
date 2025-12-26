from flask import Flask, render_template_string, request, redirect, url_for, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime, timedelta, date
import csv
import io

app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///streakly.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
limiter = Limiter(app, key_func=get_remote_address)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(50), nullable=False)

class Habit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    name = db.Column(db.String(100), nullable=False)
    frequency = db.Column(db.String(10), default='daily')  # daily, weekly, monthly

class HabitLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey('habit.id'))
    log_date = db.Column(db.Date, nullable=False)
    completed = db.Column(db.Boolean, default=False)
    reason = db.Column(db.String(200), default='')

# Ensure database tables are created inside app context
with app.app_context():
    db.create_all()

# Templates
login_template = """
<!DOCTYPE html>
<html>
<head>
<title>Streakly Login</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body { font-family: Arial, sans-serif; background-color:#f5f5f5; margin:0; padding:0;}
.container { max-width: 400px; margin: 100px auto; padding:20px; background:#fff; border-radius:10px; box-shadow:0 0 10px rgba(0,0,0,0.2);}
h2 { text-align:center; color:#4CAF50; }
input[type=text], input[type=password] { width:100%; padding:10px; margin:5px 0 10px 0; border:1px solid #ccc; border-radius:5px; }
button { width:100%; padding:10px; background:#4CAF50; color:white; border:none; border-radius:5px; cursor:pointer; }
button:hover { background:#45a049; }
a { text-decoration:none; display:block; text-align:center; margin-top:10px; color:#555; }
</style>
</head>
<body>
<div class="container">
<h2>🌟 Streakly</h2>
<form method="post">
<input type="text" name="username" placeholder="Username" required>
<input type="password" name="password" placeholder="Password" required>
<button type="submit">Login</button>
</form>
<a href="{{ url_for('register') }}">Register</a>
</div>
</body>
</html>
"""

register_template = """
<!DOCTYPE html>
<html>
<head>
<title>Streakly Register</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body { font-family: Arial, sans-serif; background-color:#f5f5f5; margin:0; padding:0;}
.container { max-width: 400px; margin: 100px auto; padding:20px; background:#fff; border-radius:10px; box-shadow:0 0 10px rgba(0,0,0,0.2);}
h2 { text-align:center; color:#4CAF50; }
input[type=text], input[type=password] { width:100%; padding:10px; margin:5px 0 10px 0; border:1px solid #ccc; border-radius:5px; }
button { width:100%; padding:10px; background:#4CAF50; color:white; border:none; border-radius:5px; cursor:pointer; }
button:hover { background:#45a049; }
a { text-decoration:none; display:block; text-align:center; margin-top:10px; color:#555; }
</style>
</head>
<body>
<div class="container">
<h2>🌟 Streakly</h2>
<form method="post">
<input type="text" name="username" placeholder="Username" required>
<input type="password" name="password" placeholder="Password" required>
<button type="submit">Register</button>
</form>
<a href="{{ url_for('login') }}">Login</a>
</div>
</body>
</html>
"""

dashboard_template = """
<!DOCTYPE html>
<html>
<head>
<title>Streakly Dashboard</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body { font-family: Arial, sans-serif; margin:0; padding:0; background:#f5f5f5; }
.header { background:#4CAF50; color:white; padding:10px 20px; display:flex; align-items:center; }
.header .logo { font-size:24px; font-weight:bold; margin-right:20px; }
.container { display:flex; }
.menu { width:180px; background:#fff; padding:20px; height:100vh; box-shadow:2px 0 5px rgba(0,0,0,0.1); }
.menu a { display:block; margin-bottom:10px; color:#333; text-decoration:none; font-weight:bold; }
.menu a:hover { color:#4CAF50; }
.main { flex:1; padding:20px; }
.calendar { display:grid; grid-template-columns: repeat(7, 1fr); grid-gap:5px; margin-top:10px; }
.day { padding:10px; background:#ddd; border-radius:5px; text-align:center; cursor:pointer; position:relative; }
.day.completed { background:#4CAF50; color:white; }
.day.partial { background:orange; color:white; }
.day.future { background:#ccc; }
.day.failed { background:#f44336; color:white; }
.reason-box { width:100%; margin-top:5px; padding:5px; border-radius:3px; }
button { padding:5px 10px; border:none; border-radius:5px; cursor:pointer; }
button:hover { opacity:0.8; }
</style>
<script>
function toggleHabit(dayId, habitId) {
  fetch("/toggle_habit", {
    method:"POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({day:dayId, habit:habitId})
  }).then(res=>res.json()).then(data=>{
    let dayElem = document.getElementById('day-'+dayId);
    dayElem.className = 'day '+data.status;
  });
}
function navigateMonth(offset) {
  fetch('/navigate_month?offset='+offset).then(res=>res.text()).then(html=>{
    document.open();
    document.write(html);
    document.close();
  });
}
</script>
</head>
<body>
<div class="header">
<div class="logo">🌟</div>
<div style="font-size:24px; font-weight:bold;">Streakly</div>
</div>
<div class="container">
<div class="menu">
<a href="{{ url_for('dashboard') }}">Home</a>
<a href="{{ url_for('analytics') }}">Analytics</a>
<a href="{{ url_for('logout') }}">Logout</a>
</div>
<div class="main">
<h3>Current Month: {{ month_name }} {{ year }}</h3>
<div>
<button onclick="navigateMonth(-1)">Previous</button>
<button onclick="navigateMonth(1)">Next</button>
</div>
<div class="calendar">
{% for day in days %}
<div class="day {{ day.status }}" id="day-{{ day.date }}">
{{ day.day }}
{% if day.reason %}
<textarea class="reason-box" placeholder="Reason">{{ day.reason }}</textarea>
{% endif %}
</div>
{% endfor %}
</div>
</div>
</div>
</body>
</html>
"""

analytics_template = """
<!DOCTYPE html>
<html>
<head>
<title>Streakly Analytics</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body { font-family: Arial, sans-serif; background:#f5f5f5; margin:0; padding:0; }
.header { background:#4CAF50; color:white; padding:10px 20px; display:flex; align-items:center; }
.header .logo { font-size:24px; font-weight:bold; margin-right:20px; }
.container { display:flex; }
.menu { width:180px; background:#fff; padding:20px; height:100vh; box-shadow:2px 0 5px rgba(0,0,0,0.1); }
.menu a { display:block; margin-bottom:10px; color:#333; text-decoration:none; font-weight:bold; }
.menu a:hover { color:#4CAF50; }
.main { flex:1; padding:20px; }
table { width:100%; border-collapse:collapse; margin-top:20px; }
th, td { border:1px solid #ccc; padding:8px; text-align:left; }
</style>
</head>
<body>
<div class="header">
<div class="logo">🌟</div>
<div style="font-size:24px; font-weight:bold;">Streakly</div>
</div>
<div class="container">
<div class="menu">
<a href="{{ url_for('dashboard') }}">Home</a>
<a href="{{ url_for('analytics') }}">Analytics</a>
<a href="{{ url_for('logout') }}">Logout</a>
</div>
<div class="main">
<h3>Analytics</h3>
<table>
<tr><th>Habit</th><th>Completion Rate</th><th>Most Common Reason</th></tr>
{% for habit in analytics %}
<tr>
<td>{{ habit.name }}</td>
<td>{{ habit.completion }}%</td>
<td>{{ habit.reason or 'N/A' }}</td>
</tr>
{% endfor %}
</table>
</div>
</div>
</body>
</html>
"""

# Helper functions
def get_current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

# Routes
@app.route('/', methods=['GET','POST'])
def login():
    if request.method=='POST':
        u = request.form['username']
        p = request.form['password']
        user = User.query.filter_by(username=u, password=p).first()
        if user:
            session['user_id'] = user.id
            return redirect(url_for('dashboard'))
    return render_template_string(login_template)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        u = request.form['username']
        p = request.form['password']
        if not User.query.filter_by(username=u).first():
            db.session.add(User(username=u,password=p))
            db.session.commit()
            return redirect(url_for('login'))
    return render_template_string(register_template)

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    return redirect(url_for('login'))

@app.route('/dashboard')
def dashboard():
    user = get_current_user()
    if not user: return redirect(url_for('login'))
    # Build calendar for current month
    today = date.today()
    month_start = date(today.year, today.month, 1)
    next_month = month_start.replace(day=28)+timedelta(days=4)
    month_end = next_month - timedelta(days=next_month.day)
    days=[]
    habits = Habit.query.filter_by(user_id=user.id).all()
    for i in range((month_end-month_start).days+1):
        d = month_start+timedelta(days=i)
        logs = HabitLog.query.join(Habit).filter(Habit.user_id==user.id,HabitLog.log_date==d).all()
        completed_count = sum([1 for log in logs if log.completed])
        status='future'
        if d<today:
            if completed_count==0: status='failed'
            elif completed_count==len(habits): status='completed'
            else: status='partial'
        elif d==today:
            if completed_count==len(habits): status='completed'
            elif completed_count>0: status='partial'
            else: status='future'
        reason = None
        for log in logs:
            if log.reason: reason=log.reason
        days.append({'day':d.day,'date':d.isoformat(),'status':status,'reason':reason})
    return render_template_string(dashboard_template, days=days, month_name=today.strftime('%B'), year=today.year)

@app.route('/analytics')
def analytics():
    user = get_current_user()
    if not user: return redirect(url_for('login'))
    analytics=[]
    habits = Habit.query.filter_by(user_id=user.id).all()
    for h in habits:
        logs = HabitLog.query.filter_by(habit_id=h.id).all()
        total=len(logs)
        completed=sum([1 for l in logs if l.completed])
        reasons={}
        for l in logs:
            if l.reason: reasons[l.reason]=reasons.get(l.reason,0)+1
        most_common = max(reasons,key=reasons.get) if reasons else None
        completion = int((completed/total)*100) if total>0 else 0
        analytics.append({'name':h.name,'completion':completion,'reason':most_common})
    return render_template_string(analytics_template, analytics=analytics)

# Start app
if __name__=='__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

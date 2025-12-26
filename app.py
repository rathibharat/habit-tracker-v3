from flask import Flask, request, redirect, url_for, session, jsonify
from flask import render_template_string
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime, timedelta, date
import calendar
import csv
from io import StringIO

app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///streakly.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
limiter = Limiter(key_func=get_remote_address)
limiter.init_app(app)

# -------------------
# Database Models
# -------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

class Habit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name = db.Column(db.String(120), nullable=False)
    frequency = db.Column(db.String(10), default='daily')  # daily, weekly, monthly

class HabitLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey('habit.id'), nullable=False)
    date = db.Column(db.Date, nullable=False)
    completed = db.Column(db.Boolean, default=False)
    reason = db.Column(db.String(200), default='')

with app.app_context():
    db.create_all()

# -------------------
# Helper Functions
# -------------------
def get_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

def get_habits(user):
    return Habit.query.filter_by(user_id=user.id).all()

def get_habit_logs(user, month, year):
    habits = get_habits(user)
    logs = {}
    for habit in habits:
        habit_entries = HabitLog.query.filter_by(habit_id=habit.id).all()
        for entry in habit_entries:
            if entry.date.year == year and entry.date.month == month:
                if entry.date not in logs:
                    logs[entry.date] = []
                logs[entry.date].append(entry)
    return logs

def calculate_streaks(user):
    habits = get_habits(user)
    if not habits:
        return 0, 0, 0.0
    today = date.today()
    streak = 0
    best_streak = 0
    consistency = 0.0
    habit_logs = HabitLog.query.filter(HabitLog.habit_id.in_([h.id for h in habits])).all()
    day_counts = {}
    for log in habit_logs:
        day_counts[log.date] = day_counts.get(log.date, 0) + (1 if log.completed else 0)
    sorted_days = sorted(day_counts.keys(), reverse=True)
    for d in sorted_days:
        if day_counts[d] == len(habits):
            streak += 1
        else:
            break
    best_streak = max([streak, best_streak])
    completed_days = sum(1 for c in day_counts.values() if c == len(habits))
    consistency = (completed_days / len(day_counts)) * 100 if day_counts else 0
    return streak, best_streak, round(consistency, 2)

def add_automatic_habits():
    today = date.today()
    users = User.query.all()
    for user in users:
        habits = get_habits(user)
        for habit in habits:
            if habit.frequency == 'weekly' and today.weekday() == 6:
                existing = HabitLog.query.filter_by(habit_id=habit.id, date=today).first()
                if not existing:
                    db.session.add(HabitLog(habit_id=habit.id, date=today))
            if habit.frequency == 'monthly' and today.day == calendar.monthrange(today.year, today.month)[1]:
                existing = HabitLog.query.filter_by(habit_id=habit.id, date=today).first()
                if not existing:
                    db.session.add(HabitLog(habit_id=habit.id, date=today))
    db.session.commit()

# -------------------
# Routes
# -------------------
@app.route('/')
def home():
    user = get_user()
    if not user:
        return redirect(url_for('login'))
    month = request.args.get('month', default=date.today().month, type=int)
    year = request.args.get('year', default=date.today().year, type=int)
    add_automatic_habits()
    habits = get_habits(user)
    logs = get_habit_logs(user, month, year)
    streak, best_streak, consistency = calculate_streaks(user)
    today = date.today()
    return render_template_string(TEMPLATE_HOME, user=user, habits=habits, logs=logs, streak=streak, best_streak=best_streak, consistency=consistency, month=month, year=year, today=today)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.password == request.form['password']:
            session['user_id'] = user.id
            return redirect(url_for('home'))
    return render_template_string(TEMPLATE_LOGIN)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        if User.query.filter_by(username=request.form['username']).first():
            return "Username already exists"
        user = User(username=request.form['username'], password=request.form['password'])
        db.session.add(user)
        db.session.commit()
        session['user_id'] = user.id
        return redirect(url_for('home'))
    return render_template_string(TEMPLATE_REGISTER)

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/toggle_habit', methods=['POST'])
def toggle_habit():
    habit_id = int(request.form['habit_id'])
    day = datetime.strptime(request.form['day'], '%Y-%m-%d').date()
    entry = HabitLog.query.filter_by(habit_id=habit_id, date=day).first()
    if entry:
        entry.completed = not entry.completed
    else:
        entry = HabitLog(habit_id=habit_id, date=day, completed=True)
        db.session.add(entry)
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/update_reason', methods=['POST'])
def update_reason():
    day = datetime.strptime(request.form['day'], '%Y-%m-%d').date()
    reason = request.form['reason']
    user = get_user()
    habits = get_habits(user)
    for habit in habits:
        log = HabitLog.query.filter_by(habit_id=habit.id, date=day).first()
        if log:
            log.reason = reason
    db.session.commit()
    return jsonify({'status': 'success'})

@app.route('/add_habit', methods=['POST'])
def add_habit():
    name = request.form['name']
    frequency = request.form['frequency']
    user = get_user()
    habit = Habit(name=name, user_id=user.id, frequency=frequency)
    db.session.add(habit)
    db.session.commit()
    return redirect(url_for('home'))

@app.route('/remove_habit/<int:habit_id>')
def remove_habit(habit_id):
    habit = Habit.query.get(habit_id)
    if habit:
        db.session.delete(habit)
        db.session.commit()
    return redirect(url_for('home'))

@app.route('/export_csv')
def export_csv():
    user = get_user()
    habits = get_habits(user)
    si = StringIO()
    writer = csv.writer(si)
    writer.writerow(['Habit', 'Date', 'Completed', 'Reason'])
    for habit in habits:
        logs = HabitLog.query.filter_by(habit_id=habit.id).all()
        for log in logs:
            writer.writerow([habit.name, log.date, log.completed, log.reason])
    output = si.getvalue()
    return app.response_class(
        output,
        mimetype='text/csv',
        headers={'Content-Disposition':'attachment;filename=streakly.csv'}
    )

# -------------------
# Templates
# -------------------
TEMPLATE_LOGIN = '''
<!DOCTYPE html>
<html>
<head><title>Streakly Login</title>
<style>
body { font-family: Arial; display: flex; justify-content:center; align-items:center; height:100vh; background:#f0f0f0; }
form { background:white; padding:2em; border-radius:10px; box-shadow:0px 0px 10px rgba(0,0,0,0.2); width:300px; }
input { display:block; margin:0.5em 0; padding:0.5em; width:100%; }
button { padding:0.5em; width:100%; background:#28a745; color:white; border:none; border-radius:5px; }
h1 { text-align:center; color:#333; }
a { display:block; text-align:center; margin-top:1em; }
</style>
</head>
<body>
<form method="post">
<h1>Streakly</h1>
<input name="username" placeholder="Username" required>
<input name="password" type="password" placeholder="Password" required>
<button type="submit">Login</button>
<a href="{{ url_for('register') }}">Register</a>
</form>
</body>
</html>
'''

TEMPLATE_REGISTER = '''
<!DOCTYPE html>
<html>
<head><title>Streakly Register</title></head>
<body>
<h1>Register</h1>
<form method="post">
<input name="username" placeholder="Username" required>
<input name="password" type="password" placeholder="Password" required>
<button type="submit">Register</button>
</form>
</body>
</html>
'''

TEMPLATE_HOME = '''
<!DOCTYPE html>
<html>
<head>
<title>Streakly</title>
<style>
body { font-family: Arial; margin:0; padding:0; background:#f0f0f0; }
.header { background:#28a745; color:white; padding:1em; display:flex; align-items:center; }
.logo { width:30px; height:30px; background:#fff; border-radius:50%; margin-right:1em; display:inline-block; }
.container { display:flex; }
.menu { width:150px; background:#333; color:white; min-height:100vh; padding-top:2em; }
.menu a { color:white; display:block; padding:1em; text-decoration:none; }
.menu a:hover { background:#444; }
.content { flex:1; padding:2em; }
.cell { padding:0.5em; text-align:center; border-radius:5px; margin-bottom:5px; }
.green { background:#28a745; color:white; }
.yellow { background:#ffc107; color:black; }
.red { background:#dc3545; color:white; }
.gray { background:#ccc; color:white; }
.calendar { display:grid; grid-template-columns:repeat(7,1fr); gap:5px; }
</style>
</head>
<body>
<div class="header">
<div class="logo"></div>
<h1>Streakly</h1>
</div>
<div class="container">
<div class="menu">
<a href="{{ url_for('home') }}">Home</a>
<a href="{{ url_for('export_csv') }}">Export CSV</a>
<a href="{{ url_for('logout') }}">Logout</a>
</div>
<div class="content">
<h2>Current Streak: {{ streak }} | Best Streak: {{ best_streak }} | Consistency: {{ consistency }}%</h2>
<form method="post" action="{{ url_for('add_habit') }}">
<input name="name" placeholder="Habit Name" required>
<select name="frequency">
<option value="daily">Daily</option>
<option value="weekly">Weekly</option>
<option value="monthly">Monthly</option>
</select>
<button type="submit">Add Habit</button>
</form>
<div>
<button onclick="goToday()">Go to Today</button>
<button onclick="prevMonth()">Previous</button>
<span id="monthYear"></span>
<button onclick="nextMonth()">Next</button>
</div>
<div class="calendar" id="calendar"></div>
</div>
</div>
<script>
let currentMonth = {{ month }};
let currentYear = {{ year }};
let today = new Date("{{ today }}");

function updateMonthYear() {
    const monthNames = ["January","February","March","April","May","June","July","August","September","October","November","December"];
    document.getElementById('monthYear').innerText = monthNames[currentMonth-1] + ' ' + currentYear;
}

function goToday() {
    currentMonth = today.getMonth()+1;
    currentYear = today.getFullYear();
    renderCalendar();
}

function prevMonth() {
    currentMonth--;
    if(currentMonth<1){ currentMonth=12; currentYear--; }
    renderCalendar();
}

function nextMonth() {
    currentMonth++;
    if(currentMonth>12){ currentMonth=1; currentYear++; }
    renderCalendar();
}

function renderCalendar() {
    updateMonthYear();
    const calendarEl = document.getElementById('calendar');
    calendarEl.innerHTML='';
    const daysInMonth = new Date(currentYear, currentMonth, 0).getDate();
    const startDay = new Date(currentYear,currentMonth-1,1).getDay();
    for(let i=0;i<startDay;i++){ let empty = document.createElement('div'); calendarEl.appendChild(empty);}
    {% for day in range(1,32) %}
    for(let day=1; day<=daysInMonth; day++){
        let cell = document.createElement('div');
        cell.className='cell';
        let cellDate = new Date(currentYear,currentMonth-1,day);
        cell.innerHTML=day;
        if(cellDate>today){
            cell.classList.add('gray');
        } else {
            // Determine color based on habit completion
            {% for d, entries in logs.items() %}
            let logDate = new Date("{{ d }}");
            if(logDate.getFullYear()===cellDate.getFullYear() && logDate.getMonth()===cellDate.getMonth() && logDate.getDate()===cellDate.getDate()){
                let completed = {{ entries|length }};
                if(completed==={{ habits|length }}){
                    cell.classList.add('green');
                } else if(completed>0){
                    cell.classList.add('yellow');
                } else {
                    cell.classList.add('red');
                }
            }
            {% endfor %}
        }
        calendarEl.appendChild(cell);
    }
}
renderCalendar();
</script>
</body>
</html>
'''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

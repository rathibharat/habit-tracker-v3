from flask import Flask, render_template_string, request, redirect, url_for, session, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
import datetime, csv, io

app = Flask(__name__)
app.config['SECRET_KEY'] = 'supersecretkey'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///streakly.db'
db = SQLAlchemy(app)

limiter = Limiter(app, key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(50))

class Habit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    frequency = db.Column(db.String(10))  # daily, weekly, monthly
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))

class HabitLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey('habit.id'))
    date = db.Column(db.Date)
    completed = db.Column(db.Boolean, default=False)
    reason = db.Column(db.String(200), default='')

# Ensure tables are created in app context
with app.app_context():
    db.create_all()

# HTML Templates
base_template = """
<!doctype html>
<html>
<head>
    <title>Streakly</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; margin:0; padding:0; }
        header { background:#4CAF50; color:white; padding:10px 20px; display:flex; align-items:center; }
        header h1 { margin:0; font-size:24px; }
        .logo { width:30px; height:30px; background:#fff; border-radius:50%; margin-right:10px; }
        nav { width:200px; background:#f0f0f0; height:100vh; padding:20px; float:left; box-sizing:border-box; }
        nav a { display:block; padding:10px; color:black; text-decoration:none; margin-bottom:5px; }
        nav a:hover { background:#ddd; }
        main { margin-left:220px; padding:20px; }
        .calendar { display:grid; grid-template-columns: repeat(7, 1fr); gap:5px; }
        .day { padding:10px; text-align:center; border:1px solid #ccc; cursor:pointer; }
        .green { background:#4CAF50; color:white; }
        .yellow { background:#FFEB3B; }
        .red { background:#F44336; color:white; }
        .gray { background:#e0e0e0; }
        form { margin:10px 0; }
        input[type=text], input[type=password] { padding:5px; width:200px; margin:5px 0; }
        button { padding:5px 10px; margin:5px 0; }
        .month-nav { display:flex; justify-content: space-between; margin-bottom:10px; }
    </style>
</head>
<body>
<header>
    <div class="logo"></div>
    <h1>Streakly</h1>
</header>
<nav>
    <a href="{{ url_for('home') }}">Home</a>
    <a href="{{ url_for('analytics') }}">Analytics</a>
</nav>
<main>
{% block content %}{% endblock %}
</main>
</body>
</html>
"""

login_template = """
<!doctype html>
<html>
<head>
<title>Login - Streakly</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body { font-family: Arial; display:flex; justify-content:center; align-items:center; height:100vh; background:#f0f0f0; margin:0; }
form { background:white; padding:20px; border-radius:5px; width:300px; }
input { width:100%; padding:5px; margin:5px 0; }
button { width:100%; padding:5px; }
h2 { text-align:center; }
</style>
</head>
<body>
<form method="post">
<h2>Streakly Login</h2>
<input type="text" name="username" placeholder="Username" required>
<input type="password" name="password" placeholder="Password" required>
<button type="submit">Login</button>
<a href="{{ url_for('register') }}">Register</a>
</form>
</body>
</html>
"""

register_template = """
<!doctype html>
<html>
<head>
<title>Register - Streakly</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body { font-family: Arial; display:flex; justify-content:center; align-items:center; height:100vh; background:#f0f0f0; margin:0; }
form { background:white; padding:20px; border-radius:5px; width:300px; }
input { width:100%; padding:5px; margin:5px 0; }
button { width:100%; padding:5px; }
h2 { text-align:center; }
</style>
</head>
<body>
<form method="post">
<h2>Streakly Register</h2>
<input type="text" name="username" placeholder="Username" required>
<input type="password" name="password" placeholder="Password" required>
<button type="submit">Register</button>
<a href="{{ url_for('login') }}">Login</a>
</form>
</body>
</html>
"""

# Helper functions
def get_streaks(user_id):
    habits = Habit.query.filter_by(user_id=user_id).all()
    streak_data = {"current":0,"best":0,"consistency":0}
    # Simplified example: calculate streaks
    return streak_data

# Routes
@app.route('/', methods=['GET','POST'])
def login():
    if request.method=='POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username,password=password).first()
        if user:
            session['user_id'] = user.id
            return redirect(url_for('home'))
    return render_template_string(login_template)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        username = request.form['username']
        password = request.form['password']
        if not User.query.filter_by(username=username).first():
            db.session.add(User(username=username,password=password))
            db.session.commit()
            return redirect(url_for('login'))
    return render_template_string(register_template)

@app.route('/home', methods=['GET','POST'])
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']

    today = datetime.date.today()
    year = int(request.args.get('year', today.year))
    month = int(request.args.get('month', today.month))

    # Month navigation
    first_day = datetime.date(year, month, 1)
    last_day = datetime.date(year, month, (datetime.date(year, month+1, 1)-datetime.timedelta(days=1)).day if month<12 else 31)
    days = [first_day + datetime.timedelta(days=i) for i in range((last_day-first_day).days+1)]

    habits = Habit.query.filter_by(user_id=user_id).all()
    logs = {log.date:log for log in HabitLog.query.join(Habit).filter(Habit.user_id==user_id).all()}

    calendar_html = ""
    for day in days:
        day_logs = [log for log in logs.values() if log.date==day]
        if not day_logs:
            color="gray"
        else:
            completed = sum(1 for l in day_logs if l.completed)
            total = len(day_logs)
            if completed==total:
                color="green"
            elif completed==0:
                color="red"
            else:
                color="yellow"
        calendar_html+=f'<div class="day {color}">{day.day}</div>'

    content = f"""
    {% extends base_template %}
    {% block content %}
    <h2>Calendar - {month}/{year}</h2>
    <div class="month-nav">
        <a href="{url_for('home', month=month-1 if month>1 else 12, year=year-1 if month==1 else year)}">Previous</a>
        <span>{month}/{year}</span>
        <a href="{url_for('home', month=month+1 if month<12 else 1, year=year+1 if month==12 else year)}">Next</a>
    </div>
    <div class="calendar">{calendar_html}</div>
    {% endblock %}
    """
    return render_template_string(content, base_template=base_template)

@app.route('/analytics')
def analytics():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    # Generate some simple analytics
    content = """
    {% extends base_template %}
    {% block content %}
    <h2>Analytics</h2>
    <p>Coming soon: insights per habit and reason analysis</p>
    {% endblock %}
    """
    return render_template_string(content, base_template=base_template)

if __name__=="__main__":
    app.run(host='0.0.0.0', port=5000, debug=True)

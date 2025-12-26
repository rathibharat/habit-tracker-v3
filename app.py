from flask import Flask, request, redirect, url_for, render_template_string, session, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from datetime import date, timedelta, datetime
import csv
import io

app = Flask(__name__)
app.secret_key = 'supersecret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///streakly.db'
db = SQLAlchemy(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

class Habit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    frequency = db.Column(db.String(20), default='daily')  # daily, weekly, monthly

class HabitLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey('habit.id'))
    date = db.Column(db.Date, default=date.today)
    done = db.Column(db.Boolean, default=False)
    reason = db.Column(db.String(255), default='')

with app.app_context():
    db.create_all()

base_template = '''
<!doctype html>
<html>
<head>
<title>Streakly</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
body { font-family: Arial, sans-serif; margin:0; padding:0; }
header { background:#4CAF50; color:white; padding:10px; display:flex; align-items:center; }
header .logo { width:40px; height:40px; background:white; border-radius:50%; margin-right:10px; }
nav { background:#f2f2f2; padding:10px; width:180px; float:left; min-height:100vh; }
nav a { display:block; margin:5px 0; color:#333; text-decoration:none; }
.content { margin-left:190px; padding:10px; }
.calendar td { width:40px; height:40px; text-align:center; }
.green { background:green; color:white; }
.yellow { background:orange; color:white; }
.red { background:red; color:white; }
.gray { background:#ddd; }
button { padding:5px 10px; margin:2px; }
</style>
</head>
<body>
<header><div class="logo"></div><h2>Streakly</h2></header>
<nav>
<a href="/">Home</a>
<a href="/analytics">Analytics</a>
{% if 'user_id' in session %}<a href="/logout">Logout</a>{% endif %}
</nav>
<div class="content">
{% block content %}{% endblock %}
</div>
</body>
</html>
'''

# Utility
def current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

# Routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            return 'User exists'
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        return redirect('/login')
    return render_template_string(base_template + '''
{% block content %}
<h3>Register</h3>
<form method="post">
<input name="username" placeholder="Username" required><br>
<input type="password" name="password" placeholder="Password" required><br>
<button type="submit">Register</button>
</form>
{% endblock %}
''')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username'], password=request.form['password']).first()
        if user:
            session['user_id'] = user.id
            return redirect('/')
        return 'Invalid'
    return render_template_string(base_template + '''
{% block content %}
<h3>Login</h3>
<form method="post">
<input name="username" placeholder="Username" required><br>
<input type="password" name="password" placeholder="Password" required><br>
<button type="submit">Login</button>
</form>
{% endblock %}
''')

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/', methods=['GET', 'POST'])
def home():
    user = current_user()
    if not user:
        return redirect('/login')
    if request.method == 'POST':
        habit_name = request.form['habit_name']
        freq = request.form['frequency']
        habit = Habit(name=habit_name, user_id=user.id, frequency=freq)
        db.session.add(habit)
        db.session.commit()
    habits = Habit.query.filter_by(user_id=user.id).all()
    today = date.today()
    return render_template_string(base_template + '''
{% block content %}
<h3>Today's Habits</h3>
<form method="post">
<input name="habit_name" placeholder="Habit name" required>
<select name="frequency"><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select>
<button type="submit">Add Habit</button>
</form>
<ul>
{% for habit in habits %}
<li>{{habit.name}} ({{habit.frequency}})</li>
{% endfor %}
</ul>
{% endblock %}
''', habits=habits)

@app.route('/analytics')
def analytics():
    user = current_user()
    if not user:
        return redirect('/login')
    habits = Habit.query.filter_by(user_id=user.id).all()
    return render_template_string(base_template + '''
{% block content %}
<h3>Analytics</h3>
<ul>
{% for habit in habits %}
<li>{{habit.name}}</li>
{% endfor %}
</ul>
{% endblock %}
''', habits=habits)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

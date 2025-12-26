# streakly_app_final.py
from flask import Flask, render_template_string, request, redirect, url_for, session, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date, timedelta
import io, csv, json

app = Flask(__name__)
app.secret_key = 'streakly-secret'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///streakly.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Initialize Limiter with default in-memory storage
limiter = Limiter(app, key_func=get_remote_address)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Habit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    frequency = db.Column(db.String(20), default='daily') # daily, weekly, monthly
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)

class HabitLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey('habit.id'), nullable=False)
    log_date = db.Column(db.Date, nullable=False)
    completed = db.Column(db.Boolean, default=False)
    reason = db.Column(db.String(500), nullable=True)

with app.app_context():
    db.create_all()

# Templates
base_template = '''
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Streakly</title>
<style>
body {font-family: Arial, sans-serif; margin:0; padding:0; background:#f5f5f5;}
.header {background:#4CAF50;color:white;padding:15px;display:flex;align-items:center;}
.logo {width:40px;height:40px;background:#fff;margin-right:10px;border-radius:5px;text-align:center;line-height:40px;color:#4CAF50;font-weight:bold;}
nav {width:200px; background:#333; color:white; height:100vh; position:fixed; top:0; left:0; display:flex; flex-direction:column; padding-top:60px;}
nav a {color:white; text-decoration:none; padding:10px 20px;}
nav a:hover {background:#444;}
.main {margin-left:200px; padding:20px;}
.calendar {display:grid; grid-template-columns: repeat(7,1fr); grid-gap:5px;}
.day {padding:15px; text-align:center; border-radius:5px; cursor:pointer;}
.green {background:#4CAF50;color:white;}
.yellow {background:#FFC107;color:black;}
.red {background:#F44336;color:white;}
.gray {background:#ccc;color:black;}
button {padding:8px 12px;margin:5px; cursor:pointer;}
input, select {padding:5px;margin:5px;width:100%;}
form {margin-bottom:20px;}
@media(max-width:600px){.main{margin-left:0;}}
</style>
<script src="https://code.jquery.com/jquery-3.6.0.min.js"></script>
</head>
<body>
<div class="header"><div class="logo">S</div><h2>Streakly</h2></div>
{% if session.get('user_id') %}
<nav>
<a href="{{ url_for('home') }}">Home</a>
<a href="{{ url_for('analytics') }}">Analytics</a>
<a href="{{ url_for('logout') }}">Logout</a>
</nav>
{% endif %}
<div class="main">{% block content %}{% endblock %}</div>
</body>
</html>
'''

# Routes
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('home'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method=='POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session['user_id'] = user.id
            return redirect(url_for('home'))
        else:
            return render_template_string(base_template + '<p>Invalid credentials</p>{% block content %}{% endblock %}')
    return render_template_string(base_template + '''
{% block content %}
<h3>Login</h3>
<form method="post">
<input type="text" name="username" placeholder="Username" required>
<input type="password" name="password" placeholder="Password" required>
<button type="submit">Login</button>
<p>New user? <a href="{{ url_for('register') }}">Register here</a></p>
</form>
{% endblock %}
''')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method=='POST':
        username = request.form['username']
        password = generate_password_hash(request.form['password'])
        if User.query.filter_by(username=username).first():
            return render_template_string(base_template + '<p>Username exists!</p>{% block content %}{% endblock %}')
        user = User(username=username,password=password)
        db.session.add(user)
        db.session.commit()
        session['user_id'] = user.id
        return redirect(url_for('home'))
    return render_template_string(base_template + '''
{% block content %}
<h3>Register</h3>
<form method="post">
<input type="text" name="username" placeholder="Username" required>
<input type="password" name="password" placeholder="Password" required>
<button type="submit">Register</button>
<p>Already registered? <a href="{{ url_for('login') }}">Login</a></p>
</form>
{% endblock %}
''')

@app.route('/logout')
def logout():
    session.pop('user_id',None)
    return redirect(url_for('login'))

@app.route('/home')
def home():
    if 'user_id' not in session:
        return redirect(url_for('login'))
    user_id = session['user_id']
    habits = Habit.query.filter_by(user_id=user_id).all()
    today = date.today()
    return render_template_string(base_template + '''
{% block content %}
<h3>Home</h3>
<button onclick="goToToday()">Go to Today</button>
<div id="calendar"></div>
<h4>Add Habit</h4>
<form id="addHabitForm">
<input type="text" name="name" placeholder="Habit name" required>
<select name="frequency"><option value="daily">Daily</option><option value="weekly">Weekly</option><option value="monthly">Monthly</option></select>
<button type="submit">Add</button>
</form>
<script>
function goToToday(){alert('Go to today logic here');}
$('#addHabitForm').submit(function(e){e.preventDefault();$.post('/add_habit',$(this).serialize(),function(){location.reload();});});
</script>
{% endblock %}
''', habits=habits, today=today)

@app.route('/add_habit', methods=['POST'])
def add_habit():
    if 'user_id' not in session: return '',401
    name = request.form['name']
    freq = request.form['frequency']
    habit = Habit(name=name, frequency=freq, user_id=session['user_id'])
    db.session.add(habit)
    db.session.commit()
    return '',200

@app.route('/analytics')
def analytics():
    return render_template_string(base_template + '{% block content %}<h3>Analytics Dashboard</h3>{% endblock %}')

if __name__=='__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

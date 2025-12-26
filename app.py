from flask import Flask, render_template_string, request, redirect, url_for, send_file, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from datetime import datetime, timedelta
import csv
from io import StringIO

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///streakly.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.secret_key = 'your_secret_key'

# Initialize limiter correctly
limiter = Limiter(app=app, key_func=get_remote_address)

db = SQLAlchemy(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)

class Habit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    name = db.Column(db.String(100), nullable=False)
    type = db.Column(db.String(10), default='daily')  # daily / weekly / monthly

class HabitEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey('habit.id'))
    date = db.Column(db.Date, nullable=False)
    completed = db.Column(db.Boolean, default=False)
    reason = db.Column(db.String(250))

with app.app_context():
    db.create_all()

# Base template
base_template = """
<!DOCTYPE html>
<html lang='en'>
<head>
<meta name='viewport' content='width=device-width, initial-scale=1'>
<title>Streakly</title>
<style>
body{font-family:Arial,sans-serif;margin:0;padding:0;background:#f5f5f5}
header{background:#4CAF50;color:white;padding:10px;text-align:center;display:flex;align-items:center;}
.logo{width:40px;height:40px;background:#fff;border-radius:50%;margin-right:10px;display:inline-block;}
nav{background:#333;color:white;padding:15px;height:100vh;position:fixed;width:200px;}
nav a{color:white;display:block;margin:10px 0;text-decoration:none;}
main{margin-left:210px;padding:20px;}
button{padding:8px 12px;margin:5px;background:#4CAF50;color:white;border:none;border-radius:4px;cursor:pointer;}
input{padding:6px;margin:5px;border-radius:4px;border:1px solid #ccc;}
.calendar-cell{width:40px;height:40px;display:inline-block;margin:2px;text-align:center;line-height:40px;color:white;border-radius:4px;cursor:pointer;}
.green{background:#4CAF50;}
.yellow{background:#FF9800;}
.red{background:#F44336;}
.gray{background:#BDBDBD;}
@media(max-width:600px){main{margin-left:0;padding:10px;} nav{width:100%;height:auto;position:relative;}}
</style>
<script>
function toggleHabit(entryId){
 fetch('/toggle_habit/' + entryId, {method:'POST'}).then(r=>r.json()).then(d=>{
    let cell = document.getElementById('cell-'+entryId);
    cell.className='calendar-cell '+d.color;
    document.getElementById('current_streak').innerText = d.current;
    document.getElementById('best_streak').innerText = d.best;
    document.getElementById('consistency').innerText = d.consistency;
 });
}
function goToToday(){
    let el = document.getElementById('today');
    if(el) el.scrollIntoView({behavior:'smooth',block:'center'});
}
</script>
</head>
<body>
<header><div class='logo'></div>Streakly</header>
<nav>
<a href='{{ url_for("home") }}'>Home</a>
<a href='{{ url_for("analytics") }}'>Analytics</a>
</nav>
<main>
{% block content %}{% endblock %}
</main>
</body>
</html>
"""

# Routes
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method=='POST':
        return redirect(url_for('home'))
    return render_template_string("""
{% extends base_template %}
{% block content %}
<h2>Login</h2>
<form method='post'>
<input type='text' name='username' placeholder='Username' required>
<input type='password' name='password' placeholder='Password' required>
<button type='submit'>Login</button>
</form>
<p><a href='{{ url_for("register") }}'>Register</a></p>
{% endblock %}
""", base_template=base_template)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method=='POST':
        return redirect(url_for('login'))
    return render_template_string("""
{% extends base_template %}
{% block content %}
<h2>Register</h2>
<form method='post'>
<input type='text' name='username' placeholder='Username' required>
<input type='password' name='password' placeholder='Password' required>
<input type='password' name='confirm_password' placeholder='Confirm Password' required>
<button type='submit'>Register</button>
</form>
<p><a href='{{ url_for("login") }}'>Login</a></p>
{% endblock %}
""", base_template=base_template)

@app.route('/')
def home():
    # placeholder dashboard
    return render_template_string("""
{% extends base_template %}
{% block content %}
<h2>Streakly Dashboard</h2>
<button onclick='goToToday()'>Go to Today</button>
<p>Current Streak: <span id='current_streak'>0</span> | Best Streak: <span id='best_streak'>0</span> | Consistency: <span id='consistency'>0%</span></p>
<!-- Calendar & habits would go here -->
{% endblock %}
""", base_template=base_template)

@app.route('/analytics')
def analytics():
    return render_template_string("""
{% extends base_template %}
{% block content %}
<h2>Analytics</h2>
<!-- Analytics charts and reasons -->
{% endblock %}
""", base_template=base_template)

@app.route('/toggle_habit/<int:entry_id>', methods=['POST'])
def toggle_habit(entry_id):
    # Placeholder toggle logic
    color='green'
    return jsonify({'color':color,'current':1,'best':2,'consistency':'100%'})

if __name__=='__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

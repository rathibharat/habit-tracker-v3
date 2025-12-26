from flask import Flask, request, redirect, url_for, render_template_string, jsonify, send_file
from flask_sqlalchemy import SQLAlchemy
from datetime import date, datetime, timedelta
import csv, io

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///streakly.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# -------------------- Database Models --------------------
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
    day = db.Column(db.Date, nullable=False)
    completed = db.Column(db.Boolean, default=False)

class HabitReason(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    day = db.Column(db.Date, unique=True)
    reason = db.Column(db.String(255))

with app.app_context():
    db.create_all()

# -------------------- Routes --------------------
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username, password=password).first()
        if user:
            return redirect(url_for('dashboard', user_id=user.id))
        else:
            return render_template_string(LOGIN_HTML, error='Invalid credentials')
    return render_template_string(LOGIN_HTML, error='')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if User.query.filter_by(username=username).first():
            return render_template_string(REGISTER_HTML, error='Username exists')
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template_string(REGISTER_HTML, error='')

@app.route('/dashboard/<int:user_id>')
def dashboard(user_id):
    today = date.today()
    habits = Habit.query.filter_by(user_id=user_id).all()

    # Compute daily logs and colors
    day_logs = {}
    for i in range(30):
        day = today - timedelta(days=29-i)
        day_logs[day] = {'completed':0, 'total':0}
        for habit in habits:
            # Check frequency
            if habit.frequency == 'weekly' and day.weekday() != 6:
                continue
            if habit.frequency == 'monthly' and day.day != (date(day.year, day.month+1, 1) - timedelta(days=1)).day:
                continue
            log = HabitLog.query.filter_by(habit_id=habit.id, day=day).first()
            day_logs[day]['total'] += 1
            if log and log.completed:
                day_logs[day]['completed'] += 1

    return render_template_string(DASHBOARD_HTML, user_id=user_id, habits=habits, day_logs=day_logs)

@app.route('/toggle_habit', methods=['POST'])
def toggle_habit():
    habit_id = int(request.form['habit_id'])
    day = datetime.strptime(request.form['day'], '%Y-%m-%d').date()
    log = HabitLog.query.filter_by(habit_id=habit_id, day=day).first()
    if not log:
        log = HabitLog(habit_id=habit_id, day=day, completed=True)
        db.session.add(log)
    else:
        log.completed = not log.completed
    db.session.commit()
    return jsonify({'status':'ok'})

@app.route('/save_reason', methods=['POST'])
def save_reason():
    data = request.get_json()
    day_date = datetime.strptime(data['day'], '%Y-%m-%d').date()
    reason_text = data['reason']
    reason = HabitReason.query.filter_by(day=day_date).first()
    if not reason:
        reason = HabitReason(day=day_date, reason=reason_text)
        db.session.add(reason)
    else:
        reason.reason = reason_text
    db.session.commit()
    return jsonify({'status':'ok'})

@app.route('/analytics/<int:user_id>')
def analytics(user_id):
    habits = Habit.query.filter_by(user_id=user_id).all()
    reasons = HabitReason.query.all()
    return render_template_string(ANALYTICS_HTML, user_id=user_id, habits=habits, reasons=reasons)

@app.route('/export_csv/<int:user_id>')
def export_csv(user_id):
    habits = Habit.query.filter_by(user_id=user_id).all()
    si = io.StringIO()
    cw = csv.writer(si)
    cw.writerow(['Habit Name','Date','Completed'])
    for habit in habits:
        logs = HabitLog.query.filter_by(habit_id=habit.id).all()
        for log in logs:
            cw.writerow([habit.name, log.day, log.completed])
    output = io.BytesIO()
    output.write(si.getvalue().encode('utf-8'))
    output.seek(0)
    return send_file(output, mimetype='text/csv', as_attachment=True, download_name='habit_logs.csv')

# -------------------- HTML Templates --------------------
LOGIN_HTML = '''
<!DOCTYPE html>
<html><head><title>Streakly Login</title></head>
<body>
<h1>Streakly</h1>
<form method='post'>
Username: <input type='text' name='username'><br>
Password: <input type='password' name='password'><br>
<input type='submit' value='Login'>
</form>
<p>{{error}}</p>
<a href='/register'>Register</a>
</body></html>
'''

REGISTER_HTML = '''
<!DOCTYPE html>
<html><head><title>Streakly Register</title></head>
<body>
<h1>Streakly</h1>
<form method='post'>
Username: <input type='text' name='username'><br>
Password: <input type='password' name='password'><br>
<input type='submit' value='Register'>
</form>
<p>{{error}}</p>
<a href='/'>Login</a>
</body></html>
'''

DASHBOARD_HTML = '''
<!DOCTYPE html>
<html><head><title>Streakly Dashboard</title>
<style>
.day-cell {width:40px;height:40px;text-align:center;vertical-align:middle;border:1px solid #ccc;display:inline-block;margin:1px;}
.green{background-color:#4CAF50;}
.yellow{background-color:#FFEB3B;}
.red{background-color:#F44336;}
.gray{background-color:#e0e0e0;}
.reason-box{width:100%;}
</style>
</head>
<body>
<h1>Streakly</h1>
<a href='/analytics/{{user_id}}'>Analytics</a>
<div>
{% for day, log in day_logs.items() %}
    {% set color = 'gray' %}
    {% if log.total > 0 %}
        {% if log.completed == log.total %}
            {% set color='green' %}
        {% elif log.completed == 0 %}
            {% set color='red' %}
        {% elif log.completed <= log.total/2 %}
            {% set color='yellow' %}
        {% else %}
            {% set color='yellow' %}
        {% endif %}
    {% endif %}
    <div class='day-cell {{color}}'>
        {{day.day}}<br>
        {% if log.completed < log.total %}
        <textarea class='reason-box' data-day='{{day}}'>{{HabitReason.query.filter_by(day=day).first().reason if HabitReason.query.filter_by(day=day).first() else ''}}</textarea>
        {% endif %}
    </div>
{% endfor %}
</div>
<script>
document.querySelectorAll('.reason-box').forEach(tb=>{
    tb.addEventListener('blur', function(){
        fetch('/save_reason',{
            method:'POST',
            headers:{'Content-Type':'application/json'},
            body: JSON.stringify({day:this.dataset.day, reason:this.value})
        })
    })
})
</script>
</body></html>
'''

ANALYTICS_HTML = '''
<!DOCTYPE html>
<html><head><title>Streakly Analytics</title></head>
<body>
<h1>Streakly Analytics</h1>
<a href='/dashboard/{{user_id}}'>Back</a>
<h3>Reasons for missed habits</h3>
<ul>
{% for r in reasons %}
    <li>{{r.day}} : {{r.reason}}</li>
{% endfor %}
</ul>
</body></html>
'''

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)

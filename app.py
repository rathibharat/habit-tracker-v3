# streakly_app.py
# Full version ready for deployment

from flask import Flask, render_template_string, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, datetime, timedelta
import calendar
import os

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

# ---------- DATABASE ----------
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DATABASE_URL", "sqlite:///habits.db")
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ---------- MODELS ----------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)

class Habit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    goal = db.Column(db.String(200))
    frequency = db.Column(db.String(10), default='daily')  # daily/weekly/monthly

class DailyStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    habit_id = db.Column(db.Integer, db.ForeignKey('habit.id'))
    day = db.Column(db.String(10))
    completed = db.Column(db.Integer, default=0)

class DailyReason(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    day = db.Column(db.String(10))
    reason = db.Column(db.String(300))

with app.app_context():
    db.create_all()

# ---------- AUTH HELPERS ----------
def current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

# ---------- AUTH ROUTES ----------
from itsdangerous import URLSafeTimedSerializer
serializer = URLSafeTimedSerializer(app.secret_key)

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        email = request.form['email']
        password = generate_password_hash(request.form['password'])
        if User.query.filter_by(email=email).first():
            return "User already exists"
        user = User(email=email, password_hash=password)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for('login'))
    return render_template_string('''
    <h2>Register</h2>
    <form method="post">
      Email <input name="email"><br>
      Password <input name="password" type="password"><br>
      <button>Register</button>
    </form>
    ''')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user and check_password_hash(user.password_hash, request.form['password']):
            session['user_id'] = user.id
            return redirect(url_for('calendar_view'))
        return "Invalid credentials"
    return render_template_string('''
    <h2>Login</h2>
    <form method="post">
      Email <input name="email"><br>
      Password <input name="password" type="password"><br>
      <button>Login</button>
    </form>
    <a href='/register'>Register</a>
    ''')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ---------- DASHBOARD HELPERS ----------
def calculate_streaks(statuses):
    days = sorted([s.day for s in statuses if s.completed])
    streak = max_streak = 0
    prev = None
    for d in days:
        cur = datetime.strptime(d, '%Y-%m-%d').date()
        if prev and cur == prev + timedelta(days=1):
            streak += 1
        else:
            streak = 1
        max_streak = max(max_streak, streak)
        prev = cur
    return streak, max_streak

# ---------- CALENDAR ----------
@app.route('/')
def calendar_view():
    user = current_user()
    if not user:
        return redirect(url_for('login'))

    today = date.today()
    year = int(request.args.get('year', today.year))
    month = int(request.args.get('month', today.month))

    # Prev/Next month
    if month == 1: prev_month, prev_year = 12, year-1
    else: prev_month, prev_year = month-1, year
    if month == 12: next_month, next_year = 1, year+1
    else: next_month, next_year = month+1, year

    habits = Habit.query.filter_by(user_id=user.id).all()
    statuses = DailyStatus.query.filter_by(user_id=user.id).all()
    reasons = {r.day:r.reason for r in DailyReason.query.filter_by(user_id=user.id).all()}

    completed = [s for s in statuses if s.completed]
    streak, best_streak = calculate_streaks(completed)
    total = len(statuses)
    done = len(completed)
    consistency = round((done/total)*100,1) if total else 0

    status_map = {}
    for s in statuses:
        status_map.setdefault(s.day, {})[s.habit_id] = s.completed

    cal = calendar.monthcalendar(year, month)

    return render_template_string('''
<!DOCTYPE html>
<html><head><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-gray-50 min-h-screen">
<div class="max-w-6xl mx-auto p-4">
  <div class="flex justify-between items-center mb-4">
    <h1 class="text-3xl font-bold text-blue-600">Streakly</h1>
    <div class="flex gap-2">
      <a href="/?month={{ prev_month }}&year={{ prev_year }}" class="bg-gray-200 px-3 py-1 rounded hover:bg-gray-300">Previous</a>
      <span class="font-semibold text-lg">{{ year }} - {{ month }}</span>
      <a href="/?month={{ next_month }}&year={{ next_year }}" class="bg-gray-200 px-3 py-1 rounded hover:bg-gray-300">Next</a>
    </div>
    <a href="/logout" class="text-red-500 ml-4">Logout</a>
  </div>

  <div class="bg-white rounded-xl shadow p-4 mb-4">
    <div class="mb-2">Current Streak: <span class="font-bold">{{ streak }}</span></div>
    <div class="mb-2">Best Streak: <span class="font-bold">{{ best_streak }}</span></div>
    <div>Consistency: <span class="font-bold">{{ consistency }}%</span></div>
  </div>

  <div class="bg-white rounded-xl shadow p-4 mb-6">
    <form method="post" action="/add_habit" class="flex gap-2">
      <input name="goal" placeholder="New habit" class="flex-1 border p-2 rounded">
      <select name="frequency" class="border p-2 rounded">
        <option value="daily" selected>Daily</option>
        <option value="weekly">Weekly</option>
        <option value="monthly">Monthly</option>
      </select>
      <button class="bg-blue-600 text-white px-4 rounded">Add</button>
    </form>
  </div>

  <div class="grid grid-cols-7 gap-2">
    {% for d in ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'] %}
      <div class="text-center font-semibold">{{d}}</div>
    {% endfor %}

    {% for week in cal %}
      {% for day in week %}
        {% if day==0 %}<div></div>
        {% else %}
          {% set ds = year|string + '-' + '%02d'|format(month) + '-' + '%02d'|format(day) %}
          {% set total_habits = habits|length %}
          {% set completed_habits = status_map.get(ds, {})|length %}
          {% if completed_habits==0 %} {% set color='bg-red-300' %}
          {% elif completed_habits==total_habits %} {% set color='bg-green-300' %}
          {% else %} {% set color='bg-yellow-200' %} {% endif %}
          <div class="{{color}} rounded-lg shadow p-2 text-sm">
            <div class="font-bold">{{day}}</div>
            {% for h in habits %}
              <form method="post" action="/update" class="flex items-center gap-1">
                <input type="hidden" name="habit_id" value="{{h.id}}">
                <input type="hidden" name="day" value="{{ds}}">
                <input type="checkbox" name="completed" {% if status_map.get(ds,{}).get(h.id) %}checked{% endif %} onchange="this.form.submit()">
                <span class="truncate">{{h.goal}}</span>
              </form>
            {% endfor %}
            <form method="post" action="/update_reason" class="mt-1">
              <input type="hidden" name="day" value="{{ds}}">
              <input name="reason" value="{{ reasons.get(ds,'') }}" placeholder="Reason" class="w-full border rounded p-1 text-xs">
              <button type="submit" class="hidden"></button>
            </form>
          </div>
        {% endif %}
      {% endfor %}
    {% endfor %}
  </div>

  <div class="mt-4">
    <a href="/export_csv" class="bg-gray-200 px-3 py-1 rounded hover:bg-gray-300">Export CSV</a>
  </div>
</div>
</body></html>
''',
    year=year, month=month, cal=cal, habits=habits, status_map=status_map, reasons=reasons,
    prev_month=prev_month, prev_year=prev_year, next_month=next_month, next_year=next_year,
    streak=streak, best_streak=best_streak, consistency=consistency)

# ---------- ACTIONS ----------
@app.route('/add_habit', methods=['POST'])
def add_habit():
    user = current_user()
    h = Habit(user_id=user.id, goal=request.form['goal'], frequency=request.form['frequency'])
    db.session.add(h)
    db.session.commit()
    return redirect(url_for('calendar_view'))

@app.route('/update', methods=['POST'])
def update():
    user = current_user()
    completed = 1 if request.form.get('completed') else 0
    entry = DailyStatus.query.filter_by(user_id=user.id, habit_id=request.form['habit_id'], day=request.form['day']).first()
    if not entry:
        entry = DailyStatus(user_id=user.id, habit_id=request.form['habit_id'], day=request.form['day'], completed=completed)
        db.session.add(entry)
    else:
        entry.completed = completed
    db.session.commit()
    return redirect(url_for('calendar_view'))

@app.route('/update_reason', methods=['POST'])
def update_reason():
    user = current_user()
    day = request.form['day']
    reason_text = request.form['reason']
    r = DailyReason.query.filter_by(user_id=user.id, day=day).first()
    if not r:
        r = DailyReason(user_id=user.id, day=day, reason=reason_text)
        db.session.add(r)
    else:
        r.reason = reason_text
    db.session.commit()
    return redirect(url_for('calendar_view'))

# ---------- EXPORT ----------
@app.route('/export_csv')
def export_csv():
    user = current_user()
    rows = DailyStatus.query.filter_by(user_id=user.id).all()
    output = 'date,habit_id,completed\n'
    for r in rows:
        output += f'{r.day},{r.habit_id},{r.completed}\n'
    return app.response_class(output, mimetype='text/csv', headers={"Content-Disposition": "attachment;filename=habit_export.csv"})

# ---------- RUN ----------
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=True)

# app.py
# Streakly — Habit Tracker with per-habit streaks
# Flask + PostgreSQL + Tailwind CSS

from flask import Flask, render_template_string, request, redirect, url_for, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import date, datetime, timedelta
import calendar, os
from itsdangerous import URLSafeTimedSerializer
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret")

# ---------- DATABASE ----------
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    "DATABASE_URL", "sqlite:///habits.db"
)
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
    name = db.Column(db.String(200))
    frequency = db.Column(db.String(10), default='daily')  # daily, weekly, monthly

class DailyStatus(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    habit_id = db.Column(db.Integer, db.ForeignKey('habit.id'))
    day = db.Column(db.String(10))
    completed = db.Column(db.Integer, default=0)
    reason = db.Column(db.String(300))

with app.app_context():
    db.create_all()

# ---------- AUTH ----------
serializer = URLSafeTimedSerializer(app.secret_key)

def current_user():
    if 'user_id' in session:
        return User.query.get(session['user_id'])
    return None

# ---------- RATE LIMIT ----------
limiter = Limiter(get_remote_address, app=app, default_limits=["100 per hour"])

@app.after_request
def secure_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    return response

# ---------- AUTH ROUTES ----------
@app.route('/register', methods=['GET', 'POST'])
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
<!DOCTYPE html>
<html>
<head><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-gray-100 min-h-screen flex items-center justify-center">
<div class="bg-white p-8 rounded-xl shadow-md w-full max-w-sm">
  <h2 class="text-2xl font-semibold mb-6 text-center">Register</h2>
  <form method="post" class="space-y-4">
    <input name="email" placeholder="Email" class="w-full border p-2 rounded">
    <input name="password" type="password" placeholder="Password" class="w-full border p-2 rounded">
    <button class="w-full bg-green-600 text-white py-2 rounded">Register</button>
  </form>
  <div class="text-sm text-center mt-4">
    Already have an account? <a href="/login" class="text-blue-600">Login</a>
  </div>
</div>
</body>
</html>
''')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user and check_password_hash(user.password_hash, request.form['password']):
            session['user_id'] = user.id
            return redirect(url_for('calendar_view'))
        return "Invalid credentials"
    return render_template_string('''
<!DOCTYPE html>
<html>
<head><script src="https://cdn.tailwindcss.com"></script></head>
<body class="bg-gray-100 min-h-screen flex items-center justify-center">
<div class="bg-white p-8 rounded-xl shadow-md w-full max-w-sm">
  <h2 class="text-2xl font-semibold mb-6 text-center">Login</h2>
  <form method="post" class="space-y-4">
    <input name="email" placeholder="Email" class="w-full border p-2 rounded">
    <input name="password" type="password" placeholder="Password" class="w-full border p-2 rounded">
    <button class="w-full bg-blue-600 text-white py-2 rounded">Login</button>
  </form>
  <div class="text-sm text-center mt-4">
    <a href="/register" class="text-green-600 mr-2">Register</a>
    <a href="/forgot" class="text-red-600">Forgot password?</a>
  </div>
</div>
</body>
</html>
''')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/forgot', methods=['GET','POST'])
def forgot_password():
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user:
            token = serializer.dumps(user.email)
            reset_link = url_for('reset_password', token=token, _external=True)
            return f"Reset link (demo): <a href='{reset_link}'>{reset_link}</a>"
        return "If account exists, reset link sent"
    return render_template_string('''
<h3>Forgot Password</h3>
<form method="post">
  Email <input name="email">
  <button>Send reset link</button>
</form>
''')

@app.route('/reset/<token>', methods=['GET','POST'])
def reset_password(token):
    try:
        email = serializer.loads(token, max_age=3600)
    except:
        return "Invalid or expired token"
    user = User.query.filter_by(email=email).first()
    if request.method == 'POST':
        user.password_hash = generate_password_hash(request.form['password'])
        db.session.commit()
        return redirect(url_for('login'))
    return render_template_string('''
<h3>Reset Password</h3>
<form method="post">
  New Password <input name="password" type="password">
  <button>Reset</button>
</form>
''')

# ---------- DASHBOARD HELPERS ----------
def calculate_streaks(statuses):
    days = sorted([s.day for s in statuses if s.completed])
    streak = max_streak = 0
    prev = None
    for d in days:
        cur = datetime.strptime(d, "%Y-%m-%d").date()
        if prev and cur == prev + timedelta(days=1):
            streak += 1
        else:
            streak = 1
        max_streak = max(max_streak, streak)
        prev = cur
    return streak, max_streak

def day_color(completed, total, is_future):
    if is_future:
        return "bg-gray-200"
    if total == 0 or completed==0:
        return "bg-red-400"
    ratio = completed/total
    if ratio==1: return "bg-green-400"
    if ratio>=0.5: return "bg-yellow-400"
    return "bg-red-300"

# ---------- CALENDAR ----------
@app.route('/', methods=['GET','POST'])
def calendar_view():
    user = current_user()
    if not user:
        return redirect(url_for('login'))

    today = date.today()
    year = int(request.args.get("year", today.year))
    month = int(request.args.get("month", today.month))

    habits = Habit.query.filter_by(user_id=user.id).all()
    statuses = DailyStatus.query.filter_by(user_id=user.id).all()

    streak, best_streak = calculate_streaks([s for s in statuses if s.completed])
    total = len(statuses)
    done = len([s for s in statuses if s.completed])
    consistency = round((done / total) * 100,1) if total else 0

    # Map statuses
    status_map = {}
    reason_map = {}
    for s in statuses:
        status_map.setdefault(s.day,{})[s.habit_id] = s.completed
        reason_map[s.day] = s.reason

    cal = calendar.monthcalendar(year, month)

    return render_template_string('''
<!DOCTYPE html>
<html>
<head>
  <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-50 min-h-screen">
  <div class="max-w-6xl mx-auto p-4">
    <!-- Header -->
    <div class="flex justify-between items-center mb-4">
      <h1 class="text-3xl font-bold text-purple-700">Streakly</h1>
      <div>
        <span class="px-2 py-1 rounded font-semibold text-white {{'bg-green-500' if streak>=5 else 'bg-yellow-500' if streak>=3 else 'bg-red-500'}}">Current Streak: {{streak}}</span>
        <span class="px-2 py-1 rounded font-semibold text-white {{'bg-green-500' if best_streak>=5 else 'bg-yellow-500' if best_streak>=3 else 'bg-red-500'}}">Best Streak: {{best_streak}}</span>
        <span class="px-2 py-1 rounded font-semibold text-white {{'bg-green-500' if consistency>=80 else 'bg-yellow-500' if consistency>=50 else 'bg-red-500'}}">Consistency: {{consistency}}%</span>
        <a href="/logout" class="ml-4 text-red-500 font-bold">Logout</a>
      </div>
    </div>

    <!-- Add habit -->
    <div class="bg-white rounded-xl shadow p-4 mb-4">
      <form method="post" action="/add_habit" class="flex gap-2">
        <input name="name" placeholder="New habit" class="flex-1 border p-2 rounded">
        <select name="frequency" class="border p-2 rounded">
          <option value="daily">Daily</option>
        </select>
        <button class="bg-blue-600 text-white px-4 rounded">Add</button>
      </form>
      <a href="/export_csv" class="text-green-700 mt-2 inline-block">Export CSV</a>
    </div>

    <!-- Calendar -->
    <div class="grid grid-cols-7 gap-2">
      {% for d in ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'] %}
        <div class="text-center font-semibold">{{d}}</div>
      {% endfor %}
      {% for week in cal %}
        {% for day in week %}
          {% if day==0 %}
            <div></div>
          {% else %}
            {% set ds = year|string + '-' + '%02d'|format(month) + '-' + '%02d'|format(day) %}
            {% set completed = status_map.get(ds,{})|sum %}
            {% set total = habits|length %}
            {% set is_future = ds>current_user().id|string %}
            <div class="{{day_color(completed,total,day>now().day)}} rounded-lg shadow p-2 text-sm">
              <div class="font-bold">{{day}}</div>
              {% for h in habits %}
                <form method="post" action="/update" class="flex items-center gap-1">
                  <input type="hidden" name="habit_id" value="{{h.id}}">
                  <input type="hidden" name="day" value="{{ds}}">
                  <input type="checkbox" name="completed" {% if status_map.get(ds,{}).get(h.id) %}checked{% endif %} onchange="this.form.submit()">
                  <span>{{h.name}}</span>
                </form>
              {% endfor %}
              <form method="post" action="/update_reason">
                <input type="hidden" name="day" value="{{ds}}">
                <input name="reason" placeholder="Reason / Note" value="{{reason_map.get(ds,'')}}" class="w-full border p-1 mt-1 rounded">
                <button class="hidden">Save</button>
              </form>
            </div>
          {% endif %}
        {% endfor %}
      {% endfor %}
    </div>
  </div>
</body>
</html>
''', habits=habits, status_map=status_map, reason_map=reason_map,
     streak=streak, best_streak=best_streak, consistency=consistency,
     year=year, month=month, cal=cal, day_color=day_color)

# ---------- HABIT ACTIONS ----------
@app.route('/add_habit', methods=['POST'])
def add_habit():
    user = current_user()
    habit = Habit(user_id=user.id, name=request.form['name'], frequency=request.form['frequency'])
    db.session.add(habit)
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
    reason = request.form['reason']
    # update or insert reason
    entries = DailyStatus.query.filter_by(user_id=user.id, day=day).all()
    if entries:
        for e in entries:
            e.reason = reason
    else:
        # create dummy entry with reason
        e = DailyStatus(user_id=user.id, habit_id=0, day=day, completed=0, reason=reason)
        db.session.add(e)
    db.session.commit()
    return redirect(url_for('calendar_view'))

# ---------- CSV EXPORT ----------
@app.route('/export_csv')
def export_csv():
    user = current_user()
    rows = DailyStatus.query.filter_by(user_id=user.id).all()
    output = "date,habit_id,completed,reason\n"
    for r in rows:
        output += f"{r.day},{r.habit_id},{r.completed},{r.reason or ''}\n"
    return app.response_class(output, mimetype='text/csv',
                              headers={"Content-Disposition":"attachment;filename=streakly_export.csv"})

# ---------- ADMIN DASHBOARD ----------
@app.route('/admin')
def admin_dashboard():
    user = current_user()
    if not user or user.email != os.environ.get("ADMIN_EMAIL"):
        return "Unauthorized",403
    users = User.query.count()
    habits = Habit.query.count()
    entries = DailyStatus.query.count()
    return render_template_string('''
<h2>Admin Dashboard</h2>
<ul>
  <li>Total Users: {{users}}</li>
  <li>Total Habits: {{habits}}</li>
  <li>Total Daily Entries: {{entries}}</li>
</ul>
''', users=users, habits=habits, entries=entries)

# ---------- RUN ----------
if __name__=="__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)

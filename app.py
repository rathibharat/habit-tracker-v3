from flask import Flask, render_template, request, redirect, url_for, session, jsonify, Response
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from functools import wraps
import datetime, calendar, csv

app = Flask(__name__)
app.secret_key = "YOUR_SECRET_KEY"
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///streakly.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# Security
serializer = URLSafeTimedSerializer(app.secret_key)

# Flask-Limiter
limiter = Limiter(key_func=get_remote_address, default_limits=["200 per day", "50 per hour"])
limiter.init_app(app)

# Models
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    habits = db.relationship("Habit", backref="user", cascade="all, delete-orphan")

class Habit(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    name = db.Column(db.String(100))
    frequency = db.Column(db.String(10))
    completions = db.relationship("Completion", backref="habit", cascade="all, delete-orphan")

class Completion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    habit_id = db.Column(db.Integer, db.ForeignKey("habit.id"))
    day = db.Column(db.Integer)
    month = db.Column(db.Integer)
    year = db.Column(db.Integer)
    done = db.Column(db.Boolean, default=False)
    reason = db.Column(db.String(200), default="")

# Context processor for templates
@app.context_processor
def inject_user():
    if "user_id" in session:
        user = User.query.get(session["user_id"])
        return dict(current_user=user)
    return dict(current_user=None)

# Context processor to make datetime available in all templates
@app.context_processor
def utility_processor():
    import datetime
    return dict(datetime=datetime)

# Authentication
@app.route("/register", methods=["GET","POST"])
@limiter.limit("5 per minute")
def register():
    if request.method=="POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])
        if User.query.filter_by(username=username).first():
            return "Username exists!"
        user = User(username=username, password=password)
        db.session.add(user)
        db.session.commit()
        return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET","POST"])
@limiter.limit("10 per minute")
def login():
    if request.method=="POST":
        username = request.form["username"]
        password = request.form["password"]
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password, password):
            session["user_id"] = user.id
            return redirect(url_for("home"))
        return "Invalid credentials"
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.pop("user_id", None)
    return redirect(url_for("login"))

# Admin decorator
def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        user = User.query.get(session["user_id"])
        if not user.is_admin:
            return "Access denied", 403
        return f(*args, **kwargs)
    return decorated_function

@app.route("/admin")
@admin_required
def admin_dashboard():
    users = User.query.all()
    return render_template("admin.html", users=users)

@app.route("/admin/delete_user/<int:user_id>", methods=["POST"])
@admin_required
def delete_user(user_id):
    user = User.query.get(user_id)
    if user:
        db.session.delete(user)
        db.session.commit()
    return redirect(url_for("admin_dashboard"))

# Calendar generation
def generate_calendar_data(user_id, year, month):
    habits = Habit.query.filter_by(user_id=user_id).all()
    calendar_data=[]
    month_range=calendar.monthrange(year,month)[1]
    for day in range(1,month_range+1):
        day_date=datetime.date(year,month,day)
        weekday=day_date.weekday()
        day_habits=[]
        for habit in habits:
            include=False
            if habit.frequency=="daily":
                include=True
            elif habit.frequency=="weekly" and weekday==5:  # Saturday
                include=True
            elif habit.frequency=="monthly" and day==month_range-1:  # second last day
                include=True
            if include:
                completion=Completion.query.filter_by(habit_id=habit.id, day=day, month=month, year=year).first()
                day_habits.append({
                    "id":habit.id,
                    "name":habit.name,
                    "done":completion.done if completion else False
                })
        total=len(day_habits)
        done_count=sum(1 for h in day_habits if h["done"])
        if day_date>datetime.date.today():
            color="gray"
        elif total==0:
            color="gray"
        elif done_count==total:
            color="green"
        elif done_count>0:
            color="yellow"
        else:
            color="red"
        show_reason=done_count<total and total>0
        calendar_data.append({"day":day,"habits":day_habits,"color":color,"show_reason":show_reason})
    return calendar_data

# Home page
@app.route("/", methods=["GET","POST"])
@app.route("/home", methods=["GET","POST"])
def home():
    if "user_id" not in session:
        return redirect(url_for("login"))
    user_id=session["user_id"]
    today=datetime.date.today()
    month=int(request.args.get("month", today.month))
    year=int(request.args.get("year", today.year))

    if request.method=="POST":
        name=request.form["name"]
        frequency=request.form["frequency"]
        habit=Habit(name=name, frequency=frequency, user_id=user_id)
        db.session.add(habit)
        db.session.commit()
        return redirect(url_for("home", month=month, year=year))

    habits=Habit.query.filter_by(user_id=user_id).all()
    calendar_data=generate_calendar_data(user_id, year, month)

    total_done=0
    total_habits=0
    for day in calendar_data:
        total_habits+=len(day["habits"])
        total_done+=sum(1 for h in day["habits"] if h["done"])
    consistency=round(total_done/total_habits*100,2) if total_habits>0 else 0
    streak=0
    return render_template("home.html", habits=habits, calendar_data=calendar_data, month=month, year=year, consistency=consistency, streak=streak)

# Toggle completion
@app.route("/complete/<int:habit_id>/<int:day>", methods=["POST"])
@limiter.limit("100 per hour")
def complete(habit_id, day):
    if "user_id" not in session:
        return jsonify({"status":"error"})
    user_id=session["user_id"]
    month=int(request.form["month"])
    year=int(request.form["year"])
    reason=request.form.get("reason","")
    completion=Completion.query.filter_by(habit_id=habit_id, day=day, month=month, year=year).first()
    if not completion:
        completion=Completion(habit_id=habit_id, day=day, month=month, year=year)
        db.session.add(completion)
    completion.done=not completion.done
    completion.reason=reason
    db.session.commit()

    day_habits=Completion.query.join(Habit).filter(Habit.user_id==user_id, Completion.day==day, Completion.month==month, Completion.year==year).all()
    total=len(day_habits)
    done_count=sum(1 for h in day_habits if h.done)
    if total==0:
        color="gray"
    elif done_count==total:
        color="green"
    elif done_count>0:
        color="yellow"
    else:
        color="red"

    return jsonify({"status":"ok","color":color})

# Remove habit
@app.route("/remove_habit/<int:habit_id>", methods=["POST"])
def remove_habit(habit_id):
    habit=Habit.query.get(habit_id)
    if habit:
        db.session.delete(habit)
        db.session.commit()
    return redirect(url_for("home"))

# Jump to today
@app.route("/jump_today")
def jump_today():
    today=datetime.date.today()
    return redirect(url_for("home", month=today.month, year=today.year))

# Analytics
@app.route("/analytics")
def analytics():
    if "user_id" not in session:
        return redirect(url_for("login"))
    user_id=session["user_id"]
    habits=Habit.query.filter_by(user_id=user_id).all()
    data=[]
    for habit in habits:
        total=Completion.query.filter_by(habit_id=habit.id).count()
        done=Completion.query.filter_by(habit_id=habit.id, done=True).count()
        streak=0
        data.append({"name":habit.name,"total":total,"done":done,"streak":streak})
    return render_template("analytics.html", data=data)

# Export CSV
@app.route("/export")
def export():
    if "user_id" not in session:
        return redirect(url_for("login"))
    user_id=session["user_id"]
    output=Response()
    output.headers["Content-Disposition"]="attachment; filename=streakly.csv"
    output.headers["Content-type"]="text/csv"
    writer=csv.writer(output)
    writer.writerow(["Habit","Day","Month","Year","Done","Reason"])
    completions=Completion.query.join(Habit).filter(Habit.user_id==user_id).all()
    for c in completions:
        writer.writerow([c.habit.name, c.day, c.month, c.year, c.done, c.reason])
    return output

# Run app with app context
if __name__=="__main__":
    with app.app_context():
        db.create_all()
app.run(host="0.0.0.0", port=5000)

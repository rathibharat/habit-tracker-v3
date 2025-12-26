import pytest
from app import app, db, User, Habit, HabitLog

@pytest.fixture
def client():
    app.config['TESTING'] = True
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
    with app.test_client() as client:
        with app.app_context():
            db.create_all()
        yield client

def register_and_login(client):
    client.post('/register', data={'email':'test@example.com','password':'pass'})
    client.post('/login', data={'email':'test@example.com','password':'pass'})

def test_register_login_logout(client):
    rv = client.post('/register', data={'email':'a@b.com','password':'p'})
    assert rv.status_code == 302
    rv = client.post('/login', data={'email':'a@b.com','password':'p'})
    assert rv.status_code == 302
    rv = client.get('/logout')
    assert rv.status_code == 302

def test_add_daily_habit(client):
    register_and_login(client)
    rv = client.post('/add_habit', data={'name':'Daily Test','frequency':'daily'})
    assert rv.status_code == 302
    habit = Habit.query.filter_by(name='Daily Test').first()
    assert habit.frequency == 'daily'

def test_add_weekly_monthly_habits(client):
    register_and_login(client)
    client.post('/add_habit', data={'name':'Weekly Test','frequency':'weekly'})
    client.post('/add_habit', data={'name':'Monthly Test','frequency':'monthly'})
    h_weekly = Habit.query.filter_by(name='Weekly Test').first()
    h_monthly = Habit.query.filter_by(name='Monthly Test').first()
    assert h_weekly.frequency == 'weekly'
    assert h_monthly.frequency == 'monthly'

def test_habit_logging_and_streak(client):
    register_and_login(client)
    client.post('/add_habit', data={'name':'Daily Habit','frequency':'daily'})
    habit = Habit.query.filter_by(name='Daily Habit').first()
    client.post('/update', data={'goal_id': habit.id, 'day':'2025-12-25', 'completed':'on'})
    log = HabitLog.query.filter_by(habit_id=habit.id).first()
    assert log.completed == 1
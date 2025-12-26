# Habit Tracker v3

**Final version of the Habit Tracker app**, optimized for minimal friction and behavioral effectiveness.

---

## Features

- Daily, weekly, and monthly habit scheduling
- Per-habit streak dashboard
- Missed habit reminders (gentle banner in-app)
- Clean, minimal UI with Tailwind CSS
- Multi-user support with authentication (email + password)
- Password reset / forgot password functionality
- CSV export per user
- Admin dashboard for monitoring users and goals
- Basic rate limiting & security hardening

---

## Tech Stack

- Python 3
- Flask (Web framework)
- SQLAlchemy (ORM)
- PostgreSQL (optional, default SQLite supported)
- Tailwind CSS (UI)
- Flask-Mail (optional email reminders)
- Flask-Limiter (basic security / rate limiting)

---

## Setup & Deployment

### 1. Clone or Upload Repository
- **GitHub:** Upload files (`app.py`, `requirements.txt`, `test_app.py`, `README.md`)  
- **Render:** Connect the GitHub repo and create a Web Service.

### 2. Environment Variables
Set the following on Render (or locally):

SECRET_KEY=<your_secure_key>
DATABASE_URL=<PostgreSQL URL, optional>
ADMIN_EMAIL=<your admin email>
EMAIL_USER=<optional, for email reminders>
EMAIL_PASS=<optional, for email reminders>


### 3. Build & Start Commands
- **Build:** `pip install -r requirements.txt`  
- **Start:** `python app.py`  

Render will deploy and provide a public URL.

---

## Usage

1. Open the app URL in your browser or phone.  
2. Register a new user.  
3. Add daily, weekly, or monthly habits.  
4. Mark habits as completed daily on the calendar.  
5. Check the dashboard for streaks and consistency.  
6. Missed habits from yesterday will appear in a gentle banner.  
7. Export your habits and progress as CSV from the export page.  

---

## Testing

Run unit tests locally or on the server:

```bash
pytest test_app.py



---


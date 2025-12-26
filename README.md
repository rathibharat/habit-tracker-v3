✅ Streakly

Streakly is a minimal, clean habit-tracking web app built with Flask.
It helps you build consistency by tracking daily, weekly, and monthly habits with streaks, analytics, and a calendar-based UI.

Designed with a mobile-first, Apple-like UI and deployed easily on Render.

✨ Features

🔐 User authentication (login & register)

📅 Calendar-based habit tracking (Mon–Sun layout)

✅ Daily, Weekly (Saturday), Monthly (2nd last day) habits

🔥 Habit streak tracking

📊 Analytics (consistency %, streak rate)

📝 Daily reason tracking (why habits were missed)

📤 Export data (CSV)

📱 Mobile-friendly UI with:

Today View toggle

Swipe between days

Tap-to-check habit rows

🧠 Smart empty states & onboarding

⏱ Rate limiting for security

💾 Persistent storage support on Render

🛠 Tech Stack

Backend: Flask (Python)

Frontend: Jinja2 + Tailwind CSS (CDN)

Database: SQLite (with Render persistent disk)

Auth: Werkzeug password hashing

Security: Flask-Limiter

Deployment: Render

📂 Project Structure
streakly/
│
├── app.py
├── requirements.txt
├── README.md
│
├── templates/
│   ├── layout.html
│   ├── login.html
│   ├── register.html
│   ├── home.html
│   ├── analytics.html
│   └── export.html
│
└── static/   (optional)

🚀 Run Locally
1️⃣ Clone the repo
git clone https://github.com/your-username/streakly.git
cd streakly

2️⃣ Create virtual environment
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

3️⃣ Install dependencies
pip install -r requirements.txt

4️⃣ Set environment variables
export SECRET_KEY="dev-secret"

5️⃣ Run the app
python app.py


Open: http://127.0.0.1:5000

☁️ Deploy on Render
1️⃣ Create a new Web Service

Connect your GitHub repo

Runtime: Python

Start command:

gunicorn app:app

2️⃣ Add environment variables
Key	Value
SECRET_KEY	long-random-string
ADMIN_EMAIL	your@email.com
💾 IMPORTANT: Persistent Storage (Required)

Streakly uses SQLite.
Render containers have ephemeral filesystems, so you must add a persistent disk or you will lose data when the app sleeps.

✅ How to fix data loss

In Render → Service → Disks

Add disk:

Mount path: /var/data

Update in app.py:

DATABASE = "/var/data/streakly.db"


Now your data survives:

Sleep / wake

Restarts

Redeploys

🔐 Security Notes

Passwords are hashed (Werkzeug)

Rate limiting enabled (Flask-Limiter)

Sessions protected via SECRET_KEY

Auth pages hidden from logged-in users

📊 Analytics Explained

Consistency %: habits completed ÷ habits scheduled

Streak: consecutive days completed per habit

Monthly comparison: this month vs last month

Reasons help identify patterns in missed habits

📱 Mobile UX Highlights

Today-first design

Swipe left/right to change day

Tap entire row to toggle habit

Sticky actions & toast feedback

Clean typography & spacing

🧭 Roadmap (Optional Ideas)

Email reminders (Render cron job)

Push notifications

Habit categories & tags

Dark mode

Postgres support

🤝 Contributing

Contributions are welcome!

Fork the repo

Create a feature branch

Submit a pull request

📄 License

MIT License

🙌 Acknowledgements

Built with care to encourage consistency over intensity.

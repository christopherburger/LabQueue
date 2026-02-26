# Lightweight Academic Lab Queue
A fast, mobile-friendly, and secure queuing system designed for academic programming labs. Built with Python, Flask, and HTMX, this application allows students to request help across multiple lab rooms while providing Teaching Assistants (TAs) with a clean, real-time dashboard to manage and resolve requests.

The system is designed to be completely ephemeral for students (no accounts or passwords required) while maintaining strict accountability and privacy standards for an academic intranet environment.

## Major Features

No Login Required: Students join the queue using only their Name and Seat Number (optional).

Persistent Sessions: A 120-minute session cookie remembers the student's identity, allowing for 1-click "Quick Re-join" for subsequent requests during the same lab period.

Privacy Mode: When enabled, students only see their own name in the queue. Other waiting students appear as anonymous placeholders to prevent broadcasting attendance or struggles.

Auto-Refreshing UI: The queue updates in real-time using HTMX—no manual page refreshes needed.

IP-Based Audit Logging: All queue joins, cancellations, and resolutions are logged with timestamps and robust IP address capture (X-Forwarded-For proxy support) to a rotating audit.log file.

Anti-Spam Rate Limiting: Built-in SQLite checks prevent the same IP address from joining the queue more than once every 60 seconds.

Input Sanitization & Profanity Filtering: Integrated better_profanity checks and character limits automatically silently reject inappropriate or overly long names.

## Tech Stack

Backend: Python 3, Flask

Database: SQLite3 (Local file-based, ephemeral-friendly)

Frontend: HTML5, CSS3, HTMX (for lightweight AJAX requests)

Security: werkzeug.security (Scrypt), better_profanity

## Setup & Installation

### 1. Clone the repository and install dependencies


`git clone https://github.com/yourusername/lab_queue.git
`cd lab_queue
`pip install flask python-dateutil better_profanity

### 2. Set the TA Password Environment Variable

Generate a secure password hash using the Werkzeug library:

`python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your_secure_password'))"

Set the output string as an environment variable named TA_PASSWORD_HASH.

Windows (PowerShell): $env:TA_PASSWORD_HASH = "scrypt:..."

Mac/Linux: export TA_PASSWORD_HASH="scrypt:..."

### 3. Run the application

`python app.py

The application will be available at http://127.0.0.1:5000.

## Configuration

You can easily adapt the application for different semesters or lab setups by editing the configuration variables at the top of app.py:

# --- CONFIGURATION ---

#### Define the active lab rooms. 

#### Key = Internal code, Value = Display name on tabs

ROOMS = {
    'A': 'Room 101',
    'B': 'Room 205',
    'C': 'Room 303'
}

#### Toggle to hide student names from other non-TA users

PRIVACY_MODE = True 

#### Add custom campus-specific banned terms

BANNED_WORDS = ['custom_slang_1', 'custom_slang_2'] 

## File Structure

app.py: The core Flask application, routing logic, and SQLite database initialization.

queue.db: Auto-generated SQLite database.

audit.log: Auto-generated rotating log file tracking user actions by IP.

### templates/

index.html: The main user interface, including tabs, forms, and mobile CSS.

partial_queue.html: The isolated table rows injected by HTMX for live updates.

login.html: The secure TA authentication portal.

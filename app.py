import sqlite3
import os
from flask import Flask, render_template, request, session, redirect, url_for
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash
import dateutil.parser
import logging
from logging.handlers import RotatingFileHandler
from better_profanity import profanity

app = Flask(__name__)
app.secret_key = 'demo' #Make sure to change the key from this placeholder
app.permanent_session_lifetime = timedelta(minutes=120)


# --- CONFIGURATION ---
# Key = URL/Database Code
# Value = Display Name
ROOMS = {
    'A': 'CSTI 114',
    'B': 'Room B',
    'C': 'Room C'
}

PROFANITY_FILTER = False
PRIVACY_MODE = True

# Set up a specific logger for audit events
audit_logger = logging.getLogger('audit')
audit_logger.setLevel(logging.INFO)
# Save to 'audit.log', rotate file after 1MB to save space
handler = RotatingFileHandler('audit.log', maxBytes=1000000, backupCount=1)
# Format: Time | IP | Action | Name | Seat
handler.setFormatter(logging.Formatter('%(asctime)s | %(message)s'))
audit_logger.addHandler(handler)


# --- TEMPLATE HELPER ---
# This makes the 'ROOMS' dictionary available in ALL templates
# without needing to pass it manually in every render_template() call.
@app.context_processor
def inject_rooms():
    return dict(rooms=ROOMS, privacy_mode=PRIVACY_MODE)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'queue.db')

# --- CUSTOM TIME FILTER ---
@app.template_filter('format_time')
def format_time(value):
    if not value: return ""
    try:
        # Parse the ISO string from SQLite
        dt = dateutil.parser.parse(value)
        # Return standard 12-hour time (e.g. "3:45 PM")
        # %-I removes the leading zero on hours (Linux/Mac specific)
        # Use %I if you want 03:45 PM


        #OFFSET FOR PYTHONANYWHERE 
        #dt = dt + timedelta(hours=-6)

        return dt.strftime("%-I:%M %p")
    except:
        return value

def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS queue
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      name TEXT,
                      seat TEXT,
                      room TEXT,
                      timestamp DATETIME,
                      ip_address TEXT)''')
        # Migrations for existing DBs
        try:
            c.execute('ALTER TABLE queue ADD COLUMN room TEXT')
        except sqlite3.OperationalError: pass

        try:
            c.execute('ALTER TABLE queue ADD COLUMN ip_address TEXT')
        except sqlite3.OperationalError: pass

        conn.commit()

def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

init_db()

def get_client_ip():
    try:
        # 1. Try to get the real IP if behind a proxy (PythonAnywhere/Nginx)
        # We grab the first IP in the list (the original client)
        forwarded_ips = request.headers.getlist("X-Forwarded-For")
        if forwarded_ips:
            return forwarded_ips[0]

        # 2. Try the direct connection IP
        if request.remote_addr:
            return request.remote_addr

        # 3. If both are None , return placeholder
        return "0.0.0.0"

    except Exception:
        # 4. If any code above crashes (e.g. malformed headers), fail safe
        return "0.0.0.0"

@app.route('/')
def index():
    current_room = session.get('current_room', 'A')
    my_ticket_id = session.get('my_ticket_id')
    ticket_room = None

    if my_ticket_id:
        conn = get_db_connection()
        row = conn.execute('SELECT room FROM queue WHERE id = ?', (my_ticket_id,)).fetchone()
        conn.close()
        if row:
            ticket_room = row['room']
        else:
            session.pop('my_ticket_id', None)
            my_ticket_id = None

    if request.headers.get('HX-Request'):
        return render_template('partial_queue.html',
                             queue=get_queue_data(current_room),
                             is_ta=session.get('is_ta'),
                             my_id=my_ticket_id)

    return render_template('index.html',
                         queue=get_queue_data(current_room),
                         current_room=current_room,
                         ticket_room=ticket_room,
                         is_ta=session.get('is_ta'),
                         my_id=my_ticket_id)

def get_queue_data(room_code):
    conn = get_db_connection()
    queue = conn.execute('SELECT * FROM queue WHERE room = ? ORDER BY timestamp ASC', (room_code,)).fetchall()
    conn.close()
    return queue

@app.route('/set_room/<room_code>')
def set_room(room_code):
    # Validate against the keys defined in ROOMS
    if room_code in ROOMS:
        session['current_room'] = room_code
    return redirect(url_for('index'))

@app.route('/join', methods=['POST'])
def join():
    # Attempt to get data from Form OR Session
    name = request.form.get('name') or session.get('student_name')
    # Default seat to empty string if not provided
    seat = request.form.get('seat') or session.get('student_seat') or ""

    # Get room from session, or default to the first key in ROOMS
    default_room = next(iter(ROOMS))
    room = session.get('current_room', default_room)
    client_ip = get_client_ip() # <--- Capture IP

    #RATE LIMIT CHECK (15 Seconds)
    # We query the DB to see if this IP has an entry newer than 15 seconds ago.
    conn = get_db_connection()
    recent_post = conn.execute(
        "SELECT id FROM queue WHERE ip_address = ? AND timestamp > datetime('now', '-15 seconds')",
        (client_ip,)
    ).fetchone()
    conn.close()

    if recent_post:
        # If we found a recent post, block this request silently
        audit_logger.warning(f"{client_ip} | RATE_LIMIT | Blocked (Too Fast)")
        return redirect(url_for('index'))

    # Length Check
    if name and len(name) > 30:
        # Log the attempt and ignore it
        audit_logger.warning(f"{client_ip} | BLOCKED_LENGTH | {name}")
        return redirect(url_for('index'))

    # Profanity Check
    # This automatically catches "badword", "b@dword", "b.a.d.w.o.r.d", etc.
    if PROFANITY_FILTER:
        if name and profanity.contains_profanity(name):
            audit_logger.warning(f"{client_ip} | BLOCKED_WORD | {name}")
            return redirect(url_for('index'))

    if name:
        session.permanent = True
        session['student_name'] = name
        # Only save seat to session if they actually entered one
        if seat:
            session['student_seat'] = seat

        #Log Valid Entry to File
        audit_logger.info(f"{client_ip} | JOIN | {name} | Seat: {seat}")

        conn = get_db_connection()
        cursor = conn.execute('INSERT INTO queue (name, seat, room, timestamp, ip_address) VALUES (?, ?, ?, ?, ?)',
                       (name, seat, room, datetime.now(), client_ip))
        conn.commit()
        new_id = cursor.lastrowid
        conn.close()

        session['my_ticket_id'] = new_id

    return redirect(url_for('index'))

@app.route('/student/reset')
def student_reset():
    session.pop('student_name', None)
    session.pop('student_seat', None)
    return redirect(url_for('index'))

@app.route('/cancel', methods=['POST'])
def cancel():
    ticket_id = session.get('my_ticket_id')
    if ticket_id:
        client_ip = get_client_ip()
        audit_logger.info(f"{client_ip} | CANCEL | Ticket: {ticket_id}")
        conn = get_db_connection()
        conn.execute('DELETE FROM queue WHERE id = ?', (ticket_id,))
        conn.commit()
        conn.close()
        session.pop('my_ticket_id', None)
    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        # Get the input password
        input_password = request.form.get('password')

        # 1. Get the real hash from the Environment (Safety Net: default to None)
        stored_hash = os.environ.get('TA_PASSWORD_HASH')

        # 2. Secure Comparison
        # check_password_hash(hash, password) handles the unscrambling safely.
        # We also check if stored_hash exists to prevent errors if you forget to set it.
        if stored_hash and input_password and check_password_hash(stored_hash, input_password):
            session['is_ta'] = True
            return redirect(url_for('index'))


        # Optional: Add a flash message here for "Invalid Password"

    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/resolve/<int:ticket_id>', methods=['POST'])
def resolve(ticket_id):
    if not session.get('is_ta'):
        return "Unauthorized", 403
    conn = get_db_connection()
    conn.execute('DELETE FROM queue WHERE id = ?', (ticket_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

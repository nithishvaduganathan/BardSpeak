import os
import sqlite3
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, send_file
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, date
import json
from gemini import analyze_sentiment, analyze_communication_practice
import random
import io
from pydub import AudioSegment
import speech_recognition as sr
# Optional PDF generation for certificates
try:
    from reportlab.pdfgen import canvas
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import cm
    REPORTLAB_AVAILABLE = True
except Exception:
    REPORTLAB_AVAILABLE = False
try:
    from gtts import gTTS
except Exception:
    gTTS = None

app = Flask(__name__)
app.secret_key = os.environ.get('SESSION_SECRET', 'shakespeare-club-secret-key')

# Optional: Configure FFmpeg/FFprobe for pydub on Windows via env vars
FFMPEG_BIN = os.environ.get('FFMPEG_BIN')
FFPROBE_BIN = os.environ.get('FFPROBE_BIN')
if FFMPEG_BIN:
    AudioSegment.converter = FFMPEG_BIN
if FFPROBE_BIN:
    AudioSegment.ffprobe = FFPROBE_BIN

# Database initialization for gamified app
def init_db():
    conn = sqlite3.connect('shakespeare_club_gamified.db')
    c = conn.cursor()
    
    # Users table (simplified registration)
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        register_number TEXT UNIQUE NOT NULL,
        department TEXT NOT NULL,
        total_points INTEGER DEFAULT 0,
        current_streak INTEGER DEFAULT 0,
        best_streak INTEGER DEFAULT 0,
        badges TEXT DEFAULT '[]',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Admins table
    c.execute('''CREATE TABLE IF NOT EXISTS admins (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Content tables for each module
    c.execute('''CREATE TABLE IF NOT EXISTS biographies (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        person_name TEXT NOT NULL,
        content TEXT NOT NULL,
        profession TEXT NOT NULL,
        created_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (created_by) REFERENCES admins (id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS daily_quotes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        quote TEXT NOT NULL,
        author TEXT,
        posted_by INTEGER NOT NULL,
        department TEXT NOT NULL,
        post_date DATE NOT NULL,
        is_featured BOOLEAN DEFAULT FALSE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (posted_by) REFERENCES users (id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS listening_content (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        audio_file TEXT NOT NULL,
        transcript TEXT NOT NULL,
        robot_character TEXT DEFAULT 'boy',
        created_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (created_by) REFERENCES admins (id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS observation_content (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        video_url TEXT NOT NULL,
        questions TEXT NOT NULL,
        correct_answers TEXT NOT NULL,
        created_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (created_by) REFERENCES admins (id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS writing_topics (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        topic TEXT NOT NULL,
        description TEXT,
        created_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (created_by) REFERENCES admins (id)
    )''')
    
    # Tasks table for admin-assigned tasks visible on student dashboard
    c.execute('''CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        description TEXT,
        department TEXT DEFAULT 'ALL',
        due_date DATE,
        is_active BOOLEAN DEFAULT TRUE,
        created_by INTEGER,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        module_type TEXT,
        content_id INTEGER,
        FOREIGN KEY (created_by) REFERENCES admins (id)
    )''')

    # Ensure new columns exist on older databases
    existing_cols = [r[1] for r in c.execute('PRAGMA table_info(tasks)').fetchall()]
    if 'module_type' not in existing_cols:
        try:
            c.execute('ALTER TABLE tasks ADD COLUMN module_type TEXT')
        except Exception:
            pass
    if 'content_id' not in existing_cols:
        try:
            c.execute('ALTER TABLE tasks ADD COLUMN content_id INTEGER')
        except Exception:
            pass
    
    # User activities and completions
    c.execute('''CREATE TABLE IF NOT EXISTS user_completions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        module_type TEXT NOT NULL,
        content_id INTEGER NOT NULL,
        score INTEGER NOT NULL,
        points_earned INTEGER NOT NULL,
        completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS user_streaks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        streak_date DATE NOT NULL,
        modules_completed INTEGER DEFAULT 0,
        points_earned INTEGER DEFAULT 0,
        FOREIGN KEY (user_id) REFERENCES users (id)
    )''')
    
    # Track speaking attempts to enforce limit
    c.execute('''CREATE TABLE IF NOT EXISTS speaking_attempts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        bio_id INTEGER NOT NULL,
        attempt_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users (id),
        FOREIGN KEY (bio_id) REFERENCES biographies (id)
    )''')
    
    # Insert default admin
    c.execute("SELECT * FROM admins WHERE username = 'admin'")
    if not c.fetchone():
        admin_password_hash = generate_password_hash('admin123')
        c.execute("INSERT INTO admins (username, password_hash) VALUES (?, ?)", 
                 ('admin', admin_password_hash))
        admin_id = c.lastrowid
        
        # Insert sample content
        sample_biographies = [
            ("MS Dhoni - The Captain Cool", "Mahendra Singh Dhoni", 
             "Mahendra Singh Dhoni, known as Captain Cool, is one of the greatest cricket captains in history. Born on July 7, 1981, in Ranchi, Jharkhand, Dhoni rose from a small town to lead India to victory in the 2007 T20 World Cup, 2011 Cricket World Cup, and 2013 Champions Trophy. His calm demeanor under pressure and lightning-fast wicket-keeping skills made him a legend. Dhoni's leadership style was unique - he led by example, never panicked, and always believed in his team. Even in the most challenging situations, he maintained his composure and made strategic decisions that turned matches around.", 
             "Cricketer", admin_id),
            ("Dr. APJ Abdul Kalam - The Missile Man", "Dr. APJ Abdul Kalam",
             "Dr. Avul Pakir Jainulabdeen Abdul Kalam, known as the Missile Man of India, was born on October 15, 1931, in Rameswaram, Tamil Nadu. From humble beginnings selling newspapers to becoming India's 11th President, Dr. Kalam's journey is truly inspiring. He played a pivotal role in India's space and missile programs, leading projects like Agni and Prithvi missiles. His vision for India as a developed nation by 2020 motivated millions. Dr. Kalam was not just a scientist but also a teacher who loved interacting with students. His simplicity, dedication to education, and unwavering belief in the power of dreams made him the People's President.",
             "Scientist", admin_id)
        ]
        
        for title, name, content, profession, created_by in sample_biographies:
            c.execute("INSERT INTO biographies (title, person_name, content, profession, created_by) VALUES (?, ?, ?, ?, ?)",
                     (title, name, content, profession, created_by))
        
        # Sample listening content
        sample_listening = [
            ("Robot Greeting", "audio_greeting.mp3", 
             "Hello there! Welcome to the Shakespeare Club Communication App. I am your friendly learning companion. Today we will practice listening skills together. Are you ready to begin this exciting journey of improving your English communication? Let's start with something fun and educational!",
             "boy", admin_id),
            ("Daily Motivation", "audio_motivation.mp3",
             "Good morning, dear students! Every day is a new opportunity to learn something amazing. Remember, communication is not just about speaking - it's about connecting with others, sharing ideas, and building relationships. Practice makes perfect, so keep working on your skills. You are capable of achieving great things!",
             "girl", admin_id)
        ]
        
        for title, audio_file, transcript, robot_character, created_by in sample_listening:
            c.execute("INSERT INTO listening_content (title, audio_file, transcript, robot_character, created_by) VALUES (?, ?, ?, ?, ?)",
                     (title, audio_file, transcript, robot_character, created_by))
        
        # Sample observation content
        sample_observation = [
            ("Success Mindset", "https://www.youtube.com/watch?v=motivational1",
             "What are the key points mentioned about achieving success? List three important qualities discussed in the video.",
             "Hard work, Perseverance, Positive attitude", admin_id),
            ("Communication Skills", "https://www.youtube.com/watch?v=communication1",
             "According to the video, what makes effective communication? Name two important elements.",
             "Active listening, Clear expression", admin_id)
        ]
        
        for title, video_url, questions, answers, created_by in sample_observation:
            c.execute("INSERT INTO observation_content (title, video_url, questions, correct_answers, created_by) VALUES (?, ?, ?, ?, ?)",
                     (title, video_url, questions, answers, created_by))
        
        # Sample writing topics
        sample_topics = [
            ("My Dreams and Aspirations", "Write about your future goals and how you plan to achieve them.", admin_id),
            ("The Importance of Communication", "Explain why good communication skills are essential in today's world.", admin_id),
            ("A Person Who Inspires Me", "Describe someone who motivates you and explain why they are your inspiration.", admin_id)
        ]
        
        for topic, description, created_by in sample_topics:
            c.execute("INSERT INTO writing_topics (topic, description, created_by) VALUES (?, ?, ?)",
                     (topic, description, created_by))
    
    conn.commit()
    conn.close()

def get_db_connection():
    conn = sqlite3.connect('shakespeare_club_gamified.db')
    conn.row_factory = sqlite3.Row
    return conn

def calculate_badge_progress(user_id):
    """Calculate badges based on user achievements"""
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
    completions = conn.execute('SELECT * FROM user_completions WHERE user_id = ?', (user_id,)).fetchall()
    conn.close()
    
    badges = []
    if user['total_points'] >= 100:
        badges.append("Century Scorer")
    if user['best_streak'] >= 7:
        badges.append("Week Warrior")
    if user['best_streak'] >= 30:
        badges.append("Monthly Master")
    if len(completions) >= 10:
        badges.append("Practice Champion")
    if len(completions) >= 50:
        badges.append("Communication Expert")
    
    # Update badges in database
    conn = get_db_connection()
    conn.execute('UPDATE users SET badges = ? WHERE id = ?', (json.dumps(badges), user_id))
    conn.commit()
    conn.close()
    
    return badges

def is_certificate_ready(user_id):
    """Eligibility: at least one completion in each module: speaking, listening, writing, observation"""
    conn = get_db_connection()
    rows = conn.execute('''
        SELECT module_type, COUNT(*) as c
        FROM user_completions
        WHERE user_id = ? AND module_type IN ('speaking','listening','writing','observation')
        GROUP BY module_type
    ''', (user_id,)).fetchall()
    conn.close()
    have = {r['module_type'] for r in rows if r['c'] > 0}
    required = {'speaking','listening','writing','observation'}
    return required.issubset(have)

@app.route('/')
def index():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        register_number = request.form['register_number']
        department = request.form['department']
        
        conn = get_db_connection()
        try:
            conn.execute('''INSERT INTO users (username, register_number, department)
                           VALUES (?, ?, ?)''',
                        (username, register_number, department))
            conn.commit()
            
            # Get the new user
            user = conn.execute('SELECT * FROM users WHERE register_number = ?', (register_number,)).fetchone()
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['department'] = user['department']
            
            flash('Welcome to Shakespeare Club! Your communication journey begins now! 🎭')
            return redirect(url_for('dashboard'))
        except sqlite3.IntegrityError:
            flash('Username or register number already exists!')
        finally:
            conn.close()
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        register_number = request.form['register_number']
        
        conn = get_db_connection()
        user = conn.execute('SELECT * FROM users WHERE register_number = ?', (register_number,)).fetchone()
        conn.close()
        
        if user:
            session['user_id'] = user['id']
            session['username'] = user['username']
            session['department'] = user['department']
            flash(f'Welcome back, {user["username"]}! Ready for more communication practice? 🌟')
            return redirect(url_for('dashboard'))
        else:
            flash('Register number not found!')
    
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    # Get user stats
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    
    # Get recent completions
    recent_activities = conn.execute('''
        SELECT * FROM user_completions 
        WHERE user_id = ? 
        ORDER BY completed_at DESC 
        LIMIT 5
    ''', (session['user_id'],)).fetchall()
    
    # Get today's featured quote
    today = date.today()
    featured_quote = conn.execute('''
        SELECT dq.*, u.username, u.department 
        FROM daily_quotes dq 
        JOIN users u ON dq.posted_by = u.id 
        WHERE dq.post_date = ? AND dq.is_featured = TRUE 
        ORDER BY dq.created_at ASC 
        LIMIT 1
    ''', (today,)).fetchone()
    
    # Calculate badges
    badges = calculate_badge_progress(session['user_id'])
    
    # Get active tasks for user's department or ALL
    tasks = conn.execute('''
        SELECT * FROM tasks 
        WHERE is_active = TRUE 
          AND (department = 'ALL' OR department = ?) 
        ORDER BY 
          CASE WHEN due_date IS NULL THEN 1 ELSE 0 END,
          due_date ASC,
          created_at DESC
        LIMIT 10
    ''', (session['department'],)).fetchall()

    conn.close()
    
    certificate_ready = is_certificate_ready(session['user_id'])
    return render_template('dashboard.html', 
                         user=user, 
                         activities=recent_activities, 
                         featured_quote=featured_quote,
                         badges=badges,
                         tasks=tasks,
                         certificate_ready=certificate_ready)

@app.route('/speaking')
def speaking_module():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    # Get available biographies
    biographies = conn.execute('SELECT * FROM biographies ORDER BY created_at DESC').fetchall()
    
    # Get completed biographies
    completed = conn.execute('''
        SELECT content_id FROM user_completions 
        WHERE user_id = ? AND module_type = "speaking"
    ''', (session['user_id'],)).fetchall()
    
    completed_ids = [row['content_id'] for row in completed]
    
    conn.close()
    
    return render_template('speaking.html', biographies=biographies, completed_ids=completed_ids)

@app.route('/speaking/<int:bio_id>')
def speaking_practice(bio_id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    # Check if already completed
    completed = conn.execute('''
        SELECT * FROM user_completions 
        WHERE user_id = ? AND module_type = "speaking" AND content_id = ?
    ''', (session['user_id'], bio_id)).fetchone()
    
    if completed:
        flash('You have already completed this speaking practice! ✅')
        return redirect(url_for('speaking_module'))
    
    biography = conn.execute('SELECT * FROM biographies WHERE id = ?', (bio_id,)).fetchone()
    conn.close()
    
    if not biography:
        flash('Biography not found!')
        return redirect(url_for('speaking_module'))
    
    return render_template('speaking_practice.html', biography=biography)

@app.route('/submit_speaking', methods=['POST'])
def submit_speaking():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    bio_id = request.form['bio_id']
    recorded_text = request.form['recorded_text']
    
    conn = get_db_connection()
    
    # Check if already completed this practice
    existing = conn.execute('''
        SELECT * FROM user_completions 
        WHERE user_id = ? AND module_type = "speaking" AND content_id = ?
    ''', (session['user_id'], bio_id)).fetchone()
    
    if existing:
        conn.close()
        flash('🚫 You have already completed this practice! Try a different one.')
        return redirect(url_for('speaking_module'))
    
    biography = conn.execute('SELECT * FROM biographies WHERE id = ?', (bio_id,)).fetchone()
    
    try:
        # Use Gemini AI for real analysis
        sentiment_result = analyze_sentiment(recorded_text)
        detailed_feedback = analyze_communication_practice(recorded_text, 'speaking')
        
        # Calculate similarity percentage with AI enhancement
        original_words = set(biography['content'].lower().split())
        user_words = set(recorded_text.lower().split())
        similarity = len(original_words.intersection(user_words)) / max(len(original_words), 1) * 100
        
        # Award 10 points for completion, bonus for high performance
        points_earned = 10
        if similarity >= 80 and sentiment_result.rating >= 4:
            points_earned = 15  # Bonus for excellent performance
        elif similarity >= 60 or sentiment_result.rating >= 3:
            points_earned = 12  # Good effort bonus
        
        final_score = min(100, similarity + sentiment_result.rating * 10)
        
    except Exception as e:
        # Fallback if AI fails
        original_words = biography['content'].lower().split()
        user_words = recorded_text.lower().split()
        matching_words = sum(1 for word in user_words if word in original_words)
        similarity = (matching_words / len(original_words)) * 100 if original_words else 0
        points_earned = 10 if similarity >= 70 else 8
        final_score = similarity
        detailed_feedback = f"Analysis completed with basic scoring. AI unavailable: {str(e)}"
    
    # Save completion
    conn.execute('''INSERT INTO user_completions 
                   (user_id, module_type, content_id, score, points_earned)
                   VALUES (?, ?, ?, ?, ?)''',
                (session['user_id'], 'speaking', bio_id, final_score, points_earned))
    
    # Update user points
    conn.execute('UPDATE users SET total_points = total_points + ? WHERE id = ?',
                (points_earned, session['user_id']))
    
    conn.commit()
    conn.close()
    
    # Update user streak and points (use a fresh connection)
    conn2 = get_db_connection()
    today = date.today()
    streak_record = conn2.execute('''
        SELECT * FROM user_streaks 
        WHERE user_id = ? AND streak_date = ?
    ''', (session['user_id'], today)).fetchone()
    
    if not streak_record:
        # First task today
        conn2.execute('''INSERT INTO user_streaks 
                       (user_id, streak_date, modules_completed, points_earned)
                       VALUES (?, ?, 1, ?)''',
                    (session['user_id'], today, points_earned))
        
        # Update current streak
        yesterday = date.today().replace(day=date.today().day-1) if date.today().day > 1 else None
        if yesterday:
            yesterday_record = conn2.execute('''
                SELECT * FROM user_streaks 
                WHERE user_id = ? AND streak_date = ?
            ''', (session['user_id'], yesterday)).fetchone()
            
            if yesterday_record:
                conn2.execute('UPDATE users SET current_streak = current_streak + 1 WHERE id = ?',
                           (session['user_id'],))
            else:
                conn2.execute('UPDATE users SET current_streak = 1 WHERE id = ?',
                           (session['user_id'],))
        else:
            conn2.execute('UPDATE users SET current_streak = 1 WHERE id = ?',
                       (session['user_id'],))
    
    # Update best streak
    current_user = conn2.execute('SELECT current_streak FROM users WHERE id = ?', 
                               (session['user_id'],)).fetchone()
    conn2.execute('''UPDATE users SET best_streak = MAX(best_streak, current_streak) 
                   WHERE id = ?''', (session['user_id'],))
    
    conn2.commit()
    conn2.close()
    
    success_data = {
        'points': points_earned,
        'similarity': similarity,
        'celebration': similarity >= 70,
        'current_streak': current_user['current_streak'] if current_user else 1
    }
    
    return jsonify(success_data)

@app.route('/submit_speaking_audio', methods=['POST'])
def submit_speaking_audio():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    bio_id = request.form.get('bio_id')
    audio_file = request.files.get('audio')
    if not bio_id or not audio_file:
        return jsonify({'error': 'Missing audio or bio_id'}), 400
    
    # Enforce attempts: max 3 per user per bio per day
    conn_attempts = get_db_connection()
    today = date.today()
    attempt_count = conn_attempts.execute('''
        SELECT COUNT(*) AS c FROM speaking_attempts
        WHERE user_id = ? AND bio_id = ? AND DATE(attempt_at) = DATE(?)
    ''', (session['user_id'], bio_id, today)).fetchone()['c']
    if attempt_count >= 10:
        conn_attempts.close()
        return jsonify({'error': 'Attempt limit reached. You have already tried 3 times today.'}), 429
    # Record this attempt regardless of success
    conn_attempts.execute('''INSERT INTO speaking_attempts (user_id, bio_id) VALUES (?, ?)''',
                          (session['user_id'], bio_id))
    conn_attempts.commit()
    conn_attempts.close()

    # Prefer: accept WAV directly. Fallback: convert using pydub if not WAV.
    raw = audio_file.read()
    wav_buf = None
    try:
        filename = (audio_file.filename or '').lower()
        content_type = (audio_file.mimetype or '').lower()
        src_buf = io.BytesIO(raw)
        src_buf.seek(0)
        # If client uploaded WAV (our new default), try using it directly
        if filename.endswith('.wav') or 'wav' in content_type:
            wav_buf = src_buf
        else:
            # Try to treat it as WAV directly (some browsers may already produce PCM WAV)
            try:
                with sr.AudioFile(src_buf) as _:
                    pass
                wav_buf = src_buf
            except Exception:
                wav_buf = None
        # If still not WAV, convert using pydub (requires ffmpeg)
        if wav_buf is None:
            segment = AudioSegment.from_file(io.BytesIO(raw))
            out = io.BytesIO()
            segment.set_frame_rate(16000).set_channels(1).export(out, format='wav')
            out.seek(0)
            wav_buf = out
    except Exception as e:
        hint = (' Ensure FFmpeg is installed and available in PATH, or set env vars '
                'FFMPEG_BIN (path to ffmpeg.exe) and FFPROBE_BIN (path to ffprobe.exe). '
                'Download: https://www.gyan.dev/ffmpeg/builds/')
        return jsonify({'error': f'Audio processing failed: {str(e)}.{hint}'}), 400
    
    # Transcribe using SpeechRecognition (Google API)
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(wav_buf) as source:
            audio_data = recognizer.record(source)
        recorded_text = recognizer.recognize_google(audio_data)
    except Exception as e:
        return jsonify({'error': f'Speech-to-text failed: {str(e)}'}), 400
    
    # Now reuse the scoring logic from submit_speaking
    conn = get_db_connection()
    # Check duplicate completion
    existing = conn.execute('''
        SELECT * FROM user_completions 
        WHERE user_id = ? AND module_type = "speaking" AND content_id = ?
    ''', (session['user_id'], bio_id)).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': 'Already completed'}), 409
    
    biography = conn.execute('SELECT * FROM biographies WHERE id = ?', (bio_id,)).fetchone()
    if not biography:
        conn.close()
        return jsonify({'error': 'Biography not found'}), 404
    
    try:
        sentiment_result = analyze_sentiment(recorded_text)
        detailed_feedback = analyze_communication_practice(recorded_text, 'speaking')
        original_words = set(biography['content'].lower().split())
        user_words = set(recorded_text.lower().split())
        similarity = len(original_words.intersection(user_words)) / max(len(original_words), 1) * 100
        points_earned = 10
        if similarity >= 80 and sentiment_result.rating >= 4:
            points_earned = 15
        elif similarity >= 60 or sentiment_result.rating >= 3:
            points_earned = 12
        final_score = min(100, similarity + sentiment_result.rating * 10)
    except Exception:
        original_words = biography['content'].lower().split()
        user_words = recorded_text.lower().split()
        matching_words = sum(1 for word in user_words if word in original_words)
        similarity = (matching_words / len(original_words)) * 100 if original_words else 0
        points_earned = 10 if similarity >= 70 else 8
        final_score = similarity
    
    # Save completion and points
    conn.execute('''INSERT INTO user_completions 
                   (user_id, module_type, content_id, score, points_earned)
                   VALUES (?, ?, ?, ?, ?)''',
                (session['user_id'], 'speaking', bio_id, final_score, points_earned))
    conn.execute('UPDATE users SET total_points = total_points + ? WHERE id = ?',
                (points_earned, session['user_id']))
    conn.commit()
    conn.close()
    
    # Update streaks using fresh connection
    conn2 = get_db_connection()
    today = date.today()
    streak_record = conn2.execute('''
        SELECT * FROM user_streaks 
        WHERE user_id = ? AND streak_date = ?
    ''', (session['user_id'], today)).fetchone()
    if not streak_record:
        conn2.execute('''INSERT INTO user_streaks 
                       (user_id, streak_date, modules_completed, points_earned)
                       VALUES (?, ?, 1, ?)''',
                    (session['user_id'], today, points_earned))
        conn2.execute('UPDATE users SET current_streak = current_streak + 1 WHERE id = ?',
                     (session['user_id'],))
    conn2.execute('''UPDATE users SET best_streak = MAX(best_streak, current_streak) 
                   WHERE id = ?''', (session['user_id'],))
    conn2.commit()
    conn2.close()
    
    return jsonify({
        'points': points_earned,
        'similarity': similarity,
        'celebration': similarity >= 70,
        'transcript': recorded_text
    })

@app.route('/writing')
def writing_module():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    # Get today's quotes by department
    today = date.today()
    department_quotes = conn.execute('''
        SELECT dq.*, u.username 
        FROM daily_quotes dq 
        JOIN users u ON dq.posted_by = u.id 
        WHERE dq.post_date = ? 
        ORDER BY dq.department, dq.created_at ASC
    ''', (today,)).fetchall()
    
    # Check if user already posted today
    user_posted_today = conn.execute('''
        SELECT * FROM daily_quotes 
        WHERE posted_by = ? AND post_date = ?
    ''', (session['user_id'], today)).fetchone()
    
    # Get available writing topics
    topics = conn.execute('SELECT * FROM writing_topics ORDER BY created_at DESC').fetchall()
    
    conn.close()
    
    return render_template('writing.html', 
                         department_quotes=department_quotes,
                         user_posted_today=user_posted_today,
                         topics=topics)

@app.route('/submit_quote', methods=['POST'])
def submit_quote():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    quote = request.form['quote']
    author = request.form['author']
    
    conn = get_db_connection()
    today = date.today()
    
    # Check if user already posted today
    existing = conn.execute('''
        SELECT * FROM daily_quotes 
        WHERE posted_by = ? AND post_date = ?
    ''', (session['user_id'], today)).fetchone()
    
    if existing:
        flash('You already posted a quote today!')
        return redirect(url_for('writing_module'))
    
    # Check if this is the first quote from this department today
    dept_quotes_today = conn.execute('''
        SELECT COUNT(*) as count FROM daily_quotes dq
        JOIN users u ON dq.posted_by = u.id
        WHERE u.department = ? AND dq.post_date = ?
    ''', (session['department'], today)).fetchone()
    
    is_first = dept_quotes_today['count'] == 0
    points_earned = 15 if is_first else 10
    
    # Insert quote
    conn.execute('''INSERT INTO daily_quotes 
                   (quote, author, posted_by, department, post_date, is_featured)
                   VALUES (?, ?, ?, ?, ?, ?)''',
                (quote, author, session['user_id'], session['department'], today, is_first))
    
    # Save completion
    conn.execute('''INSERT INTO user_completions 
                   (user_id, module_type, content_id, score, points_earned)
                   VALUES (?, ?, ?, ?, ?)''',
                (session['user_id'], 'writing', 0, 100, points_earned))
    
    # Update user points
    conn.execute('UPDATE users SET total_points = total_points + ? WHERE id = ?',
                (points_earned, session['user_id']))
    
    conn.commit()
    conn.close()
    
    if is_first:
        flash('🎉 Congratulations! You are the first from your department to post today! You earned 15 points!')
    else:
        flash(f'Great quote! You earned {points_earned} points! 📝')
    
    return redirect(url_for('writing_module'))

@app.route('/submit_writing', methods=['POST'])
def submit_writing():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    quote_id = request.form['quote_id']
    user_response = request.form['user_response']
    
    conn = get_db_connection()
    
    # Check if already completed this practice
    existing = conn.execute('''
        SELECT * FROM user_completions 
        WHERE user_id = ? AND module_type = "writing" AND content_id = ?
    ''', (session['user_id'], quote_id)).fetchone()
    
    if existing:
        conn.close()
        flash('🚫 You have already completed this writing practice! Try a different quote.')
        return redirect(url_for('writing_module'))
    
    quote = conn.execute('SELECT * FROM daily_quotes WHERE id = ?', (quote_id,)).fetchone()
    
    try:
        # Use Gemini AI for real writing analysis
        sentiment_result = analyze_sentiment(user_response)
        detailed_feedback = analyze_communication_practice(user_response, 'writing')
        
        # Calculate comprehensive writing score
        word_count = len(user_response.split())
        depth_score = min(100, word_count * 1.5)  # Reward substantial responses
        quality_score = sentiment_result.rating * 20  # Convert to percentage
        final_score = (depth_score + quality_score) / 2
        
        # Award 10 points for completion, bonus for exceptional writing
        points_earned = 10
        if word_count >= 100 and sentiment_result.rating >= 4:
            points_earned = 15  # Excellent writing bonus
        elif word_count >= 75 or sentiment_result.rating >= 3:
            points_earned = 12  # Good writing bonus
        
    except Exception as e:
        # Fallback scoring
        word_count = len(user_response.split())
        final_score = min(100, word_count * 2)
        points_earned = 10 if word_count >= 50 else 8
        detailed_feedback = f"Writing evaluated with basic scoring. AI unavailable: {str(e)}"
    
    # Save completion
    conn.execute('''INSERT INTO user_completions 
                   (user_id, module_type, content_id, score, points_earned)
                   VALUES (?, ?, ?, ?, ?)''',
                (session['user_id'], 'writing', quote_id, final_score, points_earned))
    
    # Update user points
    conn.execute('UPDATE users SET total_points = total_points + ? WHERE id = ?',
                (points_earned, session['user_id']))
    
    conn.commit()
    conn.close()
    
    flash(f'🎉 Writing practice completed! Points earned: {points_earned} | Score: {final_score:.1f}%')
    return redirect(url_for('writing_module'))

@app.route('/listening')
def listening_module():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    # Get available listening content
    listening_items = conn.execute('SELECT * FROM listening_content ORDER BY created_at DESC').fetchall()
    
    # Get completed items
    completed = conn.execute('''
        SELECT content_id FROM user_completions 
        WHERE user_id = ? AND module_type = "listening"
    ''', (session['user_id'],)).fetchall()
    
    completed_ids = [row['content_id'] for row in completed]
    
    conn.close()
    
    return render_template('listening.html', listening_items=listening_items, completed_ids=completed_ids)

@app.route('/listening/<int:content_id>')
def listening_practice(content_id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    # Check if already completed
    completed = conn.execute('''
        SELECT * FROM user_completions 
        WHERE user_id = ? AND module_type = "listening" AND content_id = ?
    ''', (session['user_id'], content_id)).fetchone()
    
    if completed:
        flash('You have already completed this listening practice! ✅')
        return redirect(url_for('listening_module'))
    
    content = conn.execute('SELECT * FROM listening_content WHERE id = ?', (content_id,)).fetchone()
    conn.close()
    
    if not content:
        flash('Content not found!')
        return redirect(url_for('listening_module'))
    
    return render_template('listening_practice.html', content=content)

@app.route('/submit_listening', methods=['POST'])
def submit_listening():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    content_id = request.form['content_id']
    user_input = request.form['user_input']
    
    conn = get_db_connection()
    
    # Check if already completed this practice
    existing = conn.execute('''
        SELECT * FROM user_completions 
        WHERE user_id = ? AND module_type = "listening" AND content_id = ?
    ''', (session['user_id'], content_id)).fetchone()
    
    if existing:
        conn.close()
        flash('🚫 You have already completed this listening practice! Try a different one.')
        return redirect(url_for('listening_module'))
    
    content = conn.execute('SELECT * FROM listening_content WHERE id = ?', (content_id,)).fetchone()
    
    try:
        # Use Gemini AI for listening comprehension analysis
        sentiment_result = analyze_sentiment(user_input)
        detailed_feedback = analyze_communication_practice(user_input, 'listening')
        
        # Calculate accuracy with AI enhancement
        original_text = content['transcript'].lower().strip()
        user_text = user_input.lower().strip()
        
        # Word-level accuracy
        original_words = set(original_text.split())
        user_words = set(user_text.split())
        word_accuracy = len(original_words.intersection(user_words)) / max(len(original_words), 1) * 100
        
        # Combined scoring
        accuracy = min(100, (word_accuracy + sentiment_result.rating * 15) / 2)
        points_earned = 10 if accuracy >= 80 else 8
        
    except Exception as e:
        # Fallback accuracy calculation
        original_text = content['transcript'].lower().strip()
        user_text = user_input.lower().strip()
        accuracy = (100 if original_text == user_text else 
                   80 if len(user_text) > 0 and original_text in user_text else
                   60 if len(user_text) > 0 else 0)
        points_earned = 10 if accuracy >= 80 else 8
    
    # Save completion
    conn.execute('''INSERT INTO user_completions 
                   (user_id, module_type, content_id, score, points_earned)
                   VALUES (?, ?, ?, ?, ?)''',
                (session['user_id'], 'listening', content_id, accuracy, points_earned))
    
    # Update user points
    conn.execute('UPDATE users SET total_points = total_points + ? WHERE id = ?',
                (points_earned, session['user_id']))
    
    conn.commit()
    conn.close()
    
    # Update user streak and points
    today = date.today()
    streak_record = conn.execute('''
        SELECT * FROM user_streaks 
        WHERE user_id = ? AND streak_date = ?
    ''', (session['user_id'], today)).fetchone()
    
    if not streak_record:
        conn.execute('''INSERT INTO user_streaks 
                       (user_id, streak_date, modules_completed, points_earned)
                       VALUES (?, ?, 1, ?)''',
                    (session['user_id'], today, points_earned))
        conn.execute('UPDATE users SET current_streak = current_streak + 1 WHERE id = ?',
                   (session['user_id'],))
    
    # Update best streak
    conn.execute('''UPDATE users SET best_streak = MAX(best_streak, current_streak) 
                   WHERE id = ?''', (session['user_id'],))
    
    conn.commit()
    conn.close()
    
    success_data = {
        'points': points_earned,
        'accuracy': accuracy,
        'celebration': accuracy >= 80
    }
    
    return jsonify(success_data)

@app.route('/observation')
def observation_module():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    # Get available observation content
    observation_items = conn.execute('SELECT * FROM observation_content ORDER BY created_at DESC').fetchall()
    
    # Get completed items
    completed = conn.execute('''
        SELECT content_id FROM user_completions 
        WHERE user_id = ? AND module_type = "observation"
    ''', (session['user_id'],)).fetchall()
    
    completed_ids = [row['content_id'] for row in completed]
    
    conn.close()
    
    return render_template('observation.html', observation_items=observation_items, completed_ids=completed_ids)

@app.route('/observation/<int:content_id>')
def observation_practice(content_id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    conn = get_db_connection()
    
    # Check if already completed
    completed = conn.execute('''
        SELECT * FROM user_completions 
        WHERE user_id = ? AND module_type = "observation" AND content_id = ?
    ''', (session['user_id'], content_id)).fetchone()
    
    if completed:
        flash('You have already completed this observation practice! ✅')
        return redirect(url_for('observation_module'))
    
    content = conn.execute('SELECT * FROM observation_content WHERE id = ?', (content_id,)).fetchone()
    conn.close()
    
    if not content:
        flash('Content not found!')
        return redirect(url_for('observation_module'))
    
    return render_template('observation_practice.html', content=content)

@app.route('/submit_observation', methods=['POST'])
def submit_observation():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    
    content_id = request.form['content_id']
    user_answer = request.form['user_answer']
    
    conn = get_db_connection()
    
    # Check if already completed this practice
    existing = conn.execute('''
        SELECT * FROM user_completions 
        WHERE user_id = ? AND module_type = "observation" AND content_id = ?
    ''', (session['user_id'], content_id)).fetchone()
    
    if existing:
        conn.close()
        flash('🚫 You have already completed this observation practice! Try a different video.')
        return redirect(url_for('observation_module'))
    
    content = conn.execute('SELECT * FROM observation_content WHERE id = ?', (content_id,)).fetchone()
    
    try:
        # Use Gemini AI for observation analysis
        sentiment_result = analyze_sentiment(user_answer)
        detailed_feedback = analyze_communication_practice(user_answer, 'observation')
        
        # Check answer accuracy with AI enhancement
        correct_answers = content['correct_answers'].lower()
        user_answer_lower = user_answer.lower()
        
        # Basic accuracy + AI quality assessment
        base_accuracy = 100 if correct_answers in user_answer_lower else 70
        quality_boost = sentiment_result.rating * 5  # Up to 25 point boost
        accuracy = min(100, base_accuracy + quality_boost)
        
        # Award 10 points for completion, bonus for excellent answers
        points_earned = 10 if accuracy >= 90 else 8
        
    except Exception as e:
        # Fallback scoring
        correct_answers = content['correct_answers'].lower()
        user_answer_lower = user_answer.lower()
        accuracy = 100 if correct_answers in user_answer_lower else 70
        points_earned = 10 if accuracy == 100 else 8
    
    # Save completion
    conn.execute('''INSERT INTO user_completions 
                   (user_id, module_type, content_id, score, points_earned)
                   VALUES (?, ?, ?, ?, ?)''',
                (session['user_id'], 'observation', content_id, accuracy, points_earned))
    
    # Update user points
    conn.execute('UPDATE users SET total_points = total_points + ? WHERE id = ?',
                (points_earned, session['user_id']))
    
    conn.commit()
    conn.close()
    
    # Update user streak and points  
    today = date.today()
    streak_record = conn.execute('''
        SELECT * FROM user_streaks 
        WHERE user_id = ? AND streak_date = ?
    ''', (session['user_id'], today)).fetchone()
    
    if not streak_record:
        conn.execute('''INSERT INTO user_streaks 
                       (user_id, streak_date, modules_completed, points_earned)
                       VALUES (?, ?, 1, ?)''',
                    (session['user_id'], today, points_earned))
        conn.execute('UPDATE users SET current_streak = current_streak + 1 WHERE id = ?',
                   (session['user_id'],))
    
    # Update best streak
    conn.execute('''UPDATE users SET best_streak = MAX(best_streak, current_streak) 
                   WHERE id = ?''', (session['user_id'],))
    
    conn.commit()
    conn.close()
    
    success_data = {
        'points': points_earned,
        'accuracy': accuracy,
        'celebration': accuracy == 100
    }
    
    return jsonify(success_data)

@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db_connection()
        admin = conn.execute('SELECT * FROM admins WHERE username = ?', (username,)).fetchone()
        conn.close()
        
        if admin and check_password_hash(admin['password_hash'], password):
            session['admin_id'] = admin['id']
            session['admin_username'] = admin['username']
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials!')
    
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    
    stats = {
        'total_users': conn.execute('SELECT COUNT(*) FROM users').fetchone()[0],
        'total_completions': conn.execute('SELECT COUNT(*) FROM user_completions').fetchone()[0],
        'today_activities': conn.execute('SELECT COUNT(*) FROM user_completions WHERE DATE(completed_at) = DATE("now")').fetchone()[0]
    }
    
    # Recent activities
    recent_activities = conn.execute('''
        SELECT uc.*, u.username, u.department 
        FROM user_completions uc
        JOIN users u ON uc.user_id = u.id
        ORDER BY uc.completed_at DESC
        LIMIT 10
    ''').fetchall()
    
    conn.close()
    
    return render_template('admin_dashboard.html', stats=stats, activities=recent_activities)

# ---------- Admin: Add Content Routes ----------
from werkzeug.utils import secure_filename

UPLOAD_DIR = os.path.join('static', 'audio')
ALLOWED_AUDIO_EXTS = {'.mp3', '.wav', '.ogg', '.m4a', '.webm'}

def ensure_upload_dir():
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
    except Exception:
        pass

@app.route('/admin/speaking/new', methods=['GET', 'POST'])
def admin_add_speaking():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    if request.method == 'POST':
        person_name = request.form.get('person_name', '').strip()
        title = request.form.get('title', '').strip()
        profession = request.form.get('profession', '').strip() or 'Leader'
        content = request.form.get('content', '').strip()
        if not person_name or not content:
            flash('Person name and script are required')
        else:
            conn = get_db_connection()
            conn.execute('''INSERT INTO biographies (title, person_name, content, profession, created_by)
                            VALUES (?, ?, ?, ?, ?)''',
                         (title or f"About {person_name}", person_name, content, profession, session['admin_id']))
            conn.commit()
            conn.close()
            flash('Speaking topic added')
            return redirect(url_for('admin_add_speaking'))
    return render_template('admin_add_speaking.html')

@app.route('/admin/listening/new', methods=['GET', 'POST'])
def admin_add_listening():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        transcript = request.form.get('transcript', '').strip()
        robot_character = request.form.get('robot_character', 'boy')
        audio = request.files.get('audio_file')
        if not title or not transcript or not audio:
            flash('Title, audio file, and script are required')
        else:
            ensure_upload_dir()
            name = secure_filename(audio.filename)
            ext = os.path.splitext(name)[1].lower()
            if ext not in ALLOWED_AUDIO_EXTS:
                flash('Unsupported audio type. Allowed: mp3, wav, ogg, m4a, webm')
            else:
                filename = f"{int(datetime.now().timestamp())}_{name}"
                path = os.path.join(UPLOAD_DIR, filename)
                audio.save(path)
                conn = get_db_connection()
                conn.execute('''INSERT INTO listening_content (title, audio_file, transcript, robot_character, created_by)
                                VALUES (?, ?, ?, ?, ?)''',
                             (title, filename, transcript, robot_character, session['admin_id']))
                conn.commit()
                conn.close()
                flash('Listening content added')
                return redirect(url_for('admin_add_listening'))
    return render_template('admin_add_listening.html')

@app.route('/admin/observation/new', methods=['GET', 'POST'])
def admin_add_observation():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        video_url = request.form.get('video_url', '').strip()
        questions = request.form.get('questions', '').strip()
        correct_answers = request.form.get('correct_answers', '').strip()
        if not title or not video_url or not questions or not correct_answers:
            flash('All fields are required')
        else:
            conn = get_db_connection()
            conn.execute('''INSERT INTO observation_content (title, video_url, questions, correct_answers, created_by)
                            VALUES (?, ?, ?, ?, ?)''',
                         (title, video_url, questions, correct_answers, session['admin_id']))
            conn.commit()
            conn.close()
            flash('Observation content added')
            return redirect(url_for('admin_add_observation'))
    return render_template('admin_add_observation.html')

@app.route('/admin/writing/new', methods=['GET', 'POST'])
def admin_add_writing():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    if request.method == 'POST':
        topic = request.form.get('topic', '').strip()
        description = request.form.get('description', '').strip()
        if not topic:
            flash('Topic is required')
        else:
            conn = get_db_connection()
            conn.execute('''INSERT INTO writing_topics (topic, description, created_by)
                            VALUES (?, ?, ?)''',
                         (topic, description, session['admin_id']))
            conn.commit()
            conn.close()
            flash('Writing topic added')
            return redirect(url_for('admin_add_writing'))
    return render_template('admin_add_writing.html')

@app.route('/admin/tts', methods=['GET', 'POST'])
def admin_tts():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    error = None
    output_filename = None
    created_listening_id = None
    if request.method == 'POST':
        if gTTS is None:
            flash('gTTS is not installed. Please install it with: pip install gTTS', 'error')
            return redirect(url_for('admin_tts'))
        text = (request.form.get('text') or '').strip()
        lang = (request.form.get('lang') or 'en').strip()
        slow = True if request.form.get('slow') == 'on' else False
        make_listening = True if request.form.get('make_listening') == 'on' else False
        title = (request.form.get('title') or '').strip()
        robot_character = request.form.get('robot_character') or 'boy'
        if not text:
            flash('Please enter text to convert to audio.', 'error')
            return redirect(url_for('admin_tts'))
        try:
            ensure_upload_dir()
            ts = int(datetime.now().timestamp())
            output_filename = f"tts_{ts}.mp3"
            output_path = os.path.join(UPLOAD_DIR, output_filename)
            tts = gTTS(text=text, lang=lang, slow=slow)
            tts.save(output_path)
            flash(f'Audio generated successfully: {output_filename}', 'success')
            if make_listening and title:
                conn = get_db_connection()
                conn.execute('''INSERT INTO listening_content (title, audio_file, transcript, robot_character, created_by)
                                VALUES (?, ?, ?, ?, ?)''',
                             (title, output_filename, text, robot_character, session['admin_id']))
                conn.commit()
                created_listening_id = conn.execute('SELECT last_insert_rowid() as id').fetchone()['id']
                conn.close()
                flash('Listening content created from generated audio.', 'success')
        except Exception as e:
            error = str(e)
            flash(f'Failed to generate audio: {error}', 'error')
    return render_template('admin_tts.html', output_filename=output_filename, created_listening_id=created_listening_id)

@app.route('/admin/tasks', methods=['GET', 'POST'])
def admin_tasks():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    
    conn = get_db_connection()
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        department = request.form.get('department', 'ALL').strip() or 'ALL'
        due_date = request.form.get('due_date') or None
        is_active = 1 if request.form.get('is_active') == 'on' else 1  # default active
        module_type = request.form.get('module_type') or None
        content_id = request.form.get('content_id') or None
        if content_id:
            try:
                content_id = int(content_id)
            except ValueError:
                content_id = None
        
        if not title:
            flash('Task title is required')
        else:
            conn.execute('''INSERT INTO tasks (title, description, department, due_date, is_active, created_by, module_type, content_id)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                         (title, description, department, due_date, is_active, session['admin_id'], module_type, content_id))
            conn.commit()
            flash('Task added successfully')
            
    # List recent tasks
    tasks = conn.execute('''SELECT t.*, a.username AS admin_name FROM tasks t
                            LEFT JOIN admins a ON t.created_by = a.id
                            ORDER BY t.created_at DESC
                            LIMIT 50''').fetchall()

    # Load content lists for linking
    biographies = conn.execute('SELECT id, person_name AS name, title FROM biographies ORDER BY created_at DESC').fetchall()
    listening_items = conn.execute('SELECT id, title FROM listening_content ORDER BY created_at DESC').fetchall()
    observation_items = conn.execute('SELECT id, title FROM observation_content ORDER BY created_at DESC').fetchall()
    writing_topics = conn.execute('SELECT id, topic AS title FROM writing_topics ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('admin_tasks.html', tasks=tasks,
                           biographies=biographies,
                           listening_items=listening_items,
                           observation_items=observation_items,
                           writing_topics=writing_topics)

@app.route('/admin/tasks/<int:task_id>/edit', methods=['GET', 'POST'])
def admin_edit_task(task_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    conn = get_db_connection()
    task = conn.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
    if not task:
        conn.close()
        flash('Task not found')
        return redirect(url_for('admin_tasks'))
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        department = request.form.get('department', 'ALL').strip() or 'ALL'
        due_date = request.form.get('due_date') or None
        is_active = 1 if request.form.get('is_active') == 'on' else 0
        module_type = request.form.get('module_type') or None
        content_id = request.form.get('content_id') or None
        if content_id:
            try:
                content_id = int(content_id)
            except ValueError:
                content_id = None
        if not title:
            flash('Task title is required')
        else:
            conn.execute('''UPDATE tasks SET title=?, description=?, department=?, due_date=?, is_active=?, module_type=?, content_id=?
                            WHERE id = ?''',
                         (title, description, department, due_date, is_active, module_type, content_id, task_id))
            conn.commit()
            flash('Task updated')
            # reload task
            task = conn.execute('SELECT * FROM tasks WHERE id = ?', (task_id,)).fetchone()
    # content lists
    biographies = conn.execute('SELECT id, person_name AS name, title FROM biographies ORDER BY created_at DESC').fetchall()
    listening_items = conn.execute('SELECT id, title FROM listening_content ORDER BY created_at DESC').fetchall()
    observation_items = conn.execute('SELECT id, title FROM observation_content ORDER BY created_at DESC').fetchall()
    writing_topics = conn.execute('SELECT id, topic AS title FROM writing_topics ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('admin_task_edit.html', task=task,
                           biographies=biographies,
                           listening_items=listening_items,
                           observation_items=observation_items,
                           writing_topics=writing_topics)

@app.route('/admin/practices')
def admin_manage_practices():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    conn = get_db_connection()
    speaking = conn.execute('SELECT * FROM biographies ORDER BY created_at DESC').fetchall()
    listening = conn.execute('SELECT * FROM listening_content ORDER BY created_at DESC').fetchall()
    observation = conn.execute('SELECT * FROM observation_content ORDER BY created_at DESC').fetchall()
    conn.close()
    return render_template('admin_manage_practices.html', speaking=speaking, listening=listening, observation=observation)

@app.route('/admin/speaking/<int:bio_id>/edit', methods=['GET', 'POST'])
def admin_edit_speaking(bio_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    conn = get_db_connection()
    bio = conn.execute('SELECT * FROM biographies WHERE id = ?', (bio_id,)).fetchone()
    if not bio:
        conn.close()
        flash('Speaking passage not found', 'error')
        return redirect(url_for('admin_manage_practices'))
    if request.method == 'POST':
        person_name = request.form.get('person_name', '').strip()
        title = request.form.get('title', '').strip()
        profession = request.form.get('profession', 'Other').strip() or 'Other'
        content = request.form.get('content', '').strip()
        conn.execute('''UPDATE biographies SET person_name = ?, title = ?, profession = ?, content = ? WHERE id = ?''',
                     (person_name, title, profession, content, bio_id))
        conn.commit()
        conn.close()
        flash('Speaking passage updated', 'success')
        return redirect(url_for('admin_manage_practices'))
    conn.close()
    return render_template('admin_edit_speaking.html', bio=bio)

@app.route('/admin/speaking/<int:bio_id>/delete', methods=['POST'])
def admin_delete_speaking(bio_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM biographies WHERE id = ?', (bio_id,))
    conn.commit()
    conn.close()
    flash('Speaking passage removed', 'success')
    return redirect(url_for('admin_manage_practices'))

@app.route('/admin/listening/<int:content_id>/edit', methods=['GET', 'POST'])
def admin_edit_listening(content_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    conn = get_db_connection()
    item = conn.execute('SELECT * FROM listening_content WHERE id = ?', (content_id,)).fetchone()
    if not item:
        conn.close()
        flash('Listening content not found', 'error')
        return redirect(url_for('admin_manage_practices'))
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        audio_file = request.form.get('audio_file', '').strip() or item['audio_file']
        transcript = request.form.get('transcript', '').strip()
        robot_character = request.form.get('robot_character', 'boy').strip() or 'boy'
        conn.execute('''UPDATE listening_content SET title = ?, audio_file = ?, transcript = ?, robot_character = ? WHERE id = ?''',
                     (title, audio_file, transcript, robot_character, content_id))
        conn.commit()
        conn.close()
        flash('Listening content updated', 'success')
        return redirect(url_for('admin_manage_practices'))
    conn.close()
    return render_template('admin_edit_listening.html', item=item)

@app.route('/admin/listening/<int:content_id>/delete', methods=['POST'])
def admin_delete_listening(content_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM listening_content WHERE id = ?', (content_id,))
    conn.commit()
    conn.close()
    flash('Listening content removed', 'success')
    return redirect(url_for('admin_manage_practices'))

@app.route('/admin/observation/<int:obs_id>/edit', methods=['GET', 'POST'])
def admin_edit_observation(obs_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    conn = get_db_connection()
    item = conn.execute('SELECT * FROM observation_content WHERE id = ?', (obs_id,)).fetchone()
    if not item:
        conn.close()
        flash('Observation content not found', 'error')
        return redirect(url_for('admin_manage_practices'))
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        video_url = request.form.get('video_url', '').strip()
        questions = request.form.get('questions', '').strip()
        correct_answers = request.form.get('correct_answers', '').strip()
        conn.execute('''UPDATE observation_content SET title = ?, video_url = ?, questions = ?, correct_answers = ? WHERE id = ?''',
                     (title, video_url, questions, correct_answers, obs_id))
        conn.commit()
        conn.close()
        flash('Observation content updated', 'success')
        return redirect(url_for('admin_manage_practices'))
    conn.close()
    return render_template('admin_edit_observation.html', item=item)

@app.route('/admin/observation/<int:obs_id>/delete', methods=['POST'])
def admin_delete_observation(obs_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    conn = get_db_connection()
    conn.execute('DELETE FROM observation_content WHERE id = ?', (obs_id,))
    conn.commit()
    conn.close()
    flash('Observation content removed', 'success')
    return redirect(url_for('admin_manage_practices'))

@app.route('/leaderboard')
def leaderboard():
    conn = get_db_connection()
    
    # Get top users by points
    top_users = conn.execute('''
        SELECT username, department, total_points, current_streak, best_streak, badges
        FROM users 
        ORDER BY total_points DESC 
        LIMIT 10
    ''').fetchall()
    
    conn.close()
    
    return render_template('leaderboard.html', top_users=top_users)

# -------- Profile and Certificate Routes --------
@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    if request.method == 'POST':
        new_username = request.form.get('username', '').strip()
        new_department = request.form.get('department', '').strip()
        try:
            if new_username:
                conn.execute('UPDATE users SET username = ? WHERE id = ?', (new_username, session['user_id']))
                session['username'] = new_username
            if new_department:
                conn.execute('UPDATE users SET department = ? WHERE id = ?', (new_department, session['user_id']))
                session['department'] = new_department
            conn.commit()
            flash('Profile updated successfully', 'success')
            # refresh user
            user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
        except sqlite3.IntegrityError:
            flash('Username already taken. Please choose another.', 'error')
        finally:
            conn.close()
        return redirect(url_for('profile'))
    conn.close()
    return render_template('profile.html', user=user)

@app.route('/certificate')
def certificate_view():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    conn.close()
    eligible = is_certificate_ready(session['user_id'])
    today_str = datetime.now().strftime('%Y-%m-%d')
    return render_template('certificate.html', user=user, eligible=eligible, reportlab=REPORTLAB_AVAILABLE, today=today_str)

@app.route('/certificate/download')
def certificate_download():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    if not is_certificate_ready(session['user_id']):
        flash('Complete all modules (Speaking, Listening, Writing, Observation) to unlock your certificate.', 'warning')
        return redirect(url_for('certificate_view'))
    if not REPORTLAB_AVAILABLE:
        flash('PDF generator is not installed on the server. Use the Print Certificate option.', 'warning')
        return redirect(url_for('certificate_view'))
    # Generate PDF in-memory
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE id = ?', (session['user_id'],)).fetchone()
    conn.close()
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    # Header
    c.setFont('Helvetica-Bold', 24)
    c.drawCentredString(width/2, height - 3*cm, 'Certificate of Completion')
    c.setFont('Helvetica', 12)
    c.drawCentredString(width/2, height - 4*cm, 'Shakespeare Club - Communication Skills Program')
    # Recipient
    c.setFont('Helvetica-Bold', 18)
    c.drawCentredString(width/2, height - 7*cm, f"This certifies that {user['username']}")
    c.setFont('Helvetica', 12)
    c.drawCentredString(width/2, height - 8*cm, f"Department: {user['department']}")
    # Body
    c.drawCentredString(width/2, height - 10*cm, 'has successfully completed all practice modules:')
    c.drawCentredString(width/2, height - 11*cm, 'Speaking, Listening, Writing, and Observation')
    # Footer
    today_str = datetime.now().strftime('%Y-%m-%d')
    c.drawCentredString(width/2, 3*cm, f"Date: {today_str}")
    c.setFont('Helvetica-Oblique', 10)
    c.drawRightString(width - 2*cm, 2*cm, 'Shakespeare Club')
    c.showPage()
    c.save()
    buf.seek(0)
    filename = f"Certificate_{user['username']}.pdf"
    return send_file(buf, as_attachment=True, download_name=filename, mimetype='application/pdf')

# Help mobile browsers by explicitly allowing microphone via headers (useful in iframes/PWAs)
@app.after_request
def add_mic_permissions_headers(response):
    # Permissions-Policy replaces Feature-Policy in modern browsers
    response.headers['Permissions-Policy'] = "microphone=(self)"
    # For older browsers still reading Feature-Policy
    response.headers['Feature-Policy'] = "microphone 'self'"
    return response

@app.route('/logout')
def logout():
    session.clear()
    flash('Thanks for practicing! Come back soon! 👋')
    return redirect(url_for('index'))

if __name__ == '__main__':
    init_db()
    app.run(host='0.0.0.0', port=5000, debug=True)
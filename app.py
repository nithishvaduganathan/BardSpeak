# app.py (PostgreSQL / SQLAlchemy version)
import os
import io
import json
import random
from datetime import datetime, date, timedelta

from flask import (
    Flask, render_template, request, redirect, url_for, session,
    flash, jsonify, send_file
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

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

# Gemini AI helpers (kept as-is)
from gemini import analyze_sentiment, analyze_communication_practice

# Flask + SQLAlchemy
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, and_, or_, text

# -------------------------
# App and config
# -------------------------
app = Flask(__name__)
app.secret_key = os.environ.get('SESSION_SECRET', 'shakespeare-club-secret-key')

# Optional: Configure FFmpeg/FFprobe for pydub on Windows via env vars
FFMPEG_BIN = os.environ.get('FFMPEG_BIN')
FFPROBE_BIN = os.environ.get('FFPROBE_BIN')
if FFMPEG_BIN:
    AudioSegment.converter = FFMPEG_BIN
if FFPROBE_BIN:
    AudioSegment.ffprobe = FFPROBE_BIN

# Database config: use DATABASE_URL env var from Render
# Example (Render): postgres://<user>:<pw>@<host>:5432/bardspeak-db
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL',
    'postgresql://localhost/bardspeak-db'  # fallback (developer machine)
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# -------------------------
# Models (mirror previous SQLite schema)
# -------------------------
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    register_number = db.Column(db.String(150), unique=True, nullable=False)
    department = db.Column(db.String(150), nullable=False)
    total_points = db.Column(db.Integer, default=0)
    current_streak = db.Column(db.Integer, default=0)
    best_streak = db.Column(db.Integer, default=0)
    badges = db.Column(db.Text, default='[]')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Admin(db.Model):
    __tablename__ = 'admins'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(300), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Biography(db.Model):
    __tablename__ = 'biographies'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    person_name = db.Column(db.String(300), nullable=False)
    content = db.Column(db.Text, nullable=False)
    profession = db.Column(db.String(150), nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class DailyQuote(db.Model):
    __tablename__ = 'daily_quotes'
    id = db.Column(db.Integer, primary_key=True)
    quote = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(200))
    posted_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    department = db.Column(db.String(150), nullable=False)
    post_date = db.Column(db.Date, nullable=False)
    is_featured = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ListeningContent(db.Model):
    __tablename__ = 'listening_content'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    audio_file = db.Column(db.String(500), nullable=False)
    transcript = db.Column(db.Text, nullable=False)
    robot_character = db.Column(db.String(50), default='boy')
    created_by = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class ObservationContent(db.Model):
    __tablename__ = 'observation_content'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    video_url = db.Column(db.String(500), nullable=False)
    questions = db.Column(db.Text, nullable=False)
    correct_answers = db.Column(db.Text, nullable=False)
    created_by = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class WritingTopic(db.Model):
    __tablename__ = 'writing_topics'
    id = db.Column(db.Integer, primary_key=True)
    topic = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text)
    created_by = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class Task(db.Model):
    __tablename__ = 'tasks'
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(300), nullable=False)
    description = db.Column(db.Text)
    department = db.Column(db.String(100), default='ALL')
    due_date = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_by = db.Column(db.Integer, db.ForeignKey('admins.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    module_type = db.Column(db.String(100), nullable=True)
    content_id = db.Column(db.Integer, nullable=True)

class UserCompletion(db.Model):
    __tablename__ = 'user_completions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    module_type = db.Column(db.String(50), nullable=False)
    content_id = db.Column(db.Integer, nullable=False)
    score = db.Column(db.Integer, nullable=False)
    points_earned = db.Column(db.Integer, nullable=False)
    completed_at = db.Column(db.DateTime, default=datetime.utcnow)

class UserStreak(db.Model):
    __tablename__ = 'user_streaks'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    streak_date = db.Column(db.Date, nullable=False)
    modules_completed = db.Column(db.Integer, default=0)
    points_earned = db.Column(db.Integer, default=0)

class SpeakingAttempt(db.Model):
    __tablename__ = 'speaking_attempts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    bio_id = db.Column(db.Integer, db.ForeignKey('biographies.id'), nullable=False)
    attempt_at = db.Column(db.DateTime, default=datetime.utcnow)

# -------------------------
# One-time sample data initializer (mirrors previous init_db())
# -------------------------
def ensure_sample_data():
    """Create default admin and sample content if not present.
       This will run on first app start (db.create_all() will be called first).
    """
    # default admin
    admin = Admin.query.filter_by(username='admin').first()
    if not admin:
        admin = Admin(username='admin', password_hash=generate_password_hash('admin123'))
        db.session.add(admin)
        db.session.commit()

        # sample biographies
        sample_biographies = [
            ("MS Dhoni - The Captain Cool", "Mahendra Singh Dhoni",
             "Mahendra Singh Dhoni, known as Captain Cool, is one of the greatest cricket captains in history. Born on July 7, 1981, in Ranchi, Jharkhand, Dhoni rose from a small town to lead India to victory in the 2007 T20 World Cup, 2011 Cricket World Cup, and 2013 Champions Trophy. His calm demeanor under pressure and lightning-fast wicket-keeping skills made him a legend. Dhoni's leadership style was unique - he led by example, never panicked, and always believed in his team. Even in the most challenging situations, he maintained his composure and made strategic decisions that turned matches around.",
             "Cricketer"),
            ("Dr. APJ Abdul Kalam - The Missile Man", "Dr. APJ Abdul Kalam",
             "Dr. Avul Pakir Jainulabdeen Abdul Kalam, known as the Missile Man of India, was born on October 15, 1931, in Rameswaram, Tamil Nadu. From humble beginnings selling newspapers to becoming India's 11th President, Dr. Kalam's journey is truly inspiring. He played a pivotal role in India's space and missile programs, leading projects like Agni and Prithvi missiles. His vision for India as a developed nation by 2020 motivated millions. Dr. Kalam was not just a scientist but also a teacher who loved interacting with students. His simplicity, dedication to education, and unwavering belief in the power of dreams made him the People's President.",
             "Scientist")
        ]
        for title, name, content, profession in sample_biographies:
            bio = Biography(title=title, person_name=name, content=content, profession=profession, created_by=admin.id)
            db.session.add(bio)

        # sample listening content
        sample_listening = [
            ("Robot Greeting", "audio_greeting.mp3",
             "Hello there! Welcome to the Shakespeare Club Communication App. I am your friendly learning companion. Today we will practice listening skills together. Are you ready to begin this exciting journey of improving your English communication? Let's start with something fun and educational!",
             "boy"),
            ("Daily Motivation", "audio_motivation.mp3",
             "Good morning, dear students! Every day is a new opportunity to learn something amazing. Remember, communication is not just about speaking - it's about connecting with others, sharing ideas, and building relationships. Practice makes perfect, so keep working on your skills. You are capable of achieving great things!",
             "girl")
        ]
        for title, audio_file, transcript, robot_character in sample_listening:
            item = ListeningContent(title=title, audio_file=audio_file, transcript=transcript,
                                    robot_character=robot_character, created_by=admin.id)
            db.session.add(item)

        # sample observation content
        sample_observation = [
            ("Success Mindset", "https://www.youtube.com/watch?v=motivational1",
             "What are the key points mentioned about achieving success? List three important qualities discussed in the video.",
             "Hard work, Perseverance, Positive attitude"),
            ("Communication Skills", "https://www.youtube.com/watch?v=communication1",
             "According to the video, what makes effective communication? Name two important elements.",
             "Active listening, Clear expression")
        ]
        for title, video_url, questions, answers in sample_observation:
            item = ObservationContent(title=title, video_url=video_url,
                                      questions=questions, correct_answers=answers, created_by=admin.id)
            db.session.add(item)

        # sample writing topics
        sample_topics = [
            ("My Dreams and Aspirations", "Write about your future goals and how you plan to achieve them."),
            ("The Importance of Communication", "Explain why good communication skills are essential in today's world."),
            ("A Person Who Inspires Me", "Describe someone who motivates you and explain why they are your inspiration.")
        ]
        for topic, description in sample_topics:
            t = WritingTopic(topic=topic, description=description, created_by=admin.id)
            db.session.add(t)

        db.session.commit()

# -------------------------
# Helper functions (converted to ORM)
# -------------------------
def calculate_badge_progress(user_id):
    """Calculate badges for a user and update user's badges field."""
    user = User.query.get(user_id)
    if not user:
        return []

    completions = UserCompletion.query.filter_by(user_id=user_id).all()
    badges = []
    if user.total_points >= 100:
        badges.append("Century Scorer")
    if user.best_streak >= 7:
        badges.append("Week Warrior")
    if user.best_streak >= 30:
        badges.append("Monthly Master")
    if len(completions) >= 10:
        badges.append("Practice Champion")
    if len(completions) >= 50:
        badges.append("Communication Expert")

    user.badges = json.dumps(badges)
    db.session.commit()
    return badges

def is_certificate_ready(user_id):
    """Eligibility: at least one completion in each module"""
    rows = db.session.query(UserCompletion.module_type, func.count(UserCompletion.id)).\
        filter(
            UserCompletion.user_id == user_id,
            UserCompletion.module_type.in_(['speaking','listening','writing','observation'])
        ).group_by(UserCompletion.module_type).all()
    have = {r[0] for r in rows if r[1] > 0}
    required = {'speaking','listening','writing','observation'}
    return required.issubset(have)

# -------------------------
# Upload / static config
# -------------------------
UPLOAD_DIR = os.path.join('static', 'audio')
ALLOWED_AUDIO_EXTS = {'.mp3', '.wav', '.ogg', '.m4a', '.webm'}

def ensure_upload_dir():
    try:
        os.makedirs(UPLOAD_DIR, exist_ok=True)
    except Exception:
        pass

# -------------------------
# Routes (logic preserved, DB calls converted)
# -------------------------
@app.route('/')
def index():
    return render_template('home.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username'].strip()
        register_number = request.form['register_number'].strip()
        department = request.form['department'].strip()

        existing = User.query.filter(or_(User.username == username, User.register_number == register_number)).first()
        if existing:
            flash('Username or register number already exists!')
            return render_template('register.html')

        new_user = User(username=username, register_number=register_number, department=department)
        db.session.add(new_user)
        db.session.commit()

        session['user_id'] = new_user.id
        session['username'] = new_user.username
        session['department'] = new_user.department

        flash('Welcome to Shakespeare Club! Your communication journey begins now! 🎭')
        return redirect(url_for('dashboard'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        register_number = request.form['register_number'].strip()
        user = User.query.filter_by(register_number=register_number).first()
        if user:
            session['user_id'] = user.id
            session['username'] = user.username
            session['department'] = user.department
            flash(f'Welcome back, {user.username}! Ready for more communication practice? 🌟')
            return redirect(url_for('dashboard'))
        else:
            flash('Register number not found!')
    return render_template('login.html')

@app.route('/dashboard')
def dashboard():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    user = User.query.get(session['user_id'])
    recent_activities = UserCompletion.query.filter_by(user_id=user.id).order_by(UserCompletion.completed_at.desc()).limit(5).all()

    today = date.today()
    featured_quote = db.session.query(DailyQuote, User).join(User, DailyQuote.posted_by == User.id).\
        filter(DailyQuote.post_date == today, DailyQuote.is_featured == True).\
        order_by(DailyQuote.created_at.asc()).first()
    # featured_quote may be tuple (DailyQuote, User) or None
    if featured_quote:
        featured_quote_obj, featured_user = featured_quote
    else:
        featured_quote_obj = None
        featured_user = None

    badges = calculate_badge_progress(session['user_id'])

    tasks = Task.query.filter(
        Task.is_active == True,
        or_(Task.department == 'ALL', Task.department == session.get('department', 'ALL'))
    ).order_by(
        # mimic ordering: due_date null last, then due_date asc, created_at desc
        Task.due_date.is_(None), Task.due_date.asc(), Task.created_at.desc()
    ).limit(10).all()

    certificate_ready = is_certificate_ready(session['user_id'])

    return render_template(
        'dashboard.html',
        user=user,
        activities=recent_activities,
        featured_quote=featured_quote_obj,
        featured_quote_user=featured_user,
        badges=badges,
        tasks=tasks,
        certificate_ready=certificate_ready
    )

@app.route('/speaking')
def speaking_module():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    biographies = Biography.query.order_by(Biography.created_at.desc()).all()
    completed = db.session.query(UserCompletion.content_id).filter_by(user_id=session['user_id'], module_type='speaking').all()
    completed_ids = [c[0] for c in completed]
    return render_template('speaking.html', biographies=biographies, completed_ids=completed_ids)

@app.route('/speaking/<int:bio_id>')
def speaking_practice(bio_id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    completed = UserCompletion.query.filter_by(user_id=session['user_id'], module_type='speaking', content_id=bio_id).first()
    if completed:
        flash('You have already completed this speaking practice! ✅')
        return redirect(url_for('speaking_module'))
    biography = Biography.query.get(bio_id)
    if not biography:
        flash('Biography not found!')
        return redirect(url_for('speaking_module'))
    return render_template('speaking_practice.html', biography=biography)

@app.route('/submit_speaking', methods=['POST'])
def submit_speaking():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    bio_id = int(request.form['bio_id'])
    recorded_text = request.form.get('recorded_text', '').strip()

    existing = UserCompletion.query.filter_by(user_id=session['user_id'], module_type='speaking', content_id=bio_id).first()
    if existing:
        flash('🚫 You have already completed this practice! Try a different one.')
        return redirect(url_for('speaking_module'))

    biography = Biography.query.get(bio_id)
    if not biography:
        flash('Biography not found!')
        return redirect(url_for('speaking_module'))

    try:
        sentiment_result = analyze_sentiment(recorded_text)
        detailed_feedback = analyze_communication_practice(recorded_text, 'speaking')

        original_words = set(biography.content.lower().split())
        user_words = set(recorded_text.lower().split())
        similarity = len(original_words.intersection(user_words)) / max(len(original_words), 1) * 100

        points_earned = 10
        if similarity >= 80 and sentiment_result.rating >= 4:
            points_earned = 15
        elif similarity >= 60 or sentiment_result.rating >= 3:
            points_earned = 12

        final_score = int(min(100, similarity + sentiment_result.rating * 10))
    except Exception as e:
        # Fallback if AI fails
        original_words = biography.content.lower().split()
        user_words = recorded_text.lower().split()
        matching_words = sum(1 for word in user_words if word in original_words)
        similarity = (matching_words / len(original_words)) * 100 if original_words else 0
        points_earned = 10 if similarity >= 70 else 8
        final_score = int(similarity)
        detailed_feedback = f"Analysis completed with basic scoring. AI unavailable: {str(e)}"

    # Save completion
    completion = UserCompletion(
        user_id=session['user_id'],
        module_type='speaking',
        content_id=bio_id,
        score=final_score,
        points_earned=points_earned
    )
    db.session.add(completion)

    # Update user points
    user = User.query.get(session['user_id'])
    user.total_points = (user.total_points or 0) + points_earned
    db.session.commit()

    # Update streaks
    today = date.today()
    streak = UserStreak.query.filter_by(user_id=session['user_id'], streak_date=today).first()
    if not streak:
        # Insert new streak record
        streak = UserStreak(user_id=session['user_id'], streak_date=today, modules_completed=1, points_earned=points_earned)
        db.session.add(streak)

        # Update current streak: check yesterday
        yesterday = today - timedelta(days=1)
        yesterday_record = UserStreak.query.filter_by(user_id=session['user_id'], streak_date=yesterday).first()
        if yesterday_record:
            user.current_streak = (user.current_streak or 0) + 1
        else:
            user.current_streak = 1
    else:
        # increment modules_completed
        streak.modules_completed = (streak.modules_completed or 0) + 1
        streak.points_earned = (streak.points_earned or 0) + points_earned

    # Update best_streak
    user.best_streak = max(user.best_streak or 0, user.current_streak or 0)

    db.session.commit()

    success_data = {
        'points': points_earned,
        'similarity': similarity,
        'celebration': similarity >= 70,
        'current_streak': user.current_streak or 1
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
    bio_id = int(bio_id)

    # Attempts limit: using SpeakingAttempt table
    today = date.today()
    attempt_count = SpeakingAttempt.query.filter(
        SpeakingAttempt.user_id == session['user_id'],
        SpeakingAttempt.bio_id == bio_id,
        func.date(SpeakingAttempt.attempt_at) == today
    ).count()
    if attempt_count >= 10:
        return jsonify({'error': 'Attempt limit reached. You have already tried 10 times today.'}), 429

    # record attempt
    attempt = SpeakingAttempt(user_id=session['user_id'], bio_id=bio_id)
    db.session.add(attempt)
    db.session.commit()

    # Process audio: try to produce WAV buffer
    raw = audio_file.read()
    wav_buf = None
    try:
        filename = (audio_file.filename or '').lower()
        content_type = (audio_file.mimetype or '').lower()
        src_buf = io.BytesIO(raw)
        src_buf.seek(0)

        if filename.endswith('.wav') or 'wav' in content_type:
            wav_buf = src_buf
        else:
            # attempt to detect using speech_recognition
            try:
                with sr.AudioFile(src_buf) as _:
                    src_buf.seek(0)
                    wav_buf = src_buf
            except Exception:
                wav_buf = None

        if wav_buf is None:
            segment = AudioSegment.from_file(io.BytesIO(raw))
            out = io.BytesIO()
            segment.set_frame_rate(16000).set_channels(1).export(out, format='wav')
            out.seek(0)
            wav_buf = out
    except Exception as e:
        hint = (' Ensure FFmpeg installed and available in PATH, or set FFMPEG_BIN/FFPROBE_BIN env vars.')
        return jsonify({'error': f'Audio processing failed: {str(e)}. {hint}'}), 400

    # Transcribe
    recognizer = sr.Recognizer()
    try:
        with sr.AudioFile(wav_buf) as source:
            audio_data = recognizer.record(source)
        recorded_text = recognizer.recognize_google(audio_data)
    except Exception as e:
        return jsonify({'error': f'Speech-to-text failed: {str(e)}'}), 400

    # reuse scoring logic from submit_speaking
    existing = UserCompletion.query.filter_by(user_id=session['user_id'], module_type='speaking', content_id=bio_id).first()
    if existing:
        return jsonify({'error': 'Already completed'}), 409

    biography = Biography.query.get(bio_id)
    if not biography:
        return jsonify({'error': 'Biography not found'}), 404

    try:
        sentiment_result = analyze_sentiment(recorded_text)
        detailed_feedback = analyze_communication_practice(recorded_text, 'speaking')
        original_words = set(biography.content.lower().split())
        user_words = set(recorded_text.lower().split())
        similarity = len(original_words.intersection(user_words)) / max(len(original_words), 1) * 100
        points_earned = 10
        if similarity >= 80 and sentiment_result.rating >= 4:
            points_earned = 15
        elif similarity >= 60 or sentiment_result.rating >= 3:
            points_earned = 12
        final_score = int(min(100, similarity + sentiment_result.rating * 10))
    except Exception:
        original_words = biography.content.lower().split()
        user_words = recorded_text.lower().split()
        matching_words = sum(1 for word in user_words if word in original_words)
        similarity = (matching_words / len(original_words)) * 100 if original_words else 0
        points_earned = 10 if similarity >= 70 else 8
        final_score = int(similarity)

    # Save completion and update user
    completion = UserCompletion(user_id=session['user_id'], module_type='speaking', content_id=bio_id,
                                score=final_score, points_earned=points_earned)
    db.session.add(completion)

    user = User.query.get(session['user_id'])
    user.total_points = (user.total_points or 0) + points_earned
    db.session.commit()

    # Update streaks
    today = date.today()
    streak = UserStreak.query.filter_by(user_id=session['user_id'], streak_date=today).first()
    if not streak:
        streak = UserStreak(user_id=session['user_id'], streak_date=today, modules_completed=1, points_earned=points_earned)
        db.session.add(streak)
        user.current_streak = (user.current_streak or 0) + 1
    else:
        streak.modules_completed = (streak.modules_completed or 0) + 1
        streak.points_earned = (streak.points_earned or 0) + points_earned

    user.best_streak = max(user.best_streak or 0, user.current_streak or 0)
    db.session.commit()

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

    today = date.today()
    department_quotes = db.session.query(DailyQuote, User).join(User, DailyQuote.posted_by == User.id).\
        filter(DailyQuote.post_date == today).order_by(DailyQuote.department, DailyQuote.created_at.asc()).all()

    # presence check
    user_posted_today = DailyQuote.query.filter_by(posted_by=session['user_id'], post_date=today).first()

    topics = WritingTopic.query.order_by(WritingTopic.created_at.desc()).all()

    return render_template('writing.html', department_quotes=department_quotes, user_posted_today=user_posted_today, topics=topics)

@app.route('/submit_quote', methods=['POST'])
def submit_quote():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    quote = request.form.get('quote', '').strip()
    author = request.form.get('author', '').strip()
    today = date.today()

    existing = DailyQuote.query.filter_by(posted_by=session['user_id'], post_date=today).first()
    if existing:
        flash('You already posted a quote today!')
        return redirect(url_for('writing_module'))

    dept_quotes_today_count = db.session.query(DailyQuote).join(User, DailyQuote.posted_by == User.id).\
        filter(User.department == session['department'], DailyQuote.post_date == today).count()
    is_first = (dept_quotes_today_count == 0)
    points_earned = 15 if is_first else 10

    dq = DailyQuote(quote=quote, author=author, posted_by=session['user_id'], department=session['department'], post_date=today, is_featured=is_first)
    db.session.add(dq)
    # save completion (writing module)
    completion = UserCompletion(user_id=session['user_id'], module_type='writing', content_id=0, score=100, points_earned=points_earned)
    db.session.add(completion)

    user = User.query.get(session['user_id'])
    user.total_points = (user.total_points or 0) + points_earned

    db.session.commit()

    if is_first:
        flash('🎉 Congratulations! You are the first from your department to post today! You earned 15 points!')
    else:
        flash(f'Great quote! You earned {points_earned} points! 📝')

    return redirect(url_for('writing_module'))

@app.route('/submit_writing', methods=['POST'])
def submit_writing():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    quote_id = int(request.form.get('quote_id'))
    user_response = request.form.get('user_response', '').strip()

    existing = UserCompletion.query.filter_by(user_id=session['user_id'], module_type='writing', content_id=quote_id).first()
    if existing:
        flash('🚫 You have already completed this writing practice! Try a different quote.')
        return redirect(url_for('writing_module'))

    quote = DailyQuote.query.get(quote_id)
    if not quote:
        flash('Quote not found.')
        return redirect(url_for('writing_module'))

    try:
        sentiment_result = analyze_sentiment(user_response)
        detailed_feedback = analyze_communication_practice(user_response, 'writing')

        word_count = len(user_response.split())
        depth_score = min(100, word_count * 1.5)
        quality_score = sentiment_result.rating * 20
        final_score = (depth_score + quality_score) / 2

        points_earned = 10
        if word_count >= 100 and sentiment_result.rating >= 4:
            points_earned = 15
        elif word_count >= 75 or sentiment_result.rating >= 3:
            points_earned = 12
    except Exception as e:
        word_count = len(user_response.split())
        final_score = min(100, word_count * 2)
        points_earned = 10 if word_count >= 50 else 8
        detailed_feedback = f"Writing evaluated with basic scoring. AI unavailable: {str(e)}"

    completion = UserCompletion(user_id=session['user_id'], module_type='writing', content_id=quote_id, score=int(final_score), points_earned=points_earned)
    db.session.add(completion)

    user = User.query.get(session['user_id'])
    user.total_points = (user.total_points or 0) + points_earned

    db.session.commit()

    flash(f'🎉 Writing practice completed! Points earned: {points_earned} | Score: {final_score:.1f}%')
    return redirect(url_for('writing_module'))

@app.route('/listening')
def listening_module():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    listening_items = ListeningContent.query.order_by(ListeningContent.created_at.desc()).all()
    completed = db.session.query(UserCompletion.content_id).filter_by(user_id=session['user_id'], module_type='listening').all()
    completed_ids = [c[0] for c in completed]
    return render_template('listening.html', listening_items=listening_items, completed_ids=completed_ids)

@app.route('/listening/<int:content_id>')
def listening_practice(content_id):
    if 'user_id' not in session:
        return redirect(url_for('index'))

    completed = UserCompletion.query.filter_by(user_id=session['user_id'], module_type='listening', content_id=content_id).first()
    if completed:
        flash('You have already completed this listening practice! ✅')
        return redirect(url_for('listening_module'))

    content = ListeningContent.query.get(content_id)
    if not content:
        flash('Content not found!')
        return redirect(url_for('listening_module'))

    return render_template('listening_practice.html', content=content)

@app.route('/submit_listening', methods=['POST'])
def submit_listening():
    if 'user_id' not in session:
        return redirect(url_for('index'))

    content_id = int(request.form.get('content_id'))
    user_input = request.form.get('user_input', '').strip()

    existing = UserCompletion.query.filter_by(user_id=session['user_id'], module_type='listening', content_id=content_id).first()
    if existing:
        flash('🚫 You have already completed this listening practice! Try a different one.')
        return redirect(url_for('listening_module'))

    content = ListeningContent.query.get(content_id)
    if not content:
        flash('Content not found.')
        return redirect(url_for('listening_module'))

    try:
        sentiment_result = analyze_sentiment(user_input)
        detailed_feedback = analyze_communication_practice(user_input, 'listening')

        original_text = content.transcript.lower().strip()
        user_text = user_input.lower().strip()
        original_words = set(original_text.split())
        user_words = set(user_text.split())
        word_accuracy = len(original_words.intersection(user_words)) / max(len(original_words), 1) * 100

        accuracy = min(100, (word_accuracy + sentiment_result.rating * 15) / 2)
        points_earned = 10 if accuracy >= 80 else 8
    except Exception as e:
        original_text = content.transcript.lower().strip()
        user_text = user_input.lower().strip()
        accuracy = (100 if original_text == user_text else
                    80 if len(user_text) > 0 and original_text in user_text else
                    60 if len(user_text) > 0 else 0)
        points_earned = 10 if accuracy >= 80 else 8

    completion = UserCompletion(user_id=session['user_id'], module_type='listening', content_id=content_id, score=int(accuracy), points_earned=points_earned)
    db.session.add(completion)

    user = User.query.get(session['user_id'])
    user.total_points = (user.total_points or 0) + points_earned

    # update streaks similar to speaking
    today = date.today()
    streak = UserStreak.query.filter_by(user_id=session['user_id'], streak_date=today).first()
    if not streak:
        streak = UserStreak(user_id=session['user_id'], streak_date=today, modules_completed=1, points_earned=points_earned)
        db.session.add(streak)
        user.current_streak = (user.current_streak or 0) + 1
    else:
        streak.modules_completed = (streak.modules_completed or 0) + 1
        streak.points_earned = (streak.points_earned or 0) + points_earned

    user.best_streak = max(user.best_streak or 0, user.current_streak or 0)
    db.session.commit()

    success_data = {'points': points_earned, 'accuracy': accuracy, 'celebration': accuracy >= 80}
    return jsonify(success_data)

@app.route('/observation')
def observation_module():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    observation_items = ObservationContent.query.order_by(ObservationContent.created_at.desc()).all()
    completed = db.session.query(UserCompletion.content_id).filter_by(user_id=session['user_id'], module_type='observation').all()
    completed_ids = [c[0] for c in completed]
    return render_template('observation.html', observation_items=observation_items, completed_ids=completed_ids)

@app.route('/observation/<int:content_id>')
def observation_practice(content_id):
    if 'user_id' not in session:
        return redirect(url_for('index'))
    completed = UserCompletion.query.filter_by(user_id=session['user_id'], module_type='observation', content_id=content_id).first()
    if completed:
        flash('You have already completed this observation practice! ✅')
        return redirect(url_for('observation_module'))
    content = ObservationContent.query.get(content_id)
    if not content:
        flash('Content not found!')
        return redirect(url_for('observation_module'))
    return render_template('observation_practice.html', content=content)

@app.route('/submit_observation', methods=['POST'])
def submit_observation():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    content_id = int(request.form.get('content_id'))
    user_answer = request.form.get('user_answer', '').strip()

    existing = UserCompletion.query.filter_by(user_id=session['user_id'], module_type='observation', content_id=content_id).first()
    if existing:
        flash('🚫 You have already completed this observation practice! Try a different video.')
        return redirect(url_for('observation_module'))

    content = ObservationContent.query.get(content_id)
    if not content:
        flash('Content not found.')
        return redirect(url_for('observation_module'))

    try:
        sentiment_result = analyze_sentiment(user_answer)
        detailed_feedback = analyze_communication_practice(user_answer, 'observation')

        correct_answers = content.correct_answers.lower()
        user_answer_lower = user_answer.lower()
        base_accuracy = 100 if correct_answers in user_answer_lower else 70
        quality_boost = sentiment_result.rating * 5
        accuracy = min(100, base_accuracy + quality_boost)
        points_earned = 10 if accuracy >= 90 else 8
    except Exception:
        correct_answers = content.correct_answers.lower()
        user_answer_lower = user_answer.lower()
        accuracy = 100 if correct_answers in user_answer_lower else 70
        points_earned = 10 if accuracy == 100 else 8

    completion = UserCompletion(user_id=session['user_id'], module_type='observation', content_id=content_id,
                                score=int(accuracy), points_earned=points_earned)
    db.session.add(completion)

    user = User.query.get(session['user_id'])
    user.total_points = (user.total_points or 0) + points_earned

    # update streaks
    today = date.today()
    streak = UserStreak.query.filter_by(user_id=session['user_id'], streak_date=today).first()
    if not streak:
        streak = UserStreak(user_id=session['user_id'], streak_date=today, modules_completed=1, points_earned=points_earned)
        db.session.add(streak)
        user.current_streak = (user.current_streak or 0) + 1
    else:
        streak.modules_completed = (streak.modules_completed or 0) + 1
        streak.points_earned = (streak.points_earned or 0) + points_earned

    user.best_streak = max(user.best_streak or 0, user.current_streak or 0)
    db.session.commit()

    success_data = {'points': points_earned, 'accuracy': accuracy, 'celebration': accuracy == 100}
    return jsonify(success_data)

# -------------------------
# Admin routes and content management
# -------------------------
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        admin = Admin.query.filter_by(username=username).first()
        if admin and check_password_hash(admin.password_hash, password):
            session['admin_id'] = admin.id
            session['admin_username'] = admin.username
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid credentials!')
    return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    total_users = db.session.query(func.count(User.id)).scalar() or 0
    total_completions = db.session.query(func.count(UserCompletion.id)).scalar() or 0
    today = date.today()
    today_activities = db.session.query(func.count(UserCompletion.id)).filter(func.date(UserCompletion.completed_at) == today).scalar() or 0

    recent_activities = db.session.query(UserCompletion, User).join(User, UserCompletion.user_id == User.id).order_by(UserCompletion.completed_at.desc()).limit(10).all()

    stats = {'total_users': total_users, 'total_completions': total_completions, 'today_activities': today_activities}
    return render_template('admin_dashboard.html', stats=stats, activities=recent_activities)

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
            bio = Biography(title=title or f"About {person_name}", person_name=person_name, content=content, profession=profession, created_by=session['admin_id'])
            db.session.add(bio)
            db.session.commit()
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
                item = ListeningContent(title=title, audio_file=filename, transcript=transcript, robot_character=robot_character, created_by=session['admin_id'])
                db.session.add(item)
                db.session.commit()
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
            item = ObservationContent(title=title, video_url=video_url, questions=questions, correct_answers=correct_answers, created_by=session['admin_id'])
            db.session.add(item)
            db.session.commit()
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
            t = WritingTopic(topic=topic, description=description, created_by=session['admin_id'])
            db.session.add(t)
            db.session.commit()
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
                item = ListeningContent(title=title, audio_file=output_filename, transcript=text, robot_character=robot_character, created_by=session['admin_id'])
                db.session.add(item)
                db.session.commit()
                created_listening_id = item.id
                flash('Listening content created from generated audio.', 'success')
        except Exception as e:
            error = str(e)
            flash(f'Failed to generate audio: {error}', 'error')
    return render_template('admin_tts.html', output_filename=output_filename, created_listening_id=created_listening_id)

@app.route('/admin/tasks', methods=['GET', 'POST'])
def admin_tasks():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        department = request.form.get('department', 'ALL').strip() or 'ALL'
        due_date = request.form.get('due_date') or None
        is_active = True if request.form.get('is_active') == 'on' else True
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
            task = Task(title=title, description=description, department=department, due_date=due_date,
                        is_active=is_active, created_by=session['admin_id'], module_type=module_type, content_id=content_id)
            db.session.add(task)
            db.session.commit()
            flash('Task added successfully')

    tasks = Task.query.order_by(Task.created_at.desc()).limit(50).all()
    biographies = Biography.query.with_entities(Biography.id, Biography.person_name, Biography.title).order_by(Biography.created_at.desc()).all()
    listening_items = ListeningContent.query.with_entities(ListeningContent.id, ListeningContent.title).order_by(ListeningContent.created_at.desc()).all()
    observation_items = ObservationContent.query.with_entities(ObservationContent.id, ObservationContent.title).order_by(ObservationContent.created_at.desc()).all()
    writing_topics = WritingTopic.query.with_entities(WritingTopic.id, WritingTopic.topic).order_by(WritingTopic.created_at.desc()).all()

    return render_template('admin_tasks.html', tasks=tasks, biographies=biographies,
                           listening_items=listening_items, observation_items=observation_items, writing_topics=writing_topics)

@app.route('/admin/tasks/<int:task_id>/edit', methods=['GET', 'POST'])
def admin_edit_task(task_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    task = Task.query.get(task_id)
    if not task:
        flash('Task not found')
        return redirect(url_for('admin_tasks'))

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        description = request.form.get('description', '').strip()
        department = request.form.get('department', 'ALL').strip() or 'ALL'
        due_date = request.form.get('due_date') or None
        is_active = True if request.form.get('is_active') == 'on' else False
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
            task.title = title
            task.description = description
            task.department = department
            task.due_date = due_date
            task.is_active = is_active
            task.module_type = module_type
            task.content_id = content_id
            db.session.commit()
            flash('Task updated')
            return redirect(url_for('admin_tasks'))

    biographies = Biography.query.with_entities(Biography.id, Biography.person_name, Biography.title).order_by(Biography.created_at.desc()).all()
    listening_items = ListeningContent.query.with_entities(ListeningContent.id, ListeningContent.title).order_by(ListeningContent.created_at.desc()).all()
    observation_items = ObservationContent.query.with_entities(ObservationContent.id, ObservationContent.title).order_by(ObservationContent.created_at.desc()).all()
    writing_topics = WritingTopic.query.with_entities(WritingTopic.id, WritingTopic.topic).order_by(WritingTopic.created_at.desc()).all()

    return render_template('admin_task_edit.html', task=task, biographies=biographies,
                           listening_items=listening_items, observation_items=observation_items, writing_topics=writing_topics)

@app.route('/admin/practices')
def admin_manage_practices():
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    speaking = Biography.query.order_by(Biography.created_at.desc()).all()
    listening = ListeningContent.query.order_by(ListeningContent.created_at.desc()).all()
    observation = ObservationContent.query.order_by(ObservationContent.created_at.desc()).all()
    return render_template('admin_manage_practices.html', speaking=speaking, listening=listening, observation=observation)

@app.route('/admin/speaking/<int:bio_id>/edit', methods=['GET', 'POST'])
def admin_edit_speaking(bio_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    bio = Biography.query.get(bio_id)
    if not bio:
        flash('Speaking passage not found', 'error')
        return redirect(url_for('admin_manage_practices'))
    if request.method == 'POST':
        person_name = request.form.get('person_name', '').strip()
        title = request.form.get('title', '').strip()
        profession = request.form.get('profession', 'Other').strip() or 'Other'
        content = request.form.get('content', '').strip()
        bio.person_name = person_name
        bio.title = title
        bio.profession = profession
        bio.content = content
        db.session.commit()
        flash('Speaking passage updated', 'success')
        return redirect(url_for('admin_manage_practices'))
    return render_template('admin_edit_speaking.html', bio=bio)

@app.route('/admin/speaking/<int:bio_id>/delete', methods=['POST'])
def admin_delete_speaking(bio_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    bio = Biography.query.get(bio_id)
    if bio:
        db.session.delete(bio)
        db.session.commit()
        flash('Speaking passage removed', 'success')
    return redirect(url_for('admin_manage_practices'))

@app.route('/admin/listening/<int:content_id>/edit', methods=['GET', 'POST'])
def admin_edit_listening(content_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    item = ListeningContent.query.get(content_id)
    if not item:
        flash('Listening content not found', 'error')
        return redirect(url_for('admin_manage_practices'))
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        audio_file = request.form.get('audio_file', '').strip() or item.audio_file
        transcript = request.form.get('transcript', '').strip()
        robot_character = request.form.get('robot_character', 'boy').strip() or 'boy'
        item.title = title
        item.audio_file = audio_file
        item.transcript = transcript
        item.robot_character = robot_character
        db.session.commit()
        flash('Listening content updated', 'success')
        return redirect(url_for('admin_manage_practices'))
    return render_template('admin_edit_listening.html', item=item)

@app.route('/admin/listening/<int:content_id>/delete', methods=['POST'])
def admin_delete_listening(content_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    item = ListeningContent.query.get(content_id)
    if item:
        db.session.delete(item)
        db.session.commit()
        flash('Listening content removed', 'success')
    return redirect(url_for('admin_manage_practices'))

@app.route('/admin/observation/<int:obs_id>/edit', methods=['GET', 'POST'])
def admin_edit_observation(obs_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    item = ObservationContent.query.get(obs_id)
    if not item:
        flash('Observation content not found', 'error')
        return redirect(url_for('admin_manage_practices'))
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        video_url = request.form.get('video_url', '').strip()
        questions = request.form.get('questions', '').strip()
        correct_answers = request.form.get('correct_answers', '').strip()
        item.title = title
        item.video_url = video_url
        item.questions = questions
        item.correct_answers = correct_answers
        db.session.commit()
        flash('Observation content updated', 'success')
        return redirect(url_for('admin_manage_practices'))
    return render_template('admin_edit_observation.html', item=item)

@app.route('/admin/observation/<int:obs_id>/delete', methods=['POST'])
def admin_delete_observation(obs_id):
    if 'admin_id' not in session:
        return redirect(url_for('admin_login'))
    item = ObservationContent.query.get(obs_id)
    if item:
        db.session.delete(item)
        db.session.commit()
        flash('Observation content removed', 'success')
    return redirect(url_for('admin_manage_practices'))

@app.route('/leaderboard')
def leaderboard():
    top_users = User.query.order_by(User.total_points.desc()).limit(10).all()
    return render_template('leaderboard.html', top_users=top_users)

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    user = User.query.get(session['user_id'])
    if request.method == 'POST':
        new_username = request.form.get('username', '').strip()
        new_department = request.form.get('department', '').strip()
        try:
            if new_username:
                # ensure uniqueness
                other = User.query.filter(User.username == new_username, User.id != user.id).first()
                if other:
                    flash('Username already taken. Please choose another.', 'error')
                    return redirect(url_for('profile'))
                user.username = new_username
                session['username'] = new_username
            if new_department:
                user.department = new_department
                session['department'] = new_department
            db.session.commit()
            flash('Profile updated successfully', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Failed to update profile.', 'error')
        return redirect(url_for('profile'))
    return render_template('profile.html', user=user)

@app.route('/certificate')
def certificate_view():
    if 'user_id' not in session:
        return redirect(url_for('index'))
    user = User.query.get(session['user_id'])
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

    user = User.query.get(session['user_id'])
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    width, height = A4
    c.setFont('Helvetica-Bold', 24)
    c.drawCentredString(width/2, height - 3*cm, 'Certificate of Completion')
    c.setFont('Helvetica', 12)
    c.drawCentredString(width/2, height - 4*cm, 'Shakespeare Club - Communication Skills Program')
    c.setFont('Helvetica-Bold', 18)
    c.drawCentredString(width/2, height - 7*cm, f"This certifies that {user.username}")
    c.setFont('Helvetica', 12)
    c.drawCentredString(width/2, height - 8*cm, f"Department: {user.department}")
    c.drawCentredString(width/2, height - 10*cm, 'has successfully completed all practice modules:')
    c.drawCentredString(width/2, height - 11*cm, 'Speaking, Listening, Writing, and Observation')
    today_str = datetime.now().strftime('%Y-%m-%d')
    c.drawCentredString(width/2, 3*cm, f"Date: {today_str}")
    c.setFont('Helvetica-Oblique', 10)
    c.drawRightString(width - 2*cm, 2*cm, 'Shakespeare Club')
    c.showPage()
    c.save()
    buf.seek(0)
    filename = f"Certificate_{user.username}.pdf"
    return send_file(buf, as_attachment=True, download_name=filename, mimetype='application/pdf')

@app.after_request
def add_mic_permissions_headers(response):
    response.headers['Permissions-Policy'] = "microphone=(self)"
    response.headers['Feature-Policy'] = "microphone 'self'"
    return response

@app.route('/logout')
def logout():
    session.clear()
    flash('Thanks for practicing! Come back soon! 👋')
    return redirect(url_for('index'))

# -------------------------
# App bootstrap
# -------------------------
if __name__ == '__main__':
    # Create tables and sample data when starting locally or on server first time
    with app.app_context():
        db.create_all()
        ensure_sample_data()
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=True)
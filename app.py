from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file, flash
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, Preference, Classroom, Chair, Swipe, Reservation, Achievement, UserAchievement
from datetime import datetime, date
import qrcode, io, os, json, random

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'chair-match-secret-2024')
database_url = os.environ.get('DATABASE_URL', '')
if database_url.startswith('postgres://'):
    database_url = database_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = database_url or \
    f"sqlite:///{os.path.join(os.path.dirname(os.path.abspath(__file__)), 'database.db')}"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(uid):
    return User.query.get(int(uid))

# ── Matching Algorithm ──────────────────────────────────────────────────────
WEIGHTS = {'window': 0.30, 'front_back': 0.25, 'visibility': 0.25, 'charging': 0.20}

def compute_compatibility(pref, chair):
    def score(p, c): return max(0, 100 - abs(p - c) * 11.1)
    charging_score = 100 if (pref.charging >= 7 and chair.charging) or pref.charging < 7 else 40
    breakdown = {
        'window':     score(pref.window, chair.window_score),
        'front_back': score(pref.front_back, chair.front_back_score),
        'visibility': score(pref.visibility, chair.visibility_score),
        'charging':   charging_score,
    }
    total = sum(breakdown[k] * WEIGHTS[k] for k in WEIGHTS)
    return round(total), breakdown

def get_personality(pref):
    scores = {
        'backbencher': pref.front_back,
        'window': pref.window,
        'invisible': pref.visibility,
        'charging': pref.charging,
        'front': 10 - pref.front_back,
    }
    top = max(scores, key=scores.get)
    personalities = {
        'backbencher': ('🦥', 'Strategic Backbencher', 'Comfort and invisibility are your love language.'),
        'window':      ('🪟', 'Window Philosopher',    'You stare outside and call it studying.'),
        'invisible':   ('🥷', 'Invisible Student',     'You sit where the board can\'t find you.'),
        'charging':    ('⚡', 'Charging Hunter',       'Your phone battery is your emotional support.'),
        'front':       ('👑', "Board Watcher",         'Front row, full board view. You actually pay attention.'),
    }
    return personalities[top]

# ── Achievement checker ─────────────────────────────────────────────────────
def check_achievements(user):
    unlocked_keys = {ua.achievement.key for ua in user.achievements}
    all_achievements = Achievement.query.all()
    likes = [s for s in user.swipes if s.action == 'like']
    new_unlocks = []

    def unlock(key):
        if key not in unlocked_keys:
            ach = Achievement.query.filter_by(key=key).first()
            if ach:
                ua = UserAchievement(user_id=user.id, achievement_id=ach.id)
                db.session.add(ua)
                user.points += ach.points
                new_unlocks.append(ach.name)
                unlocked_keys.add(key)

    if len(user.swipes) >= 20: unlock('explorer')
    if any(compute_compatibility(user.preference, s.chair)[0] >= 95 for s in likes if user.preference): unlock('perfect_match')
    back_likes = [s for s in likes if s.chair.row >= 5]
    if len(back_likes) >= 10: unlock('backbench_legend')
    window_likes = [s for s in likes if s.chair.window_score >= 7]
    if len(window_likes) >= 5: unlock('window_addict')
    charging_likes = [s for s in likes if s.chair.charging]
    if len(charging_likes) >= 5: unlock('charging_hunter')
    if user.reservations: unlock('first_reservation')
    db.session.commit()
    return new_unlocks

# ── Routes ──────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        d = request.form
        if User.query.filter_by(email=d['email']).first():
            flash('Email already registered.', 'error')
            return redirect(url_for('register'))
        u = User(name=d['name'], email=d['email'], department=d.get('department'),
                 year=d.get('year'), class_name=d.get('class_name'))
        u.set_password(d['password'])
        db.session.add(u)
        db.session.commit()
        login_user(u)
        return redirect(url_for('setup_profile'))
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = User.query.filter_by(email=request.form['email']).first()
        if u and u.check_password(request.form['password']):
            login_user(u)
            return redirect(url_for('dashboard'))
        flash('Invalid credentials.', 'error')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/setup-profile', methods=['GET', 'POST'])
@login_required
def setup_profile():
    if request.method == 'POST':
        d = request.form
        pref = current_user.preference or Preference(user_id=current_user.id)
        pref.front_back = float(d.get('front_back', 5))
        pref.window     = float(d.get('window', 5))
        pref.visibility = float(d.get('visibility', 5))
        pref.charging   = float(d.get('charging', 5))
        pref.comfort    = float(d.get('comfort', 5))
        if not current_user.preference:
            db.session.add(pref)
        db.session.commit()
        return redirect(url_for('personality'))
    return render_template('profile.html')

@app.route('/personality')
@login_required
def personality():
    pref = current_user.preference
    if not pref:
        return redirect(url_for('setup_profile'))
    icon, title, desc = get_personality(pref)
    stats = {
        'Backbench affinity':    round(pref.front_back * 10),
        'Window obsession':      round(pref.window * 10),
        'Board avoidance':       round(pref.visibility * 10),
        'Charging dependency':   round(pref.charging * 10),
        'Sleeping comfort':      round(pref.comfort * 10),
    }
    return render_template('personality.html', icon=icon, title=title, desc=desc, stats=stats)

@app.route('/dashboard')
@login_required
def dashboard():
    if current_user.role == 'admin':
        return redirect(url_for('admin'))
    return redirect(url_for('discover'))

@app.route('/discover')
@login_required
def discover():
    pref = current_user.preference
    if not pref:
        return redirect(url_for('setup_profile'))
    swiped_ids = {s.chair_id for s in current_user.swipes}
    chairs = Chair.query.all()
    unseen = [c for c in chairs if c.id not in swiped_ids]
    chair_data = []
    for c in unseen:
        compat, breakdown = compute_compatibility(pref, c)
        chair_data.append({
            'chair': c,
            'compat': compat,
            'breakdown': breakdown,
            'chair_json': {
                'id': c.id,
                'chair_code': c.chair_code,
                'classroom_name': c.classroom.name,
                'row': c.row,
                'window_score': c.window_score,
                'charging': c.charging
            }
        })
    chair_data.sort(key=lambda x: -x['compat'])
    return render_template('discover.html', chair_data=chair_data)

@app.route('/swipe', methods=['POST'])
@login_required
def swipe():
    data = request.get_json()
    chair_id, action = data.get('chair_id'), data.get('action')
    existing = Swipe.query.filter_by(user_id=current_user.id, chair_id=chair_id).first()
    if not existing:
        s = Swipe(user_id=current_user.id, chair_id=chair_id, action=action)
        db.session.add(s)
        db.session.commit()

    pref = current_user.preference
    chair = Chair.query.get(chair_id)
    compat = compute_compatibility(pref, chair)[0] if pref else 0
    new_unlocks = check_achievements(current_user)
    return jsonify({'status': 'ok', 'compat': compat, 'achievements': new_unlocks})

@app.route('/chair/<int:chair_id>')
@login_required
def chair_detail(chair_id):
    chair = Chair.query.get_or_404(chair_id)
    pref = current_user.preference
    compat, breakdown = compute_compatibility(pref, chair) if pref else (0, {})
    active_res = Reservation.query.filter_by(user_id=current_user.id, chair_id=chair_id, status='active').first()
    chair_reserved = Reservation.query.filter_by(chair_id=chair_id, status='active').first()
    return render_template('chair.html', chair=chair, compat=compat, breakdown=breakdown,
                           active_res=active_res, chair_reserved=chair_reserved)

@app.route('/reserve/<int:chair_id>', methods=['POST'])
@login_required
def reserve(chair_id):
    existing = Reservation.query.filter_by(user_id=current_user.id, status='active').first()
    if existing:
        return jsonify({'status': 'error', 'msg': 'You already have an active reservation. Cancel it first.'})
    taken = Reservation.query.filter_by(chair_id=chair_id, status='active').first()
    if taken:
        return jsonify({'status': 'error', 'msg': 'This chair is already reserved by someone else.'})
    r = Reservation(user_id=current_user.id, chair_id=chair_id, date=str(date.today()))
    db.session.add(r)
    current_user.points += 5
    db.session.commit()
    check_achievements(current_user)
    return jsonify({'status': 'ok', 'msg': 'Congratulations. You\'ve committed to a chair. 💺'})

@app.route('/cancel-reservation/<int:res_id>', methods=['POST'])
@login_required
def cancel_reservation(res_id):
    r = Reservation.query.get_or_404(res_id)
    if r.user_id != current_user.id:
        return jsonify({'status': 'error', 'msg': 'Not your reservation.'})
    r.status = 'cancelled'
    db.session.commit()
    return jsonify({'status': 'ok'})

@app.route('/reservations')
@login_required
def reservations():
    active = Reservation.query.filter_by(user_id=current_user.id, status='active').first()
    history = Reservation.query.filter_by(user_id=current_user.id).order_by(Reservation.created_at.desc()).all()
    pref = current_user.preference
    res_data = []
    for r in history:
        compat = compute_compatibility(pref, r.chair)[0] if pref else 0
        res_data.append({'res': r, 'compat': compat})
    active_compat = compute_compatibility(pref, active.chair)[0] if active and pref else 0
    return render_template('reservations.html', active=active, active_compat=active_compat, history=res_data)

@app.route('/classroom')
@login_required
def classroom():
    classrooms = Classroom.query.all()
    selected_id = request.args.get('id', classrooms[0].id if classrooms else None)
    selected = Classroom.query.get(selected_id) if selected_id else None
    pref = current_user.preference
    chair_map = {}
    if selected:
        for c in selected.chairs:
            compat = compute_compatibility(pref, c)[0] if pref else 0
            res = Reservation.query.filter_by(chair_id=c.id, status='active').first()
            my_res = res and res.user_id == current_user.id
            chair_map[c.chair_code] = {
                'id': c.id, 'compat': compat,
                'reserved': bool(res), 'mine': my_res,
                'row': c.row, 'col': c.col
            }
    return render_template('classroom.html', classrooms=classrooms, selected=selected, chair_map=chair_map)

@app.route('/verify-chair/<token>')
def verify_chair(token):
    chair = Chair.query.filter_by(qr_token=token).first_or_404()
    if not current_user.is_authenticated:
        return redirect(url_for('login', next=url_for('verify_chair', token=token)))
    res = Reservation.query.filter_by(user_id=current_user.id, status='active').first()
    pref = current_user.preference
    compat = compute_compatibility(pref, chair)[0] if pref else 0
    if res and res.chair_id == chair.id:
        return render_template('verify.html', chair=chair, status='match', compat=compat, res=res)
    elif res:
        return render_template('verify.html', chair=chair, status='mismatch', res=res, compat=compat)
    else:
        return render_template('verify.html', chair=chair, status='no_reservation', compat=compat)

@app.route('/qr/<int:chair_id>')
@login_required
def generate_qr(chair_id):
    from PIL import Image, ImageDraw, ImageFont
    chair = Chair.query.get_or_404(chair_id)
    url = request.host_url.rstrip('/') + url_for('verify_chair', token=chair.qr_token)

    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    qr_img = qr.make_image(fill_color='black', back_color='white').convert('RGB')

    # Add label below QR
    qr_w, qr_h = qr_img.size
    label_h = 40
    final = Image.new('RGB', (qr_w, qr_h + label_h), 'white')
    final.paste(qr_img, (0, 0))
    draw = ImageDraw.Draw(final)
    try:
        font = ImageFont.truetype('arial.ttf', 18)
    except:
        font = ImageFont.load_default()
    label = f'Chair {chair.chair_code}'
    bbox = draw.textbbox((0, 0), label, font=font)
    text_w = bbox[2] - bbox[0]
    draw.text(((qr_w - text_w) // 2, qr_h + 8), label, fill='black', font=font)

    buf = io.BytesIO()
    final.save(buf, format='PNG')
    buf.seek(0)
    return send_file(buf, mimetype='image/png')

@app.route('/achievements')
@login_required
def achievements():
    all_ach = Achievement.query.all()
    unlocked = {ua.achievement_id for ua in current_user.achievements}
    leaderboard = User.query.filter_by(role='student').order_by(User.points.desc()).limit(10).all()
    return render_template('achievements.html', achievements=all_ach, unlocked=unlocked,
                           leaderboard=leaderboard)

@app.route('/advisor', methods=['GET', 'POST'])
@login_required
def advisor():
    result = None
    if request.method == 'POST':
        msg = request.form.get('message', '').lower()
        pref = current_user.preference
        # Rule-based keyword extraction
        temp_pref = Preference(
            user_id=current_user.id,
            front_back=pref.front_back if pref else 5,
            window=pref.window if pref else 5,
            visibility=pref.visibility if pref else 5,
            charging=pref.charging if pref else 5,
            comfort=pref.comfort if pref else 5,
        )
        if any(w in msg for w in ['back', 'last', 'rear']): temp_pref.front_back = 9
        if any(w in msg for w in ['front', 'first']): temp_pref.front_back = 2
        if any(w in msg for w in ['window', 'outside', 'view']): temp_pref.window = 9
        if any(w in msg for w in ['invisible', 'hide', 'notice', 'seen', 'avoid', 'board']): temp_pref.visibility = 9
        if any(w in msg for w in ['charge', 'charging', 'plug', 'socket', 'power']): temp_pref.charging = 9
        chairs = Chair.query.all()
        scored = [(c, compute_compatibility(temp_pref, c)) for c in chairs]
        scored.sort(key=lambda x: -x[1][0])
        top3 = scored[:3]
        result = {'query': msg, 'chairs': [(c, s, bd) for c, (s, bd) in top3]}
    return render_template('advisor.html', result=result)

@app.route('/analytics')
@login_required
def analytics():
    chairs = Chair.query.all()
    chair_likes = sorted(chairs, key=lambda c: c.like_count, reverse=True)[:10]
    chair_dislikes = sorted(chairs, key=lambda c: c.dislike_count, reverse=True)[:5]
    total_swipes = Swipe.query.count()
    total_likes = Swipe.query.filter_by(action='like').count()
    total_reservations = Reservation.query.filter_by(status='active').count()
    # Preference distribution
    prefs = Preference.query.all()
    avg_prefs = {}
    if prefs:
        avg_prefs = {
            'Window': round(sum(p.window for p in prefs) / len(prefs) * 10),
            'Back Row': round(sum(p.front_back for p in prefs) / len(prefs) * 10),
            'Board Avoidance': round(sum(p.visibility for p in prefs) / len(prefs) * 10),
            'Charging': round(sum(p.charging for p in prefs) / len(prefs) * 10),
        }
    return render_template('analytics.html', chair_likes=chair_likes, chair_dislikes=chair_dislikes,
                           total_swipes=total_swipes, total_likes=total_likes,
                           total_reservations=total_reservations, avg_prefs=avg_prefs)

@app.route('/heatmap-data')
@login_required
def heatmap_data():
    classroom_id = request.args.get('classroom_id', 1)
    metric = request.args.get('metric', 'popularity')
    classroom = Classroom.query.get(classroom_id)
    if not classroom:
        return jsonify([])
    data = []
    for chair in classroom.chairs:
        if metric == 'popularity':
            val = chair.like_count
        elif metric == 'window':
            val = chair.window_score
        elif metric == 'ac':
            val = chair.ac_score
        elif metric == 'visibility':
            val = chair.visibility_score
        elif metric == 'charging':
            val = 10 if chair.charging else 0
        else:
            val = chair.comfort_score
        data.append({'row': chair.row, 'col': chair.col, 'code': chair.chair_code, 'val': val})
    return jsonify(data)

# ── Admin Routes ─────────────────────────────────────────────────────────────
def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

@app.route('/admin')
@login_required
@admin_required
def admin():
    classrooms = Classroom.query.all()
    chairs = Chair.query.all()
    reservations = Reservation.query.order_by(Reservation.created_at.desc()).limit(20).all()
    students = User.query.filter_by(role='student').all()
    total_swipes = Swipe.query.count()
    return render_template('admin.html', classrooms=classrooms, chairs=chairs,
                           reservations=reservations, students=students, total_swipes=total_swipes)

@app.route('/admin/add-classroom', methods=['POST'])
@login_required
@admin_required
def add_classroom():
    name = request.form.get('name')
    rows = int(request.form.get('rows', 6))
    cols = int(request.form.get('cols', 5))
    c = Classroom(name=name, rows=rows, columns=cols)
    db.session.add(c)
    db.session.flush()
    row_labels = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    for r in range(1, rows + 1):
        for col in range(1, cols + 1):
            code = f"{row_labels[r-1]}{col}"
            chair = Chair(classroom_id=c.id, chair_code=code, row=r, col=col,
                          window_score=round(random.uniform(1, 10), 1),
                          ac_score=round(random.uniform(1, 10), 1),
                          visibility_score=round(random.uniform(1, 10), 1),
                          noise_score=round(random.uniform(1, 10), 1),
                          comfort_score=round(random.uniform(1, 10), 1),
                          charging=random.choice([True, False]))
            db.session.add(chair)
    db.session.commit()
    flash(f'Classroom {name} created with {rows * cols} chairs.', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/delete-classroom/<int:cid>', methods=['POST'])
@login_required
@admin_required
def delete_classroom(cid):
    c = Classroom.query.get_or_404(cid)
    db.session.delete(c)
    db.session.commit()
    flash('Classroom deleted.', 'success')
    return redirect(url_for('admin'))

@app.route('/admin/edit-chair/<int:chair_id>', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_chair(chair_id):
    chair = Chair.query.get_or_404(chair_id)
    if request.method == 'POST':
        d = request.form
        chair.window_score = float(d.get('window_score', chair.window_score))
        chair.ac_score = float(d.get('ac_score', chair.ac_score))
        chair.visibility_score = float(d.get('visibility_score', chair.visibility_score))
        chair.noise_score = float(d.get('noise_score', chair.noise_score))
        chair.comfort_score = float(d.get('comfort_score', chair.comfort_score))
        chair.charging = 'charging' in d
        db.session.commit()
        flash(f'Chair {chair.chair_code} updated.', 'success')
        return redirect(url_for('admin'))
    return render_template('edit_chair.html', chair=chair)

@app.route('/admin/delete-chair/<int:chair_id>', methods=['POST'])
@login_required
@admin_required
def delete_chair(chair_id):
    chair = Chair.query.get_or_404(chair_id)
    db.session.delete(chair)
    db.session.commit()
    return jsonify({'status': 'ok'})

@app.route('/admin/cancel-reservation/<int:res_id>', methods=['POST'])
@login_required
@admin_required
def admin_cancel_reservation(res_id):
    r = Reservation.query.get_or_404(res_id)
    r.status = 'cancelled'
    db.session.commit()
    return jsonify({'status': 'ok'})

# ── Seed Data ────────────────────────────────────────────────────────────────
def seed_data():
    if User.query.first():
        return

    # Achievements
    ach_data = [
        ('explorer', '🏅 Chair Explorer', 'Swiped on 20+ chairs', '🏅', 15),
        ('perfect_match', '💘 Perfect Match', 'Found a 95%+ compatibility chair', '💘', 25),
        ('backbench_legend', '🦥 Backbench Legend', 'Liked 10 back-row chairs', '🦥', 20),
        ('window_addict', '🪟 Window Addict', 'Liked 5 window chairs', '🪟', 15),
        ('charging_hunter', '⚡ Charging Hunter', 'Liked 5 charging seats', '⚡', 15),
        ('first_reservation', '💺 Committed', 'Made your first reservation', '💺', 10),
    ]
    for key, name, desc, icon, pts in ach_data:
        db.session.add(Achievement(key=key, name=name, description=desc, icon=icon, points=pts))

    # Admin
    admin = User(name='Admin', email='admin@seatsync.com', role='admin')
    admin.set_password('admin123')
    db.session.add(admin)

    # Classroom
    classroom = Classroom(name='CSE-301', rows=6, columns=5)
    db.session.add(classroom)
    db.session.flush()

    row_labels = 'ABCDEF'
    # Chair properties: window increases left-to-right (col 5 = window side)
    # AC stronger near front-left, visibility lower in back rows
    chairs = []
    for r in range(1, 7):
        for col in range(1, 6):
            window_s = round(col * 1.8 + random.uniform(-0.5, 0.5), 1)
            ac_s = round((7 - r) * 1.2 + random.uniform(-0.5, 0.5), 1)
            vis_s = round(r * 1.5 + random.uniform(-0.5, 0.5), 1)  # back = high invisibility
            noise_s = round(random.uniform(3, 8), 1)
            comfort_s = round(random.uniform(4, 9), 1)
            charging = col in [1, 3, 5] and r in [1, 3, 5, 6]
            code = f"{row_labels[r-1]}{col}"
            c = Chair(classroom_id=classroom.id, chair_code=code, row=r, col=col,
                      window_score=min(10, max(1, window_s)),
                      ac_score=min(10, max(1, ac_s)),
                      visibility_score=min(10, max(1, vis_s)),
                      noise_score=min(10, max(1, noise_s)),
                      comfort_score=min(10, max(1, comfort_s)),
                      charging=charging)
            db.session.add(c)
            chairs.append(c)
    db.session.flush()

    # Sample students
    student_data = [
        # (name, email, dept, year, front_back, window, ac, visibility, noise, charging, comfort)
        ('Rahul Sharma',   'rahul@demo.com',   'CSE', '3rd Year', 9, 8, 9, 6, 8),
        ('Priya Patel',    'priya@demo.com',   'ECE', '2nd Year', 3, 9, 4, 8, 7),
        ('Arjun Singh',    'arjun@demo.com',   'ME',  '4th Year', 8, 5, 8, 9, 6),
        ('Sneha Reddy',    'sneha@demo.com',   'CSE', '1st Year', 2, 7, 2, 5, 9),
        ('Karan Mehta',    'karan@demo.com',   'IT',  '3rd Year', 9, 9, 9, 7, 7),
        ('Abhinav Gopal',  'abhinav@demo.com', 'CSE', '3rd Year', 8, 7, 8, 8, 7),
        ('Divya Nair',     'divya@demo.com',   'ECE', '2nd Year', 4, 8, 3, 5, 8),
        ('Rohan Verma',    'rohan@demo.com',   'IT',  '1st Year', 7, 6, 7, 9, 6),
    ]
    students = []
    for name, email, dept, year, fb, win, vis, chg, comf in student_data:
        u = User(name=name, email=email, department=dept, year=year, class_name='CSE-A', points=random.randint(20, 100))
        u.set_password('demo123')
        db.session.add(u)
        db.session.flush()
        p = Preference(user_id=u.id, front_back=fb, window=win,
                       visibility=vis, charging=chg, comfort=comf)
        db.session.add(p)
        students.append((u, p))

    db.session.flush()

    # Generate swipes for demo data
    for u, p in students:
        liked = []
        for c in random.sample(chairs, min(25, len(chairs))):
            compat, _ = compute_compatibility(p, c)
            action = 'like' if compat >= 55 else 'dislike'
            db.session.add(Swipe(user_id=u.id, chair_id=c.id, action=action))
            if action == 'like':
                liked.append(c)

    db.session.commit()
    print("Demo data seeded successfully.")

# ── Ensure Admin Account ─────────────────────────────────────────────────────
def ensure_admin():
    admin = User.query.filter_by(email='admin@seatsync.com').first()

    if not admin:
        admin = User(
            name='Admin',
            email='admin@seatsync.com',
            role='admin'
        )
        admin.set_password('admin123')
        db.session.add(admin)
        db.session.commit()
        print("Admin account created successfully.")
    else:
        # Make sure the existing account has admin privileges.
        if admin.role != 'admin':
            admin.role = 'admin'
            db.session.commit()

        print("Admin account already exists.")


with app.app_context():
    db.create_all()
    seed_data()
    ensure_admin()

if __name__ == '__main__':
    app.run(debug=True)
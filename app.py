from flask import Flask, render_template, request, redirect, url_for, session, jsonify, send_file
from flask_login import LoginManager, login_user, logout_user, login_required, current_user
from models import db, User, Preference, Classroom, Chair, Swipe, Reservation, Achievement, UserAchievement
from datetime import datetime, date
import os, uuid, io, json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'chairmatch-secret-2024'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///database.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(uid): return User.query.get(int(uid))

# ── Matching Algorithm ──────────────────────────────────────────────
WEIGHTS = {'window':25,'front_back':20,'ac':15,'visibility':15,'charging':15,'noise':10}

def calc_compatibility(pref, chair):
    if not pref: return 50, {}
    def score(p, c): return max(0, 100 - abs(p - c) * 11)
    charging_score = 100 if (pref.charging >= 7 and chair.charging) or pref.charging < 7 else 30
    breakdown = {
        'window': score(pref.window, chair.window_score),
        'front_back': score(pref.front_back, chair.row),
        'ac': score(pref.ac, chair.ac_score),
        'visibility': score(pref.visibility, chair.visibility_score),
        'charging': charging_score,
        'noise': score(pref.noise, chair.noise_score),
    }
    total = sum(breakdown[k] * WEIGHTS[k] / 100 for k in WEIGHTS)
    return round(total), breakdown

def get_personality(pref):
    if not pref: return None
    scores = {
        'backbencher': pref.front_back * 10,
        'window': pref.window * 10,
        'ac': pref.ac * 10,
        'invisible': pref.visibility * 10,
        'charging': pref.charging * 10,
        'teacher': (10 - pref.visibility) * 10,
    }
    top = max(scores, key=scores.get)
    personalities = {
        'backbencher': ('🦥', 'Strategic Backbencher', 'Comfort and invisibility are your superpowers.'),
        'window': ('🪟', 'Window Philosopher', 'You stare outside and call it studying.'),
        'ac': ('❄️', 'AC Addict', 'You would sit in a freezer if it had a desk.'),
        'invisible': ('🥷', 'Invisible Student', 'The teacher has never seen your face. Intentionally.'),
        'charging': ('⚡', 'Charging Hunter', 'Your true soulmate is a power socket.'),
        'teacher': ('👑', "Teacher's Favorite", 'Front row, eye contact, hand always raised.'),
    }
    return personalities[top], scores

def check_achievements(user):
    unlocked = [ua.achievement_id for ua in user.achievements]
    likes = [s for s in user.swipes if s.action == 'like']
    all_achievements = Achievement.query.all()
    new_ones = []
    for ach in all_achievements:
        if ach.id in unlocked: continue
        earned = False
        if ach.key == 'explorer' and len(user.swipes) >= 20: earned = True
        elif ach.key == 'perfect_match':
            pref = user.preference
            for s in likes:
                c, _ = calc_compatibility(pref, s.chair)
                if c >= 95: earned = True; break
        elif ach.key == 'backbench_legend':
            back = sum(1 for s in likes if s.chair.row >= 4)
            if back >= 10: earned = True
        elif ach.key == 'window_addict':
            win = sum(1 for s in likes if s.chair.window_score >= 7)
            if win >= 5: earned = True
        elif ach.key == 'charging_hunter':
            ch = sum(1 for s in likes if s.chair.charging)
            if ch >= 5: earned = True
        elif ach.key == 'first_like' and len(likes) >= 1: earned = True
        elif ach.key == 'reserved' and len(user.reservations) >= 1: earned = True
        if earned:
            ua = UserAchievement(user_id=user.id, achievement_id=ach.id)
            db.session.add(ua)
            user.points += ach.points
            new_ones.append(ach)
    db.session.commit()
    return new_ones

# ── Routes ──────────────────────────────────────────────────────────
@app.route('/')
def index(): return render_template('index.html')

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        u = User.query.filter_by(email=request.form['email']).first()
        if u and u.check_password(request.form['password']):
            login_user(u)
            return redirect(url_for('discover') if u.preference else url_for('profile_setup'))
        return render_template('login.html', error='Invalid credentials. Your chair is waiting though.')
    return render_template('login.html')

@app.route('/register', methods=['GET','POST'])
def register():
    if request.method == 'POST':
        if User.query.filter_by(email=request.form['email']).first():
            return render_template('register.html', error='Email already registered.')
        u = User(name=request.form['name'], email=request.form['email'],
                 department=request.form['department'], year=int(request.form['year']),
                 class_name=request.form['class_name'])
        u.set_password(request.form['password'])
        db.session.add(u); db.session.commit()
        login_user(u)
        return redirect(url_for('profile_setup'))
    return render_template('register.html')

@app.route('/logout')
@login_required
def logout(): logout_user(); return redirect(url_for('index'))

@app.route('/profile', methods=['GET','POST'])
@login_required
def profile_setup():
    if request.method == 'POST':
        p = current_user.preference or Preference(user_id=current_user.id)
        p.front_back = int(request.form['front_back'])
        p.window = int(request.form['window'])
        p.ac = int(request.form['ac'])
        p.visibility = int(request.form['visibility'])
        p.noise = int(request.form['noise'])
        p.charging = int(request.form['charging'])
        p.comfort = int(request.form['comfort'])
        db.session.add(p); db.session.commit()
        return redirect(url_for('personality'))
    return render_template('profile.html', pref=current_user.preference)

@app.route('/personality')
@login_required
def personality():
    result = get_personality(current_user.preference)
    if not result: return redirect(url_for('profile_setup'))
    persona, scores = result
    return render_template('personality.html', persona=persona, scores=scores, pref=current_user.preference)

@app.route('/discover')
@login_required
def discover():
    swiped = [s.chair_id for s in current_user.swipes]
    chairs = Chair.query.filter(Chair.id.notin_(swiped) if swiped else True).all()
    pref = current_user.preference
    chair_data = []
    for c in chairs:
        compat, breakdown = calc_compatibility(pref, c)
        chair_data.append({'chair': c, 'compat': compat, 'breakdown': breakdown})
    chair_data.sort(key=lambda x: -x['compat'])
    return render_template('discover.html', chairs=chair_data)

@app.route('/swipe', methods=['POST'])
@login_required
def swipe():
    data = request.get_json()
    chair_id, action = data['chair_id'], data['action']
    existing = Swipe.query.filter_by(user_id=current_user.id, chair_id=chair_id).first()
    if existing: existing.action = action
    else:
        s = Swipe(user_id=current_user.id, chair_id=chair_id, action=action)
        db.session.add(s)
    db.session.commit()
    new_ach = check_achievements(current_user)
    chair = Chair.query.get(chair_id)
    pref = current_user.preference
    compat, _ = calc_compatibility(pref, chair)
    return jsonify({'status':'ok','compat':compat,'achievements':[a.name for a in new_ach]})

@app.route('/chair/<int:chair_id>')
@login_required
def chair_detail(chair_id):
    chair = Chair.query.get_or_404(chair_id)
    pref = current_user.preference
    compat, breakdown = calc_compatibility(pref, chair)
    swipe = Swipe.query.filter_by(user_id=current_user.id, chair_id=chair_id).first()
    reserved = Reservation.query.filter_by(user_id=current_user.id, chair_id=chair_id, status='active').first()
    likes = Swipe.query.filter_by(chair_id=chair_id, action='like').count()
    return render_template('chair.html', chair=chair, compat=compat, breakdown=breakdown,
                           swipe=swipe, reserved=reserved, likes=likes)

@app.route('/reserve/<int:chair_id>', methods=['POST'])
@login_required
def reserve(chair_id):
    active = Reservation.query.filter_by(user_id=current_user.id, status='active').first()
    if active:
        return jsonify({'status':'error','msg':'You already have an active reservation. Commit to one chair at a time.'})
    taken = Reservation.query.filter_by(chair_id=chair_id, status='active').first()
    if taken:
        return jsonify({'status':'error','msg':'This chair is already taken. There are other chairs in the sea.'})
    r = Reservation(user_id=current_user.id, chair_id=chair_id, date=str(date.today()))
    db.session.add(r); db.session.commit()
    check_achievements(current_user)
    return jsonify({'status':'ok','msg':'Congratulations. You have committed to a chair.'})

@app.route('/cancel-reservation/<int:res_id>', methods=['POST'])
@login_required
def cancel_reservation(res_id):
    r = Reservation.query.get_or_404(res_id)
    if r.user_id != current_user.id: return jsonify({'status':'error'}), 403
    r.status = 'cancelled'; db.session.commit()
    return jsonify({'status':'ok'})

@app.route('/reservations')
@login_required
def reservations():
    active = Reservation.query.filter_by(user_id=current_user.id, status='active').first()
    history = Reservation.query.filter_by(user_id=current_user.id).order_by(Reservation.created_at.desc()).all()
    pref = current_user.preference
    compat = 0
    if active: compat, _ = calc_compatibility(pref, active.chair)
    return render_template('reservations.html', active=active, history=history, compat=compat)

@app.route('/verify/<token>')
def verify_chair(token):
    chair = Chair.query.filter_by(qr_token=token).first_or_404()
    if not current_user.is_authenticated:
        session['verify_token'] = token
        return redirect(url_for('login'))
    reservation = Reservation.query.filter_by(user_id=current_user.id, status='active').first()
    pref = current_user.preference
    compat, _ = calc_compatibility(pref, chair)
    if reservation and reservation.chair_id == chair.id:
        return render_template('verify.html', chair=chair, status='match', reservation=reservation, compat=compat)
    return render_template('verify.html', chair=chair, status='mismatch', reservation=reservation, compat=compat)

@app.route('/qr/<int:chair_id>')
@login_required
def get_qr(chair_id):
    chair = Chair.query.get_or_404(chair_id)
    import qrcode
    url = request.host_url + f'verify/{chair.qr_token}'
    img = qrcode.make(url)
    buf = io.BytesIO(); img.save(buf, 'PNG'); buf.seek(0)
    return send_file(buf, mimetype='image/png')

@app.route('/classroom')
@login_required
def classroom():
    classrooms = Classroom.query.all()
    selected_id = request.args.get('classroom_id', classrooms[0].id if classrooms else None, type=int)
    selected = Classroom.query.get(selected_id) if selected_id else None
    pref = current_user.preference
    chair_data = {}
    if selected:
        for c in selected.chairs:
            compat, _ = calc_compatibility(pref, c)
            reserved = Reservation.query.filter_by(chair_id=c.id, status='active').first()
            my_res = reserved and reserved.user_id == current_user.id
            likes = Swipe.query.filter_by(chair_id=c.id, action='like').count()
            chair_data[c.id] = {'compat': compat, 'reserved': bool(reserved), 'mine': my_res, 'likes': likes}
    return render_template('classroom.html', classrooms=classrooms, selected=selected, chair_data=chair_data)

@app.route('/analytics')
@login_required
def analytics():
    chairs = Chair.query.all()
    chair_likes = []
    for c in chairs:
        likes = Swipe.query.filter_by(chair_id=c.id, action='like').count()
        dislikes = Swipe.query.filter_by(chair_id=c.id, action='dislike').count()
        chair_likes.append({'code': c.chair_code, 'likes': likes, 'dislikes': dislikes})
    chair_likes.sort(key=lambda x: -x['likes'])
    total_swipes = Swipe.query.count()
    total_reservations = Reservation.query.filter_by(status='active').count()
    total_users = User.query.filter_by(role='student').count()
    leaderboard = User.query.filter_by(role='student').order_by(User.points.desc()).limit(10).all()
    return render_template('analytics.html', chair_likes=chair_likes, total_swipes=total_swipes,
                           total_reservations=total_reservations, total_users=total_users,
                           leaderboard=leaderboard)

@app.route('/achievements')
@login_required
def achievements():
    all_ach = Achievement.query.all()
    unlocked = {ua.achievement_id: ua.unlocked_at for ua in current_user.achievements}
    return render_template('achievements.html', achievements=all_ach, unlocked=unlocked)

@app.route('/advisor', methods=['GET','POST'])
@login_required
def advisor():
    result = None
    if request.method == 'POST':
        msg = request.form['message'].lower()
        pref = current_user.preference
        # keyword-based preference override
        temp_pref = Preference(
            front_back=pref.front_back if pref else 5,
            window=pref.window if pref else 5,
            ac=pref.ac if pref else 5,
            visibility=pref.visibility if pref else 5,
            noise=pref.noise if pref else 5,
            charging=pref.charging if pref else 5,
            comfort=pref.comfort if pref else 5,
        )
        if any(w in msg for w in ['back','last','rear']): temp_pref.front_back = 9
        if any(w in msg for w in ['front','first']): temp_pref.front_back = 2
        if any(w in msg for w in ['window','outside','view']): temp_pref.window = 9
        if any(w in msg for w in ['ac','cold','cool','air']): temp_pref.ac = 9
        if any(w in msg for w in ['hide','invisible','notice','teacher']): temp_pref.visibility = 9
        if any(w in msg for w in ['charg','power','socket','plug']): temp_pref.charging = 9
        if any(w in msg for w in ['quiet','silent','noise']): temp_pref.noise = 2
        chairs = Chair.query.all()
        scored = []
        for c in chairs:
            compat, breakdown = calc_compatibility(temp_pref, c)
            scored.append({'chair': c, 'compat': compat, 'breakdown': breakdown})
        scored.sort(key=lambda x: -x['compat'])
        result = scored[:5]
    return render_template('advisor.html', result=result)

# ── Admin Routes ─────────────────────────────────────────────────────
def admin_required(f):
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if not current_user.is_authenticated or current_user.role != 'admin':
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated

@app.route('/admin')
@login_required
@admin_required
def admin():
    classrooms = Classroom.query.all()
    chairs = Chair.query.all()
    reservations = Reservation.query.order_by(Reservation.created_at.desc()).limit(20).all()
    users = User.query.filter_by(role='student').all()
    stats = {
        'classrooms': len(classrooms), 'chairs': len(chairs),
        'reservations': Reservation.query.filter_by(status='active').count(),
        'users': len(users), 'swipes': Swipe.query.count()
    }
    chair_likes = []
    for c in chairs:
        likes = Swipe.query.filter_by(chair_id=c.id, action='like').count()
        chair_likes.append({'chair': c, 'likes': likes})
    chair_likes.sort(key=lambda x: -x['likes'])
    return render_template('admin.html', classrooms=classrooms, chairs=chairs,
                           reservations=reservations, users=users, stats=stats,
                           chair_likes=chair_likes[:10])

@app.route('/admin/classroom/add', methods=['POST'])
@login_required
@admin_required
def add_classroom():
    name = request.form['name']
    rows = int(request.form.get('rows', 6))
    cols = int(request.form.get('columns', 5))
    if Classroom.query.filter_by(name=name).first():
        return redirect(url_for('admin'))
    c = Classroom(name=name, rows=rows, columns=cols)
    db.session.add(c); db.session.flush()
    row_labels = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
    import random
    for r in range(rows):
        for col in range(1, cols+1):
            code = f"{row_labels[r]}{col}"
            chair = Chair(
                classroom_id=c.id, chair_code=code, row=r+1, col=col,
                window_score=random.randint(1,10), ac_score=random.randint(1,10),
                visibility_score=random.randint(1,10), noise_score=random.randint(1,10),
                comfort_score=random.randint(1,10), charging=random.choice([True,False]),
                qr_token=str(uuid.uuid4())[:16]
            )
            db.session.add(chair)
    db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/classroom/delete/<int:cid>', methods=['POST'])
@login_required
@admin_required
def delete_classroom(cid):
    c = Classroom.query.get_or_404(cid)
    db.session.delete(c); db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/chair/edit/<int:cid>', methods=['POST'])
@login_required
@admin_required
def edit_chair(cid):
    chair = Chair.query.get_or_404(cid)
    chair.window_score = int(request.form['window_score'])
    chair.ac_score = int(request.form['ac_score'])
    chair.visibility_score = int(request.form['visibility_score'])
    chair.noise_score = int(request.form['noise_score'])
    chair.comfort_score = int(request.form['comfort_score'])
    chair.charging = 'charging' in request.form
    db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/chair/delete/<int:cid>', methods=['POST'])
@login_required
@admin_required
def delete_chair(cid):
    chair = Chair.query.get_or_404(cid)
    db.session.delete(chair); db.session.commit()
    return redirect(url_for('admin'))

@app.route('/admin/reservation/cancel/<int:rid>', methods=['POST'])
@login_required
@admin_required
def admin_cancel_reservation(rid):
    r = Reservation.query.get_or_404(rid)
    r.status = 'cancelled'; db.session.commit()
    return redirect(url_for('admin'))

# ── API for charts ───────────────────────────────────────────────────
@app.route('/api/heatmap/<int:classroom_id>')
@login_required
def heatmap_data(classroom_id):
    classroom = Classroom.query.get_or_404(classroom_id)
    metric = request.args.get('metric', 'popularity')
    data = []
    for chair in classroom.chairs:
        if metric == 'popularity':
            val = Swipe.query.filter_by(chair_id=chair.id, action='like').count()
        elif metric == 'window': val = chair.window_score
        elif metric == 'ac': val = chair.ac_score
        elif metric == 'visibility': val = chair.visibility_score
        elif metric == 'charging': val = 10 if chair.charging else 0
        else: val = chair.comfort_score
        data.append({'row': chair.row, 'col': chair.col, 'code': chair.chair_code, 'value': val})
    return jsonify(data)

@app.route('/api/analytics')
@login_required
def analytics_data():
    chairs = Chair.query.all()
    labels, likes, dislikes = [], [], []
    for c in chairs[:15]:
        labels.append(c.chair_code)
        likes.append(Swipe.query.filter_by(chair_id=c.id, action='like').count())
        dislikes.append(Swipe.query.filter_by(chair_id=c.id, action='dislike').count())
    prefs = Preference.query.all()
    avg = lambda attr: round(sum(getattr(p, attr) for p in prefs)/len(prefs)*10) if prefs else 0
    preference_data = {
        'Window': avg('window'), 'Back Row': avg('front_back'), 'AC': avg('ac'),
        'Invisibility': avg('visibility'), 'Charging': avg('charging'), 'Comfort': avg('comfort')
    }
    return jsonify({'labels': labels, 'likes': likes, 'dislikes': dislikes, 'preferences': preference_data})

# ── Seed Data ────────────────────────────────────────────────────────
def seed():
    if Classroom.query.first(): return
    import random
    # Achievements
    achs = [
        ('first_like','First Swipe','You swiped right on your first chair.','💘',5),
        ('explorer','Chair Explorer','Viewed 20 chairs. You have commitment issues.','🧭',15),
        ('perfect_match','Perfect Match','Found a 95%+ compatibility chair.','💯',25),
        ('backbench_legend','Backbench Legend','Liked 10 back-row chairs.','🦥',20),
        ('window_addict','Window Addict','Liked 5 window chairs.','🪟',15),
        ('charging_hunter','Charging Hunter','Liked 5 charging seats.','⚡',15),
        ('reserved','Committed','Reserved your first chair.','💺',10),
    ]
    for key,name,desc,icon,pts in achs:
        db.session.add(Achievement(key=key,name=name,description=desc,icon=icon,points=pts))

    # Admin
    admin = User(name='Admin', email='admin@chairmatch.com', role='admin', department='Admin', year=0, class_name='Admin')
    admin.set_password('admin123')
    db.session.add(admin)

    # Classroom
    classroom = Classroom(name='CSE-301', rows=6, columns=5)
    db.session.add(classroom); db.session.flush()

    row_labels = 'ABCDEF'
    window_cols = {5: 10, 4: 8, 3: 5, 2: 3, 1: 1}
    ac_rows = {1: 9, 2: 8, 3: 6, 4: 4, 5: 3, 6: 2}
    vis_rows = {1: 1, 2: 2, 3: 4, 4: 7, 5: 9, 6: 10}

    chairs = []
    for r in range(1, 7):
        for col in range(1, 6):
            code = f"{row_labels[r-1]}{col}"
            chair = Chair(
                classroom_id=classroom.id, chair_code=code, row=r, col=col,
                window_score=window_cols.get(col, 5) + random.randint(-1,1),
                ac_score=ac_rows.get(r, 5) + random.randint(-1,1),
                visibility_score=vis_rows.get(r, 5) + random.randint(-1,1),
                noise_score=random.randint(3,8),
                comfort_score=random.randint(4,9),
                charging=(col in [1,5] or r == 6),
                qr_token=str(uuid.uuid4())[:16]
            )
            db.session.add(chair); chairs.append(chair)
    db.session.flush()

    # Sample students
    sample_students = [
        ('Rahul Sharma','rahul@demo.com','CSE',3,'A'),
        ('Priya Nair','priya@demo.com','ECE',2,'B'),
        ('Arjun Menon','arjun@demo.com','CSE',4,'A'),
        ('Sneha Pillai','sneha@demo.com','IT',1,'C'),
        ('Kiran Das','kiran@demo.com','CSE',3,'B'),
    ]
    students = []
    for name,email,dept,yr,cls in sample_students:
        u = User(name=name,email=email,department=dept,year=yr,class_name=cls,role='student',points=random.randint(10,80))
        u.set_password('demo123')
        db.session.add(u); db.session.flush()
        p = Preference(user_id=u.id,
            front_back=random.randint(1,10), window=random.randint(1,10),
            ac=random.randint(1,10), visibility=random.randint(1,10),
            noise=random.randint(1,10), charging=random.randint(1,10),
            comfort=random.randint(1,10))
        db.session.add(p)
        students.append(u)
    db.session.flush()

    # Sample swipes
    for u in students:
        sample_chairs = random.sample(chairs, min(20, len(chairs)))
        for c in sample_chairs:
            action = 'like' if random.random() > 0.35 else 'dislike'
            db.session.add(Swipe(user_id=u.id, chair_id=c.id, action=action))

    db.session.commit()

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
        seed()
    app.run(debug=True)

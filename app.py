# Olimpiad Abyss - working app (safe CSRF handling for polls/chat/clicker)
import os, json, datetime
from dotenv import load_dotenv
load_dotenv()

from flask import Flask, render_template, redirect, url_for, flash, request, session, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm, CSRFProtect
from flask_wtf.csrf import generate_csrf
from wtforms import StringField, PasswordField, TextAreaField, SubmitField
from wtforms.validators import InputRequired, Length, EqualTo

# App setup
app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')

# ---------- МИНИМАЛЬНАЯ ПРАВКА: выбор БД ----------
# Если задана DATABASE_URL (Render Postgres) — используем её.
# Иначе — fallback на локальную SQLite (instance/app.db), как раньше.
database_url = os.environ.get("DATABASE_URL", "").strip()
if database_url:
    # поддержка старого формата
    if database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql://", 1)
    # добавить sslmode=require если не указан (нужно для Render)
    if "sslmode" not in database_url:
        database_url += ("&" if "?" in database_url else "?") + "sslmode=require"
    app.config['SQLALCHEMY_DATABASE_URI'] = database_url
else:
    # Use instance DB path (three slashes -> relative path; four -> absolute). We'll use absolute.
    instance_db = os.path.join(BASE_DIR, 'instance', 'app.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{instance_db}"
# -------------------------------------------------

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Ensure instance folder exists (useful locally for sqlite)
if not os.environ.get("DATABASE_URL"):
    os.makedirs(os.path.join(BASE_DIR, 'instance'), exist_ok=True)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
csrf = CSRFProtect(app)

# Make some builtins available to Jinja
app.jinja_env.globals.update(enumerate=enumerate, len=len, range=range, str=str)

# Models
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_god = db.Column(db.Boolean, default=False, nullable=False)
    points = db.Column(db.Integer, default=0)
    avatar = db.Column(db.String(200), default='🐼')
    bio = db.Column(db.String(300), default='')
    joined_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    username = db.Column(db.String(80))
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.datetime.utcnow)

class Poll(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(300), nullable=False)
    options = db.Column(db.Text, nullable=False)  # JSON list

class Vote(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    poll_id = db.Column(db.Integer, db.ForeignKey('poll.id'), nullable=False)
    option_index = db.Column(db.Integer, nullable=False)

# Forms
class RegisterForm(FlaskForm):
    username = StringField('Логин', validators=[InputRequired(), Length(min=3, max=80)])
    password = PasswordField('Пароль', validators=[InputRequired(), Length(min=6)])
    password2 = PasswordField('Повтор пароля', validators=[InputRequired(), EqualTo('password')])
    submit = SubmitField('Зарегистрироваться')

class LoginForm(FlaskForm):
    username = StringField('Логин', validators=[InputRequired()])
    password = PasswordField('Пароль', validators=[InputRequired()])
    submit = SubmitField('Войти')

class PollForm(FlaskForm):
    question = StringField('Вопрос', validators=[InputRequired(), Length(max=300)])
    options = StringField('Опции (через | )', validators=[InputRequired()])
    submit = SubmitField('Создать опрос')

class ProfileForm(FlaskForm):
    avatar = StringField('Аватар', validators=[Length(max=200)])
    bio = TextAreaField('О себе', validators=[Length(max=300)])
    submit = SubmitField('Сохранить')

# Utility/context
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

@app.context_processor
def inject_globals():
    return {
        'user': current_user,
        'admin_mode': session.get('admin_mode', False) and current_user.is_authenticated and (current_user.is_admin or current_user.is_god),
        'csrf_token_value': generate_csrf()
    }

# Initialize DB + create god user if needed
def init_db():
    db.create_all()
    god = User.query.filter_by(is_god=True).first()
    if not god:
        gn = os.environ.get('GOD_USERNAME', 'god')
        gp = os.environ.get('GOD_PASSWORD', 'godpass')
        if gn and gp and not User.query.filter_by(username=gn).first():
            u = User(username=gn, is_god=True, is_admin=True)
            u.set_password(gp)
            db.session.add(u); db.session.commit()
            print('Created god user:', gn)

with app.app_context():
    init_db()

# Routes (оставлены без изменений — их копируй из твоего рабочего файла)
@app.route('/')
def index():
    polls = Poll.query.order_by(Poll.id.desc()).limit(6).all()
    top_clickers = User.query.order_by(User.points.desc()).limit(6).all()
    return render_template('index.html', polls=polls, top_clickers=top_clickers)

@app.route('/register', methods=['GET','POST'])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        if User.query.filter_by(username=form.username.data).first():
            flash('Пользователь с таким логином уже существует', 'warning')
        else:
            u = User(username=form.username.data)
            u.set_password(form.password.data)
            db.session.add(u); db.session.commit()
            flash('Зарегистрированы — войдите в систему', 'success')
            return redirect(url_for('login'))
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET','POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        u = User.query.filter_by(username=form.username.data).first()
        if u and u.check_password(form.password.data):
            login_user(u)
            flash('Вход выполнен', 'success')
            return redirect(url_for('index'))
        flash('Неверный логин или пароль', 'danger')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    session.pop('admin_mode', None)
    flash('Выход выполнен', 'info')
    return redirect(url_for('index'))

@app.route('/profile', methods=['GET','POST'])
@login_required
def profile():
    form = ProfileForm(obj=current_user)
    if form.validate_on_submit():
        current_user.avatar = form.avatar.data or current_user.avatar
        current_user.bio = form.bio.data or current_user.bio
        db.session.add(current_user); db.session.commit()
        flash('Профиль обновлён', 'success')
        return redirect(url_for('profile'))
    messages = Message.query.filter_by(user_id=current_user.id).order_by(Message.created_at.desc()).limit(20).all()
    return render_template('profile.html', form=form, messages=messages)

# Chat endpoints
@app.route('/chat')
@login_required
def chat():
    return render_template('chat.html')

@app.route('/api/chat', methods=['GET','POST'])
def api_chat():
    if request.method == 'GET':
        msgs = Message.query.order_by(Message.created_at.asc()).limit(200).all()
        return jsonify([{'id':m.id,'username':m.username,'text':m.text,'created_at':m.created_at.isoformat()} for m in msgs])
    else:
        if not current_user.is_authenticated:
            return jsonify({'error':'login required'}), 403
        data = request.get_json() or {}
        text = data.get('text','').strip()
        if not text:
            return jsonify({'error':'empty'}), 400
        m = Message(user_id=current_user.id, username=current_user.username, text=text)
        db.session.add(m); db.session.commit()
        return jsonify({'ok':True,'id':m.id})

# Polls
@app.route('/polls', methods=['GET','POST'])
def polls():
    form = PollForm()
    if form.validate_on_submit():
        opts = [o.strip() for o in form.options.data.split('|') if o.strip()]
        p = Poll(question=form.question.data, options=json.dumps(opts))
        db.session.add(p); db.session.commit()
        flash('Опрос создан', 'success')
        return redirect(url_for('polls'))
    polls = Poll.query.order_by(Poll.id.desc()).all()
    return render_template('polls.html', form=form, polls=polls)

@app.route('/poll/<int:pid>', methods=['GET','POST'])
def poll_view(pid):
    p = Poll.query.get_or_404(pid)
    opts = json.loads(p.options)
    # handle both form POST (traditional) and JSON POST (AJAX)
    if request.method == 'POST':
        if request.is_json:
            data = request.get_json() or {}
            try:
                idx = int(data.get('option', -1))
            except:
                idx = -1
        else:
            try:
                idx = int(request.form.get('option', -1))
            except:
                idx = -1
        if not current_user.is_authenticated:
            flash('Войдите чтобы проголосовать', 'warning'); return redirect(url_for('login'))
        if idx<0 or idx>=len(opts):
            flash('Неправильный выбор', 'warning'); return redirect(url_for('poll_view', pid=pid))
        existing = Vote.query.filter_by(user_id=current_user.id, poll_id=pid).first()
        if existing:
            flash('Вы уже голосовали', 'info'); return redirect(url_for('poll_view', pid=pid))
        v = Vote(user_id=current_user.id, poll_id=pid, option_index=idx)
        db.session.add(v); db.session.commit()
        flash('Спасибо за голос', 'success'); return redirect(url_for('poll_view', pid=pid))
    votes = Vote.query.filter_by(poll_id=pid).all()
    counts = [0]*len(opts)
    for v in votes:
        if 0<=v.option_index<len(counts): counts[v.option_index]+=1
    return render_template('poll_view.html', poll=p, options=opts, counts=counts, votes=len(votes))

# Clicker
@app.route('/click', methods=['GET','POST'])
@login_required
def clicker():
    if request.method == 'POST':
        data = request.get_json() or {}
        delta = int(data.get('delta',1))
        current_user.points = (current_user.points or 0) + delta
        db.session.add(current_user); db.session.commit()
        return jsonify({'points': current_user.points})
    return render_template('click.html')

# Admin routes
@app.route('/admin')
@login_required
def admin_panel():
    ok_admin = (session.get('admin_mode') and (current_user.is_admin or current_user.is_god)) or current_user.is_god
    if not ok_admin:
        abort(403)
    users = User.query.order_by(User.joined_at.desc()).all()
    return render_template('admin.html', users=users)

@app.route('/toggle_admin')
@login_required
def toggle_admin():
    if not (current_user.is_admin or current_user.is_god):
        flash('У вас нет прав администратора','danger'); return redirect(url_for('index'))
    session['admin_mode'] = not session.get('admin_mode', False)
    flash('Режим администратора ' + ('включён' if session['admin_mode'] else 'выключен'),'info')
    return redirect(url_for('index'))

@app.route('/admin/delete/<int:uid>', methods=['POST'])
@login_required
def admin_delete(uid):
    ok_admin = (session.get('admin_mode') and (current_user.is_admin or current_user.is_god)) or current_user.is_god
    if not ok_admin: abort(403)
    target = User.query.get_or_404(uid)
    if current_user.is_god:
        if target.id == current_user.id:
            return jsonify({'error':'cannot delete self'}), 400
        Message.query.filter_by(user_id=target.id).delete()
        Vote.query.filter_by(user_id=target.id).delete()
        db.session.delete(target); db.session.commit()
        return jsonify({'ok':True})
    else:
        if target.is_admin or target.is_god:
            return jsonify({'error':'cannot delete admin/god'}), 400
        Message.query.filter_by(user_id=target.id).delete()
        Vote.query.filter_by(user_id=target.id).delete()
        db.session.delete(target); db.session.commit()
        return jsonify({'ok':True})

@app.route('/admin/promote/<int:uid>', methods=['POST'])
@login_required
def admin_promote(uid):
    if not current_user.is_god: abort(403)
    u = User.query.get_or_404(uid)
    if u.is_god: return jsonify({'error':'cannot change god'}), 400
    u.is_admin = True; db.session.add(u); db.session.commit()
    return jsonify({'ok':True})

@app.route('/admin/demote/<int:uid>', methods=['POST'])
@login_required
def admin_demote(uid):
    if not current_user.is_god: abort(403)
    u = User.query.get_or_404(uid)
    if u.is_god: return jsonify({'error':'cannot change god'}), 400
    u.is_admin = False; db.session.add(u); db.session.commit()
    return jsonify({'ok':True})

@app.route('/users')
def users_list():
    q = request.args.get('q',''); role = request.args.get('role','all')
    qs = User.query
    if q: qs = qs.filter(User.username.contains(q))
    if role=='admin': qs = qs.filter_by(is_admin=True)
    if role=='god': qs = qs.filter_by(is_god=True)
    users = qs.order_by(User.joined_at.desc()).all()
    return render_template('users.html', users=users, q=q, role=role)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT',5000)))

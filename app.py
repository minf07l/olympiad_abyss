import os
import datetime
import json
from dotenv import load_dotenv

from flask import Flask, render_template, redirect, url_for, flash, request, session, abort, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from flask_wtf import FlaskForm, CSRFProtect
from flask_wtf.csrf import generate_csrf
from wtforms import StringField, PasswordField, TextAreaField, SubmitField
from wtforms.validators import InputRequired, Length, EqualTo

# =========================
#   APP CONFIG
# =========================
load_dotenv()
app = Flask(__name__)
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev-secret-change-me')

# ===== Database selection =====
db_url = os.environ.get('DATABASE_URL')
if db_url:
    # Render/Postgres case
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
else:
    # Local SQLite fallback
    instance_dir = os.path.join(BASE_DIR, 'instance')
    os.makedirs(instance_dir, exist_ok=True)
    sqlite_path = os.path.join(instance_dir, 'app.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f"sqlite:///{sqlite_path}"

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'
csrf = CSRFProtect(app)

# Make helpers available in Jinja
app.jinja_env.globals.update(enumerate=enumerate, len=len, range=range, str=str)

# =========================
#   MODELS
# =========================
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    is_god = db.Column(db.Boolean, default=False)
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
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
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

# =========================
#   FORMS
# =========================
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

# =========================
#   LOGIN MANAGER
# =========================
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

# =========================
#   INIT DB & GOD USER
# =========================
def init_db():
    db.create_all()
    god = User.query.filter_by(is_god=True).first()
    if not god:
        gn = os.environ.get('GOD_USERNAME', 'god')
        gp = os.environ.get('GOD_PASSWORD', 'godpass')
        if gn and gp and not User.query.filter_by(username=gn).first():
            u = User(username=gn, is_god=True, is_admin=True)
            u.set_password(gp)
            db.session.add(u)
            db.session.commit()
            print('Created god user:', gn)

with app.app_context():
    init_db()

# =========================
#   ROUTES
# =========================
@app.route('/')
def index():
    polls = Poll.query.order_by(Poll.id.desc()).limit(6).all()
    top_clickers = User.query.order_by(User.points.desc()).limit(6).all()
    return render_template('index.html', polls=polls, top_clickers=top_clickers)

# тут идут остальные твои маршруты (регистрация, вход, чат, опросы и т.д.)
# их можно оставить без изменений — всё будет работать с Postgres

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))

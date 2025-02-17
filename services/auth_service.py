from flask import session, redirect, url_for, request, render_template
from models.user import User, db
from functools import wraps

class AuthService:
    @staticmethod
    def register_user(username, email, password):
        if User.query.filter_by(username=username).first():
            return False, "用户名已存在"
        if User.query.filter_by(email=email).first():
            return False, "邮箱已被注册"
        
        new_user = User(username=username, email=email)
        new_user.set_password(password)
        db.session.add(new_user)
        db.session.commit()
        return True, "注册成功"

    @staticmethod
    def login_user(username, password):
        user = User.query.filter_by(username=username).first()
        if not user or not user.check_password(password):
            return False, "用户名或密码错误"
        session['user_id'] = user.id
        return True, "登录成功"

    @staticmethod
    def logout_user():
        session.pop('user_id', None)

    @staticmethod
    def get_current_user():
        if 'user_id' in session:
            return User.query.get(session['user_id'])
        return None

    @staticmethod
    def handle_login():
        username = request.form.get('username')
        password = request.form.get('password')
        success, message = AuthService.login_user(username, password)
        if success:
            return redirect(url_for('index'))
        return render_template('login.html', error=message)

    @staticmethod
    def handle_registration():
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        success, message = AuthService.register_user(username, email, password)
        if success:
            return redirect(url_for('login'))
        return render_template('register.html', error=message)

    @staticmethod
    def handle_logout():
        AuthService.logout_user()
        return redirect(url_for('login'))

    @staticmethod
    def login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not AuthService.get_current_user():
                return redirect(url_for('login'))
            return f(*args, **kwargs)
        return decorated_function

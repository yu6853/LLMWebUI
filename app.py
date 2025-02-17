from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from werkzeug.utils import secure_filename
from flask_migrate import Migrate
import os
import uuid
from services.ollama_service import OllamaService
from models.user import db, User
import uuid
from services.ollama_service import OllamaService
from models.user import db, User
from models.message import Message, ConversationThread
from services.auth_service import AuthService
from datetime import datetime

app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-key-'+os.urandom(16).hex())
app.config.update(
    PERMANENT_SESSION_LIFETIME=3600,  # 1小时
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax'
)
ollama = OllamaService()

# 确保上传目录存在
os.makedirs('uploads', exist_ok=True)

# 数据库配置
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)), 'site.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# 初始化数据库迁移
migrate = Migrate(app, db)


@app.route('/', endpoint='index')
@AuthService.login_required
def index():
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'], endpoint='login')
def login():
    if request.method == 'POST':
        response = AuthService.handle_login()
        # 设置持久会话
        session.permanent = True  
        return response
    return render_template('login.html')

@app.route('/favicon.ico')
def favicon():
    return app.send_static_file('favicon.ico')

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.route('/register', methods=['GET', 'POST'], endpoint='register')
def register():
    if request.method == 'POST':
        return AuthService.handle_registration()
    return render_template('register.html')

@app.route('/logout', endpoint='logout')
def logout():
    return AuthService.handle_logout()

@app.route('/conversations', methods=['GET'], endpoint='get_conversations')
@AuthService.login_required
def get_conversations():
    user = AuthService.get_current_user()
    conversations = db.session.query(
        Message.conversation_id,
        db.func.max(Message.timestamp).label('last_activity'),
        db.func.count(Message.id).label('message_count')
    ).filter_by(user_id=user.id).group_by(Message.conversation_id).all()
    
    return jsonify([{
        'id': conv.conversation_id,
        'last_activity': conv.last_activity.isoformat(),
        'message_count': conv.message_count
    } for conv in conversations])

@app.route('/conversations/<conversation_id>', methods=['GET'], endpoint='get_conversation')
@AuthService.login_required
def get_conversation(conversation_id):
    user = AuthService.get_current_user()
    messages = Message.query.filter_by(
        user_id=user.id,
        conversation_id=conversation_id
    ).order_by(Message.timestamp.asc()).all()
    
    return jsonify([msg.to_dict() for msg in messages])

@app.route('/chat', methods=['POST'], endpoint='chat')
@AuthService.login_required
def chat():
    user = AuthService.get_current_user()
    
    # 获取或创建会话ID
    conversation_id = request.form.get('conversation_id') or str(uuid.uuid4())
    
    # 获取消息内容
    message_content = request.form.get('message', '')
    
    # 处理文件上传
    file_path = None
    if 'file' in request.files:
        file = request.files['file']
        if file.filename != '':
            filename = secure_filename(file.filename)
            file_path = os.path.join('uploads', filename)
            file.save(file_path)
    
    # 保存用户消息
    user_message = Message(
        content=message_content,
        is_user=True,
        user_id=user.id,
        conversation_id=conversation_id,
        file_path=file_path
    )
    db.session.add(user_message)
    db.session.commit()

    try:
        model_response = ollama.generate_response(
            prompt=message_content,
            user_id=user.id,
            conversation_id=conversation_id,
            file_path=file_path
        )
        db.session.add(model_response)
        db.session.commit()
    except Exception as e:
        print(f"[ERROR]生成回复错误:{str(e)}")
        model_response = "生成回复错误"

    # 返回响应时包含conversation_id
    return jsonify({
        "success": True,
        "conversation_id": conversation_id,
        "user_message": user_message.to_dict(),
        "model_response": model_response
    })

if __name__ == '__main__':
    app.run(debug=True)
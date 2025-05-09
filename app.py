from flask import Flask, render_template, request, jsonify, redirect, url_for, session
from flask_migrate import Migrate
from werkzeug.utils import secure_filename

from services.ollama_service import OllamaService
from services.file_service import process_file
from models.user import db, User
from models.message import Message, ConversationThread
from services.auth_service import AuthService
import os


app = Flask(__name__, static_folder='static')
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'dev-key-' + os.urandom(16).hex())
app.config.update(
    PERMANENT_SESSION_LIFETIME=3600,  # 1小时
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax'
)
ollama = OllamaService()

# 确保上传目录存在
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)


# 数据库配置
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(os.path.abspath(os.path.dirname(__file__)),
                                                                    'site.db')
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
        ConversationThread.id,
        ConversationThread.title,
        ConversationThread.created_at,
        db.func.max(Message.timestamp).label('last_activity'),
        db.func.count(Message.id).label('message_count')
    ).join(
        Message, Message.conversation_id == ConversationThread.id
    ).filter_by(user_id=user.id).group_by(Message.conversation_id).all()

    return jsonify([{
        'id': conv.id,
        'title': conv.title,
        'created_at': conv.created_at.isoformat(),
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
    if not request.form.get('conversation_id'):
        conversation_thread = ConversationThread(
            title = "新对话",
            user_id = user.id,
        )

        # 新建对话线程并提交到数据库
        db.session.add(conversation_thread)
        db.session.commit()
        conversation_id = conversation_thread.id
    else:
        # 使用现有会话id
        conversation_id = int(request.form.get('conversation_id'))

    # 获取消息内容
    message_content = request.form.get('message', '')

    # 解析文件路径
    file_path = None
    if 'file' in request.files:
        file = request.files['file']
        if file.filename != '':
            filename = secure_filename(file.filename)
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            file.save(file_path)
            print(f"上传的文件名:{file.filename}")

    # 处理上传的文件
    file_text = None
    if 'file' in request.files:
        file = request.files['file']
        file_text = process_file(file)  # 提取文件内容

    # 如果文件有内容，使用文件内容作为输入消息
    if file_text:
        message_content = file_text  # 更新消息内容为文件内容

    # 保存用户消息
    user_message = Message(
        content=message_content,
        is_user=True,
        user_id=user.id,
        conversation_id=conversation_id,
        file_path=file_path
    )

    # 确保没有重复对象
    existing_message = Message.query.filter_by(content=message_content, conversation_id=conversation_id).first()
    if not existing_message:
        db.session.add(user_message)
        db.session.commit()

    # 获取模型响应
    model_response = ollama.generate_response(
        prompt=message_content,
        user_id=user.id,
        conversation_id=conversation_id,
        file_path=file_path
    )

    # Ensure the model response is an instance of Message and add to session
    ai_message = Message(
        content=model_response,
        is_user=False,  # This is from the model
        user_id=user.id,
        conversation_id=conversation_id,
        file_path=str(file_path) if file_path else None
    )

    db.session.add(ai_message)
    db.session.commit()

    # 返回响应时包含conversation_id
    return jsonify({
        "success": True,
        "conversation_id": conversation_id,
        "user_message": user_message.to_dict(),
        "model_response": ai_message.to_dict()
    })

# 删除对话
@app.route('/delete_conversation/<int:conversation_id>', methods=['DELETE'])
@AuthService.login_required
def delete_conversation(conversation_id):
    user = AuthService.get_current_user()

    # 获取并删除对话及相关消息
    conversation = ConversationThread.query.filter_by(id=conversation_id, user_id=user.id).first()

    if not conversation:
        return jsonify({"error": "对话不存在或无权限删除"}), 404

    # 删除与对话相关的消息
    Message.query.filter_by(conversation_id=conversation_id).delete()
    db.session.delete(conversation)
    db.session.commit()

    return jsonify({"success": True})


if __name__ == '__main__':
    app.run()

from datetime import datetime
from models.user import db

class ConversationThread(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    messages = db.relationship('Message', backref='thread', lazy=True)

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    is_user = db.Column(db.Boolean, default=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    conversation_id = db.Column(db.Integer, db.ForeignKey('conversation_thread.id'), nullable=False)
    file_path = db.Column(db.String(200))

    def to_dict(self):
        return {
            "id": self.id,
            "content": self.content,
            "is_user": self.is_user,
            "timestamp": self.timestamp.isoformat(),
            "conversation_id": self.conversation_id,
            "file_path": self.file_path
        }

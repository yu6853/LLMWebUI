import requests
from typing import List, Dict
from pathlib import Path
import hashlib
import numpy as np
import faiss
from PyPDF2 import PdfReader
from docx import Document
from sentence_transformers import SentenceTransformer
from .searxng_service import SearXNGService
from models.message import Message
from models.user import db

class OllamaService:
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url
        self.context_window = 8192  # 扩大上下文窗口
        self.max_context_items = 10  # 新增最大上下文条目限制
        self.conversation_history: List[Dict] = []
        self.searxng = SearXNGService()
        
        # 初始化向量数据库
        self.embedder = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        self.index = faiss.IndexFlatL2(384)  # 匹配模型维度
        self.context_vectors = []
        
    def check_connection(self) -> bool:
        """检查Ollama服务是否可用"""
        try:
            response = requests.get(f"{self.base_url}/", timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException:
            return False
        
    def _generate_embedding(self, text: str) -> np.ndarray:
        return self.embedder.encode([text])[0]
    
    def _update_vector_db(self, text: str):
        vector = self._generate_embedding(text).reshape(1, -1)
        self.index.add(vector)
        self.context_vectors.append(text)
        
    def _get_relevant_context(self, query: str, k: int = 3) -> List[str]:
        query_vec = self._generate_embedding(query).reshape(1, -1)
        _, indices = self.index.search(query_vec, k)
        return [self.context_vectors[i] for i in indices[0] if i < len(self.context_vectors)]
    
    def _manage_context(self, new_message: str):
        self._update_vector_db(new_message)
        if len(self.context_vectors) > 20:
            self.index.remove_ids(np.array([0]))
            self.context_vectors.pop(0)

    def process_file(self, file_path: Path):
        try:
            if file_path.suffix.lower() == '.pdf':
                with open(file_path, 'rb') as f:
                    reader = PdfReader(f)
                    text_content = "\n".join([page.extract_text() for page in reader.pages])
            
            elif file_path.suffix.lower() in ('.doc', '.docx'):
                doc = Document(file_path)
                text_content = "\n".join([para.text for para in doc.paragraphs])
            
            else:
                text_content = f"【不支持的文件类型】{file_path.name}"
            
            if text_content.strip():
                self._manage_context(f"文件内容：{text_content[:2000]}...")
                
        except Exception as e:
            self._manage_context(f"【文件处理错误】{str(e)}")

    def generate_response(self, prompt: str, user_id: int, conversation_id: int, file_path: Path = None) -> str:

        print(f"[DEBUG] 用户输入: {prompt}")
        if file_path:
            self.process_file(file_path)
            
        self._manage_context(prompt)
        
        search_context = self.searxng.get_search_context(prompt)
        if search_context:
            self._manage_context(search_context)

        relevant_context = self._get_relevant_context(prompt)
        context_block = "\n".join(relevant_context + [search_context if search_context else ""])
        
        try:
            if not self.check_connection():
                return "错误：无法连接Ollama服务，请检查是否已启动"
                
            response = requests.post(
                f"{self.base_url}/api/generate",
                json={
                    "model": "deepseek-r1:1.5b",
                    "prompt": f"请基于以下上下文用中文回答，保持自然对话风格：\n【相关上下文】\n{context_block}\n\n【用户问题】{prompt}\n【回答要求】用markdown格式，包含必要的信息来源说明",
                    "stream": False
                },
                timeout=30
            )
            response.raise_for_status()
            
            # 保存AI响应到数据库
            ai_message = Message(
                content=response.json()["response"],
                is_user=False,
                user_id=user_id,
                conversation_id=conversation_id,
                file_path=str(file_path) if file_path else None
            )
            db.session.add(ai_message)
            db.session.commit()
            
            return ai_message.content
        except Exception as e:
            return f"错误：{str(e)}"

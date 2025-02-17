import requests
from typing import List, Dict

class SearXNGService:
    def __init__(self, base_url: str = "http://localhost:8080"):
        self.base_url = base_url
        self.timeout = 10  # 请求超时时间

    def search(self, query: str, lang: str = 'zh') -> List[Dict]:
        """执行网页搜索并返回格式化结果"""
        try:
            params = {
                'q': query,
                'format': 'json',
                'language': lang,
                'safesearch': 1
            }
            response = requests.get(
                f"{self.base_url}/search",
                params=params,
                timeout=self.timeout
            )
            response.raise_for_status()
            
            return self._format_results(response.json()['results'])
            
        except Exception as e:
            return [{"title": "搜索服务不可用", "content": str(e)}]

    def _format_results(self, results: List[Dict]) -> List[Dict]:
        """格式化搜索结果"""
        formatted = []
        for result in results[:3]:  # 取前3个结果
            formatted.append({
                "title": result.get('title', '无标题'),
                "content": result.get('content', ''),
                "url": result.get('url', '#')
            })
        return formatted

    def get_search_context(self, query: str) -> str:
        """生成搜索上下文提示"""
        results = self.search(query)
        if not results:
            return ""
            
        context = "【网络搜索结果】\n"
        for i, result in enumerate(results, 1):
            context += f"{i}. {result['title']}: {result['content'][:200]}...\n"
        return context
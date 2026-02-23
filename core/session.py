from datetime import datetime
from typing import List, Dict, Optional

class SessionManager:
    """会话管理器 (v3.0.0 Refactored)
    负责管理不同用户的运维隔离会话历史。
    """

    def __init__(self, plugin_instance):
        self.plugin = plugin_instance
        self._history_cache = {}

    async def get_history(self, user_id: str, max_messages: int = 20) -> List[Dict]:
        """获取指定用户的会话历史。"""
        history_key = f"ops_history_{user_id}"
        history = await self.plugin.get_kv_data(history_key, [])
        return history[-max_messages:] if max_messages > 0 else history

    async def save_message(self, user_id: str, role: str, content: str):
        """保存单条消息到用户会话。"""
        history_key = f"ops_history_{user_id}"
        history = await self.plugin.get_kv_data(history_key, [])
        history.append({
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat()
        })
        # 限制存储长度，避免 KV 过大
        if len(history) > 100:
            history = history[-100:]
        await self.plugin.put_kv_data(history_key, history)

    async def clear_session(self, user_id: str):
        """清空会话内容。"""
        history_key = f"ops_history_{user_id}"
        await self.plugin.put_kv_data(history_key, [])

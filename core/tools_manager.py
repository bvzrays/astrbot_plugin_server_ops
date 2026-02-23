from typing import List, Dict, Any, Type
import importlib
import inspect
from astrbot.core.agent.tool import FunctionTool

class ToolsRegistry:
    """工具注册中心 (v3.0.0 Refactored)
    负责动态加载和注入上下文。
    """

    def __init__(self, plugin_instance, ssh_mgr):
        self.plugin = plugin_instance
        self.ssh_mgr = ssh_mgr
        self._tools = []

    def register_tool(self, tool_class):
        """注册并实例化工具，自动注入 context。"""
        # 如果是类，则实例化；如果是实例，则补充上下文
        if inspect.isclass(tool_class):
            tool = tool_class()
        else:
            tool = tool_class

        # 依赖注入 (鸭子类型判断)
        if hasattr(tool, 'ssh_mgr'):
            tool.ssh_mgr = self.ssh_mgr
        if hasattr(tool, 'plugin'):
            tool.plugin = self.plugin
        
        self._tools.append(tool)

    def get_tools(self) -> List[FunctionTool]:
        """返回已实例化的工具列表。"""
        return self._tools

    @property
    def tool_names(self) -> List[str]:
        return [t.name for t in self._tools]

"""Base tool class using the correct AstrBot FunctionTool API."""
from dataclasses import dataclass, field
from astrbot.api import FunctionTool
from astrbot.api.event import AstrMessageEvent
from typing import Any


@dataclass
class OpsTool(FunctionTool):
    """Base class for all Server Ops tools.
    
    Subclasses must set: name, description, parameters.
    They must implement:  run(self, event, **kwargs)
    Context (ssh_mgr, plugin) is injected after construction.
    """
    name: str = ""
    description: str = ""
    parameters: dict = field(default_factory=lambda: {"type": "object", "properties": {}})

    # Injected after construction
    ssh_mgr: Any = field(default=None, repr=False)
    plugin: Any = field(default=None, repr=False)
    workspace: Any = field(default=None, repr=False)  # pathlib.Path

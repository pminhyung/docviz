"""
Tool Registry

Manages custom tool loading, validation, and execution.
Tools are loaded dynamically from .py files using duck typing.

Custom tools can override built-in tools by using the same name.
Built-in tools are backed up and can be restored.
"""

import importlib.util
import inspect
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Any, Optional, Set

from .tool_actions import ToolContext, VALID_TOOL_TYPES


class ToolValidationError(Exception):
    """Raised when a tool fails duck typing validation"""
    pass


class ToolExecutionError(Exception):
    """Raised when a tool fails during execution"""
    pass


class ToolRegistry:
    """
    Registry for custom tools loaded from .py files.

    Tools are validated using duck typing - they must have:
    - name: str (unique tool name)
    - description: str (LLM-visible description)
    - parameters: dict (JSON Schema)
    - tool_type: str ("search" or "inference")
    - execute(args: dict, context: dict) -> str

    Custom tools can override built-in tools by registering with the same name.
    Built-in tools are backed up and can be restored via restore_builtin().

    Usage:
        registry = ToolRegistry()
        loaded_names = registry.load_from_file("/path/to/my_tools.py")
        result = registry.execute("my_tool", {"arg": "value"}, context)
    """

    # Built-in tool names
    BUILTIN_NAMES: Set[str] = {
        "search",
        "ReadFullDocument",
        "ReadFullText",
        "GetPage",
    }

    def __init__(self, include_builtin: bool = True):
        """
        Initialize registry.

        Args:
            include_builtin: If True, automatically load built-in tools
        """
        self._tools: Dict[str, Any] = {}  # name -> tool instance
        self._tool_metadata: Dict[str, Dict[str, Any]] = {}  # name -> metadata
        self._builtin_tools: Dict[str, Any] = {}  # name -> backed-up builtin instance

        if include_builtin:
            self._load_builtin_tools()

    def load_from_file(self, py_path: str, allow_override: bool = True) -> List[str]:
        """
        Load tool classes from a .py file.

        The file is copied to a temporary directory and imported dynamically.
        All classes with valid duck typing attributes are registered.

        Args:
            py_path: Path to the .py file containing tool classes
            allow_override: If True, custom tools can override built-in tools

        Returns:
            List of registered tool names

        Raises:
            FileNotFoundError: If py_path doesn't exist
            ToolValidationError: If no valid tools found
        """
        path = Path(py_path)
        if not path.exists():
            raise FileNotFoundError(f"Tool file not found: {py_path}")

        if not path.suffix == ".py":
            raise ValueError(f"Tool file must be .py: {py_path}")

        # Create temporary directory for safe import
        temp_dir = tempfile.mkdtemp(prefix="doc_agent_tools_")

        try:
            # Copy file to temp directory
            temp_file = Path(temp_dir) / path.name
            shutil.copy2(path, temp_file)

            # Generate unique module name
            module_name = f"custom_tools_{path.stem}_{id(self)}"

            # Load module dynamically
            spec = importlib.util.spec_from_file_location(module_name, temp_file)
            if spec is None or spec.loader is None:
                raise ImportError(f"Cannot load module from: {py_path}")

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # Find and register tool classes
            registered_names = []
            for name, obj in inspect.getmembers(module, inspect.isclass):
                # Skip base classes or imports
                if obj.__module__ != module_name:
                    continue

                # Try to validate and register
                try:
                    self._validate_tool_class(obj)
                    instance = obj()

                    # Handle override: back up builtin if custom uses same name
                    if allow_override and instance.name in self.BUILTIN_NAMES:
                        if instance.name in self._tools:
                            self._builtin_tools[instance.name] = self._tools[instance.name]
                        self.register(instance, override=True)
                    else:
                        self.register(instance, override=allow_override)

                    registered_names.append(instance.name)
                except (ToolValidationError, TypeError) as e:
                    # Skip classes that don't meet requirements
                    continue

            if not registered_names:
                raise ToolValidationError(
                    f"No valid tool classes found in: {py_path}. "
                    "Tools must have: name, description, parameters, tool_type, execute()"
                )

            return registered_names

        finally:
            # Clean up temp directory
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

    def register(self, tool_instance: Any, override: bool = False) -> None:
        """
        Register a tool instance.

        Args:
            tool_instance: Tool instance with required duck typing attributes
            override: If True, replace existing tool with same name

        Raises:
            ToolValidationError: If validation fails
        """
        self._validate_tool_instance(tool_instance)

        name = tool_instance.name

        # Prevent duplicate registration unless override
        if name in self._tools and not override:
            return

        self._tools[name] = tool_instance
        self._tool_metadata[name] = {
            "name": name,
            "description": tool_instance.description,
            "parameters": tool_instance.parameters,
            "tool_type": tool_instance.tool_type,
        }

    def unregister(self, name: str) -> bool:
        """
        Unregister a tool by name.

        Args:
            name: Tool name to unregister

        Returns:
            True if tool was unregistered, False if not found
        """
        if name in self._tools:
            del self._tools[name]
            del self._tool_metadata[name]
            return True
        return False

    def restore_builtin(self, name: str) -> bool:
        """
        Restore a built-in tool that was overridden by a custom tool.

        Args:
            name: Built-in tool name to restore

        Returns:
            True if restored, False if no backup found
        """
        if name in self._builtin_tools:
            self._tools[name] = self._builtin_tools[name]
            instance = self._builtin_tools[name]
            self._tool_metadata[name] = {
                "name": instance.name,
                "description": instance.description,
                "parameters": instance.parameters,
                "tool_type": instance.tool_type,
            }
            del self._builtin_tools[name]
            return True
        return False

    def has_tool(self, name: str) -> bool:
        """
        Check if a tool is registered.

        Args:
            name: Tool name to check

        Returns:
            True if tool exists in registry
        """
        return name in self._tools

    def execute(
        self,
        name: str,
        args: Dict[str, Any],
        context: ToolContext
    ) -> str:
        """
        Execute a registered tool.

        Args:
            name: Tool name to execute
            args: Tool arguments dictionary
            context: ToolContext with execution context

        Returns:
            Tool result as string

        Raises:
            KeyError: If tool not found
            ToolExecutionError: If execution fails
        """
        if name not in self._tools:
            raise KeyError(f"Tool not found: {name}")

        tool = self._tools[name]

        try:
            # Convert context to dict for duck typing compatibility
            context_dict = context.to_dict()

            # Expose builtin tools reference so custom tools can wrap builtins
            context_dict["_builtin_tools"] = self._builtin_tools

            result = tool.execute(args, context_dict)

            # Ensure result is string
            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False)

            return result

        except Exception as e:
            raise ToolExecutionError(f"Tool '{name}' failed: {e}") from e

    def get_tools_for_prompt(self) -> List[Dict[str, Any]]:
        """
        Get tool definitions for prompt injection.

        Returns:
            List of tool definition dicts with name, description, parameters
        """
        return [
            {
                "name": meta["name"],
                "description": meta["description"],
                "parameters": meta["parameters"],
            }
            for meta in self._tool_metadata.values()
        ]

    def get_tool_names(self) -> List[str]:
        """
        Get list of registered tool names.

        Returns:
            List of tool names
        """
        return list(self._tools.keys())

    def get_tool_info(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific tool.

        Args:
            name: Tool name

        Returns:
            Tool metadata dict or None if not found
        """
        return self._tool_metadata.get(name)

    def is_custom_tool(self, name: str) -> bool:
        """Check if a tool is custom (not builtin).

        Args:
            name: Tool name to check

        Returns:
            True if the tool is registered and not a builtin tool
        """
        return name in self._tools and name not in self.BUILTIN_NAMES

    def get_builtin_names(self) -> Set[str]:
        """Get the set of built-in tool names that have been backed up."""
        return set(self._builtin_tools.keys())

    def clear(self) -> None:
        """Clear all registered tools"""
        self._tools.clear()
        self._tool_metadata.clear()
        self._builtin_tools.clear()

    def _validate_tool_class(self, cls: type) -> None:
        """
        Validate a tool class has required attributes.

        Args:
            cls: Tool class to validate

        Raises:
            ToolValidationError: If validation fails
        """
        required_attrs = ["name", "description", "parameters", "tool_type"]

        for attr in required_attrs:
            if not hasattr(cls, attr):
                raise ToolValidationError(
                    f"Tool class '{cls.__name__}' missing required attribute: {attr}"
                )

        # Check for execute method
        if not hasattr(cls, "execute") or not callable(getattr(cls, "execute")):
            raise ToolValidationError(
                f"Tool class '{cls.__name__}' missing execute() method"
            )

        # Validate tool_type
        tool_type = getattr(cls, "tool_type")
        if tool_type not in VALID_TOOL_TYPES:
            raise ToolValidationError(
                f"Tool class '{cls.__name__}' has invalid tool_type: {tool_type}. "
                f"Must be one of: {VALID_TOOL_TYPES}"
            )

    def _validate_tool_instance(self, tool: Any) -> None:
        """
        Validate a tool instance has required attributes and valid values.

        Args:
            tool: Tool instance to validate

        Raises:
            ToolValidationError: If validation fails
        """
        required_attrs = ["name", "description", "parameters", "tool_type"]

        for attr in required_attrs:
            if not hasattr(tool, attr):
                raise ToolValidationError(
                    f"Tool instance missing required attribute: {attr}"
                )

        # Validate name is string
        if not isinstance(tool.name, str) or not tool.name.strip():
            raise ToolValidationError("Tool name must be a non-empty string")

        # Validate description is string
        if not isinstance(tool.description, str):
            raise ToolValidationError("Tool description must be a string")

        # Validate parameters is dict
        if not isinstance(tool.parameters, dict):
            raise ToolValidationError("Tool parameters must be a dictionary")

        # Validate tool_type
        if tool.tool_type not in VALID_TOOL_TYPES:
            raise ToolValidationError(
                f"Tool has invalid tool_type: {tool.tool_type}. "
                f"Must be one of: {VALID_TOOL_TYPES}"
            )

        # Validate execute method
        if not hasattr(tool, "execute") or not callable(tool.execute):
            raise ToolValidationError("Tool must have callable execute() method")

        # Check execute signature (should accept args and context)
        sig = inspect.signature(tool.execute)
        params = list(sig.parameters.keys())
        if len(params) < 2:
            raise ToolValidationError(
                "Tool execute() must accept at least 2 parameters: args and context"
            )

    def __len__(self) -> int:
        """Return number of registered tools"""
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        """Check if tool name is registered"""
        return name in self._tools

    def __iter__(self):
        """Iterate over tool names"""
        return iter(self._tools)

    def _load_builtin_tools(self) -> None:
        """
        Load built-in tools from builtin_tools module.

        Built-in tools (search, ReadFullDocument, GetPage, ReadFullText)
        are instantiated and registered automatically.
        """
        from .builtin_tools import BUILTIN_TOOL_CLASSES

        for tool_cls in BUILTIN_TOOL_CLASSES:
            try:
                instance = tool_cls()
                self._validate_tool_instance(instance)
                self._tools[instance.name] = instance
                self._tool_metadata[instance.name] = {
                    "name": instance.name,
                    "description": instance.description,
                    "parameters": instance.parameters,
                    "tool_type": instance.tool_type,
                }
            except Exception as e:
                print(f"[Warning] Failed to load built-in tool {tool_cls.__name__}: {e}")

"""
Base Tool Abstract Class

Custom tools MUST inherit from BaseTool or implement the same interface.
This provides clear documentation of required attributes and methods.

Example:
    from agent.core.base_tool import BaseTool

    class MyCustomTool(BaseTool):
        name = "my_tool"
        description = "Description shown to the LLM"
        parameters = {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search query"}
            },
            "required": ["query"]
        }
        tool_type = "search"  # or "inference"

        def execute(self, args: dict, context: dict) -> str:
            query = args.get("query", "")
            return f"Result for: {query}"
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, ClassVar


class BaseTool(ABC):
    """
    Abstract base class for custom tools.

    All custom tools must define these class attributes and implement execute().
    Tools are validated using duck typing, so inheriting from this class is
    OPTIONAL but RECOMMENDED for IDE support and documentation.

    Class Attributes (REQUIRED):
        name: Unique tool name (used in LLM tool calls)
        description: Tool description shown to the LLM (affects when/how it's used)
        parameters: JSON Schema defining the tool's input parameters
        tool_type: Either "search" (retrieves information) or "inference" (generates content)

    Methods (REQUIRED):
        execute(args, context) -> str: Execute the tool and return result as string
    """

    # =========================================================================
    # REQUIRED CLASS ATTRIBUTES
    # =========================================================================

    name: ClassVar[str]
    """
    Unique identifier for the tool.

    - Must be a non-empty string
    - Must be unique across all registered tools
    - Used by LLM to invoke the tool

    Example: "analyze_chart", "search_database", "translate_text"
    """

    description: ClassVar[str]
    """
    Description shown to the LLM.

    - Should clearly explain what the tool does
    - Should describe when to use it
    - Affects how the LLM decides to use the tool

    Example:
        "Analyze charts and graphs in document images.
         Use this when the user asks about visual data representations."
    """

    parameters: ClassVar[Dict[str, Any]]
    """
    JSON Schema defining input parameters.

    Must follow JSON Schema format with:
    - "type": "object"
    - "properties": dict of parameter definitions
    - "required": list of required parameter names (optional)

    Example:
        {
            "type": "object",
            "properties": {
                "image_path": {
                    "type": "string",
                    "description": "Path to the image file"
                },
                "analysis_type": {
                    "type": "string",
                    "enum": ["chart", "table", "diagram"],
                    "description": "Type of visual to analyze"
                }
            },
            "required": ["image_path"]
        }
    """

    tool_type: ClassVar[str]
    """
    Tool category for execution flow control.

    Must be one of:
    - "search": Tools that retrieve or look up information
              (e.g., search, GetPage, database queries)
    - "inference": Tools that generate or transform content
                  (e.g., summarize, translate, analyze)

    This affects how the agent orchestrates tool calls.
    """

    # =========================================================================
    # REQUIRED METHOD
    # =========================================================================

    @abstractmethod
    def execute(self, args: Dict[str, Any], context: Dict[str, Any]) -> str:
        """
        Execute the tool with given arguments and context.

        This is the main entry point called by the ToolRegistry.
        Must return a string (JSON-serializable results should use json.dumps).

        Args:
            args: Dictionary of tool arguments matching the parameters schema.
                  Example: {"image_path": "/path/to/image.png", "analysis_type": "chart"}

            context: Execution context dictionary containing:
                - user_query (str): The user's original question
                - filenames (List[str]): Document filenames
                - multi_docs (List[List[Dict]]): Document pages data
                - image_dir (Optional[str]): Path to image directory
                - language (str): Output language ("ko" or "en")
                - current_step (int): Current agent step number
                - tool_secrets (Optional[Dict]): Secret values (API keys, etc.)

        Returns:
            str: Tool result as a string.
                 For structured data, use json.dumps(result, ensure_ascii=False).

                 IMAGE OUTPUT (VL Mode):
                 If your tool generates images that should be sent to the VL reasoner,
                 include an "image_paths" key in your JSON output:

                     return json.dumps({
                         "result": "Chart generated",
                         "image_paths": ["/absolute/path/to/image.png"]
                     })

                 - image_paths can be a single string or list of strings
                 - Paths must be absolute paths to existing image files
                 - Supported formats: PNG, JPEG
                 - Only used when reasoner_type="vl" (ignored for "llm")

        Raises:
            Any exception will be caught and wrapped in ToolExecutionError.

        Example:
            def execute(self, args: dict, context: dict) -> str:
                query = args.get("query", "")
                language = context.get("language", "en")

                # Do something...
                result = {"found": True, "data": [...]}

                return json.dumps(result, ensure_ascii=False)

        Example with image output (VL mode):
            def execute(self, args: dict, context: dict) -> str:
                # Generate chart image
                chart_path = "/tmp/chart.png"
                self._create_chart(args["data"], chart_path)

                return json.dumps({
                    "message": "Chart created",
                    "image_paths": [chart_path]  # Will be sent to VL reasoner
                }, ensure_ascii=False)
        """
        pass

    # =========================================================================
    # OPTIONAL METHODS (Override if needed)
    # =========================================================================

    def validate_args(self, args: Dict[str, Any]) -> bool:
        """
        Optional: Validate arguments before execution.

        Override this to add custom validation logic.
        Return False to reject the arguments.

        Args:
            args: Tool arguments to validate

        Returns:
            True if valid, False otherwise
        """
        return True

    def on_error(self, error: Exception, args: Dict[str, Any]) -> str:
        """
        Optional: Custom error handling.

        Override this to provide custom error responses.
        By default, errors are raised to the registry.

        Args:
            error: The exception that occurred
            args: The arguments that caused the error

        Returns:
            Error message string
        """
        raise error


# =============================================================================
# TOOL TYPE CONSTANTS
# =============================================================================

TOOL_TYPE_SEARCH = "search"
"""Tool type for information retrieval tools (search, GetPage, queries)"""

TOOL_TYPE_INFERENCE = "inference"
"""Tool type for content generation tools (summarize, translate, analyze)"""

VALID_TOOL_TYPES = {TOOL_TYPE_SEARCH, TOOL_TYPE_INFERENCE}
"""Set of valid tool_type values"""

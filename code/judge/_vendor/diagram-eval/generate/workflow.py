from __future__ import annotations
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

import os
import yaml
from dataclasses import dataclass
from typing import Optional
from io import BytesIO

from google import genai
from PIL import Image
from pydantic import BaseModel, Field, ValidationError

from utils.structured_llm import StructuredLLM


class LayoutPlan(BaseModel):
    """Structured plan describing the intended layout for a diagram."""
    thinking_phase: str = Field(description="Your thinking process")
    key_components: list[str] = Field(description="Main components/modules to include in the diagram")
    relationships: list[str] = Field(description="Key relationships and flows between components")
    layout_structure: str = Field(description="Suggested layout of the diagram, including the approximate position of each component")


@dataclass
class DiagramGenerationResult:
    """Aggregates outputs produced during a generation run."""
    image_data: bytes
    image_url: Optional[str]
    plan: Optional[LayoutPlan]

    def save_png(self, destination: Path) -> Path:
        """(destination: Path) -> Path: Write the generated PNG to disk and return the saved path."""
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(self.image_data)
        return destination


class DiagramGenerationWorkflow:
    """
    Orchestrates optional planning followed by diagram generation using Nano Banana API.

    The workflow first gathers a layout plan (if configured) and then calls the
    Nano Banana API to generate SVG code.
    """

    def __init__(
        self,
        *,
        config_path: Path | str,
        use_planner: bool = False,
    ):
        """
        (config_path: Union[Path,str], use_planner: bool = False) -> None: 
        Initialize Google Gemini client for diagram generation.
        
        Args:
            config_path: Path to unified config file (e.g., configs/llm_config.yaml)
            use_planner: Whether to use layout planner (not used for Nano Banana)
        """
        config_path = str(config_path)
        
        # Load full config
        with open(config_path, "r", encoding="utf-8") as f:
            full_config = yaml.safe_load(f)
        
        # Extract generator config section
        gen_config = full_config.get("diagram_generator", {})
        
        # Get API key
        key_file = gen_config.get("key_file")
        api_key_name = gen_config.get("api_key")
        
        config_dir = os.path.dirname(config_path)
        key_file_path = os.path.join(config_dir, key_file)
        
        with open(key_file_path, "r", encoding="utf-8") as f:
            key_store = yaml.safe_load(f)
        
        api_key = key_store.get(api_key_name)
        
        # Initialize Google Gemini client
        self._client = genai.Client(api_key=api_key)
        self._model = gen_config.get("model", "gemini-2.5-flash-image")
        
        # Initialize planner if requested
        self._use_planner = use_planner
        if use_planner:
            self._planner = StructuredLLM(config_path, LayoutPlan, config_section="layout_planner")
        else:
            self._planner = None

    def generate(
        self,
        *,
        paper_context: str,
        style_reference_image: Optional[Path | str] = None,
        max_retries: int = 2,
    ) -> DiagramGenerationResult:
        """
        (paper_context: str, style_reference_image: Optional[Path|str]=None, max_retries: int=2) -> DiagramGenerationResult: 
        Execute generation to produce a PNG diagram using Google Gemini.
        
        If planner is enabled, first creates a structured plan focusing on methodology,
        then generates the diagram based on the plan.
        
        Args:
            paper_context: Text describing the research paper
            style_reference_image: Optional path to a reference diagram for visual style guidance
            max_retries: Maximum number of retry attempts
        """
        # Create layout plan if planner is enabled
        plan = None
        if self._use_planner:
            plan = self._create_layout_plan(paper_context=paper_context)
        
        # Generate diagram with plan and optional style reference
        image_data = self._request_diagram(
            paper_context=paper_context, 
            plan=plan,
            style_reference_image=style_reference_image
        )
        return DiagramGenerationResult(image_data=image_data, image_url=None, plan=plan)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    
    def _create_layout_plan(self, *, paper_context: str) -> LayoutPlan:
        """
        Create a structured layout plan focusing on methodology.
        
        Args:
            paper_context: Text describing the research paper
            
        Returns:
            LayoutPlan with methodology focus, components, and relationships
        """
        prompt = f"""
You are a diagram planning expert for research papers. Analyze the following research paper content and create a detailed plan for a diagram that illustrates the METHODOLOGY.

Paper Content:
{paper_context}

Your task is to give a plan consisting of the following features for the sake of planning a diagram:
1. List the main components of the methodology, each of which should be a module box in the diagram.
2. Describe the directed data/control flows between components, each of which should be an arrow in the diagram.
3. Suggest an appropriate layout structure of the diagram, including the approximate position of each component.

Rules:
1. Plan the diagram step by step and put your thinking process in the 'thinking_phase' field before the above three plan features.
2. Focus on listing ALL elements appearing in the methodology section of the paper context as independent components. Do not include any element that does not appear in the methodology section.
4. The ratio of the width to the height of the diagram should be 4:3. Arrange the component layout accordingly and balance the component distribution.
"""
        
        response = self._planner.query(prompt)
        return response
    
    def _request_diagram(
        self, 
        *, 
        paper_context: str, 
        plan: Optional[LayoutPlan] = None,
        style_reference_image: Optional[Path | str] = None
    ) -> bytes:
        """
        Generate diagram PNG using Google Gemini image generation with optional planning and style reference.
        
        Args:
            paper_context: Text describing the research paper
            plan: Optional structured layout plan
            style_reference_image: Optional path to reference diagram for visual style guidance
        """
        if plan:
            # Build prompt with structured plan
            prompt = f"""
Create a clear, professional diagram illustrating the methodology based on the given plan and the paper context.

Paper Content:
{paper_context}

FOLLOWING IS THE PLAN FOR THE DIAGRAM:

KEY COMPONENTS:
{chr(10).join(f"- {comp}" for comp in plan['key_components'])}

RELATIONSHIPS:
{chr(10).join(f"- {rel}" for rel in plan['relationships'])}

LAYOUT STRUCTURE: {plan['layout_structure']}

**INSTRUCTIONS FOR DIAGRAM GENERATION:**
1. **STRICTLY follow the plan when generating the diagram.**
2. Use text annotated boxes, arrows, and labels to represent components and their relationships.
3. Align the text of the components with the content in the paper context and the plan.
4. The ratio of the width to the height of the diagram should be 4:3. 
5. Balance the component distribution and avoid overcrowded or overlapping layout. Fill the whole diagram with the components as much as possible.
6. Only focus on elements appearing in the methodology section of the paper context. For those not in the methodology section, NEVER include them as components.
"""
        else:
            # Simple prompt without planning
            prompt = (
                f"Create a clear, professional diagram illustrating the following research paper content. "
                f"The diagram should show the architecture, methodology, or workflow described in the text. "
                f"Use boxes, arrows, and labels to represent components and their relationships.\n\n"
                f"{paper_context}"
            )
        
        # Add style reference instruction if provided
        if style_reference_image:
            prompt = (
                f"{prompt}\n\n"
                f"Use the following provided reference image as a visual style guide only for referring the color scheme and design elements, "
                f"do not use it as a layout guide. "
            )
        
        # Prepare contents for API call
        contents = [prompt]
        
        # Add reference image if provided
        if style_reference_image:
            reference_path = Path(style_reference_image)
            if reference_path.exists():
                reference_image = Image.open(reference_path)
                contents.append(reference_image)
        
        response = self._client.models.generate_content(
            model=self._model,
            contents=contents,
        )
        
        for part in response.candidates[0].content.parts:
            if part.inline_data is not None:
                return part.inline_data.data
        
        raise RuntimeError("No image data returned from Gemini")


__all__ = ["DiagramGenerationWorkflow", "DiagramGenerationResult", "LayoutPlan"]
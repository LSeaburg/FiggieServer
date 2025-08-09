import logging
from pathlib import Path
from typing import Any, Dict, List, Tuple, TypedDict
import yaml

class ParamSpec(TypedDict, total=False):
    name: str
    type: str
    min: float
    max: float
    default: Any

class AgentSpec(TypedDict):
    label: str
    module: str
    attr: str
    params: List[ParamSpec]

def load_agent_specs() -> Tuple[List[AgentSpec], Dict[str, str]]:
    """Load agent specs from agents/traders.yaml.

    Returns:
        - specs: list of {label, module, attr, params}
        - module_to_attr: mapping module->attr
    """
    current_dir = Path(__file__).resolve().parent
    yaml_path = (current_dir / ".." / "agents" / "traders.yaml").resolve()

    specs: List[AgentSpec] = []
    module_to_attr: Dict[str, str] = {}

    try:
        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f) or []
        for entry in data:
            name = entry.get("name")
            module, attr = entry.get("class", "").split(".", 1)
            params = entry.get("params", []) or []
            specs.append({
                "label": name or attr,
                "module": module,
                "attr": attr,
                "params": params,
            })
            if module and attr:
                module_to_attr[module] = attr
    except Exception:
        logging.getLogger(__name__).exception("Failed loading traders.yaml")

    return specs, module_to_attr


def get_params_for_module(specs: List[AgentSpec], module_name: str) -> List[ParamSpec]:
    for spec in specs:
        if spec["module"] == module_name:
            return spec.get("params", [])
    return []



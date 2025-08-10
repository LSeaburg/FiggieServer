import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, TypedDict
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


# Internal dataclass models with validation
@dataclass
class ParamSpecDC:
    name: str
    type: str = "text"
    min: Optional[float] = None
    max: Optional[float] = None
    default: Any = None

    @classmethod
    def from_raw(cls, raw: Dict[str, Any]) -> "ParamSpecDC":
        name = raw.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("ParamSpec.name is required and must be a non-empty string")
        ptype = raw.get("type") or "text"
        pmin = raw.get("min")
        pmax = raw.get("max")
        default = raw.get("default")
        return cls(name=name, type=str(ptype), min=pmin, max=pmax, default=default)

    def to_dict(self) -> ParamSpec:
        data: ParamSpec = {
            "name": self.name,
            "type": self.type,
        }
        if self.min is not None:
            data["min"] = float(self.min)
        if self.max is not None:
            data["max"] = float(self.max)
        if self.default is not None:
            data["default"] = self.default
        return data


@dataclass
class AgentSpecDC:
    label: str
    module: str
    attr: str
    params: List[ParamSpecDC] = field(default_factory=list)

    @classmethod
    def from_yaml_entry(cls, entry: Dict[str, Any]) -> "AgentSpecDC":
        class_str = entry.get("class", "")
        if not isinstance(class_str, str) or "." not in class_str:
            raise ValueError("Invalid or missing 'class' field; expected 'module.attr'")
        module, attr = class_str.split(".", 1)
        label = entry.get("name") or attr
        params_raw = entry.get("params") or []
        params: List[ParamSpecDC] = []
        for p in params_raw:
            try:
                params.append(ParamSpecDC.from_raw(p or {}))
            except Exception:
                logging.getLogger(__name__).warning("Skipping invalid parameter spec for %s.%s", module, attr)
        return cls(label=label, module=module, attr=attr, params=params)

    def to_dict(self) -> AgentSpec:
        return {
            "label": self.label,
            "module": self.module,
            "attr": self.attr,
            "params": [p.to_dict() for p in self.params],
        }


def load_agent_specs() -> Tuple[List[AgentSpec], Dict[str, str]]:
    """Load and validate agent specs from agents/traders.yaml.

    Returns:
        - specs: list of {label, module, attr, params}
        - module_to_attr: mapping module->attr
    """
    current_dir = Path(__file__).resolve().parent
    yaml_path = (current_dir / ".." / ".." / "agents" / "traders.yaml").resolve()

    specs: List[AgentSpec] = []
    module_to_attr: Dict[str, str] = {}

    try:
        with open(yaml_path, "r") as f:
            data = yaml.safe_load(f) or []
        for entry in data:
            try:
                dc = AgentSpecDC.from_yaml_entry(entry or {})
            except Exception:
                logging.getLogger(__name__).warning("Skipping invalid trader entry in YAML")
                continue
            specs.append(dc.to_dict())
            module_to_attr[dc.module] = dc.attr
    except Exception:
        logging.getLogger(__name__).exception("Failed loading traders.yaml")

    return specs, module_to_attr


def get_params_for_module(specs: List[AgentSpec], module_name: str) -> List[ParamSpec]:
    # Build a temporary index for faster lookups when called frequently
    index = {spec.get("module"): spec.get("params", []) for spec in specs}
    return index.get(module_name, [])


def get_spec_by_module(specs: List[AgentSpec], module_name: str) -> Optional[AgentSpec]:
    for spec in specs:
        if spec.get("module") == module_name:
            return spec
    return None


def validate_params(extra_kwargs: Dict[str, Any], spec: AgentSpec) -> Tuple[Dict[str, Any], List[str]]:
    """Validate and coerce extra_kwargs according to the provided spec.

    Returns (coerced_kwargs, errors)
    """
    errors: List[str] = []
    coerced: Dict[str, Any] = {}
    params = spec.get("params", [])
    for p in params:
        name = p.get("name")
        if not name:
            continue
        ptype = p.get("type", "text")
        pmin = p.get("min")
        pmax = p.get("max")
        default = p.get("default")
        value = extra_kwargs.get(name, default)
        try:
            if ptype == "int" and value is not None:
                value = int(value)
            elif ptype == "float" and value is not None:
                value = float(value)
            elif ptype == "bool" and value is not None:
                value = bool(value)
        except (TypeError, ValueError):
            errors.append(f"Parameter '{name}' has invalid type")
            continue
        if ptype in ("int", "float") and (pmin is not None or pmax is not None) and value is None:
            errors.append(f"Parameter '{name}' is required and must be a number")
            continue
        try:
            if pmin is not None and value is not None and value < pmin:
                errors.append(f"'{name}' must be >= {pmin}")
            if pmax is not None and value is not None and value > pmax:
                errors.append(f"'{name}' must be <= {pmax}")
        except TypeError:
            pass
        coerced[name] = value
    return coerced, errors

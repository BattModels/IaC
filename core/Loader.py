import yaml
import inspect
from typing import Dict, Any
import sys
from core.Register import autodiscover_resources, RESOURCE_TYPES
from core.Resource import Resource
from core.LabNetwork import LabNetwork
from core.ControlModule import ControlModule
from enum import Enum

def get_enum_classes_defined_in(cls):
    """Return all Enum classes defined directly inside a given class."""
    enums = []
    for name, obj in cls.__dict__.items():
        if inspect.isclass(obj) and issubclass(obj, Enum) and obj is not Enum:
            enums.append(obj)
    return enums

def try_convert_string_to_enum(raw: str, enum_classes):
    """Given a raw string and a list of Enum classes, return first match."""
    raw_upper = raw.upper()

    for enum_cls in enum_classes:
        if raw_upper in enum_cls.__members__:
            return enum_cls[raw_upper]

    return raw   # no match

def resolve_enum_for_class(cls, raw_value):
    """
    Search for an Enum match starting from cls, then Instrument, then Resource.
    Only convert YAML strings.
    """
    if not isinstance(raw_value, str):
        return raw_value

    # Collect enums in order of priority: cls → parents → Resource
    enum_search_order = []

    # Walk MRO but stop at Resource
    for base in cls.__mro__:
        enum_search_order.extend(get_enum_classes_defined_in(base))
        if base.__name__ == "Resource":
            break

    # Attempt conversion
    return try_convert_string_to_enum(raw_value, enum_search_order)

# ------------------------------------------------------------
# Construct resource from YAML spec dynamically
# ------------------------------------------------------------
def construct_resource(name: str, spec: Dict[str, Any]) -> Resource:
    """
    Fully dynamic loader:
      - Inspect __init__ signature
      - YAML keys -> constructor parameters
      - Enum conversion based on class and parent classes
      - No param rules or hard-coded field names
    """

    if "type_name" not in spec:
        raise ValueError(f"Resource '{name}' missing 'type_name' field")

    type_name = spec["type_name"]
    if type_name not in RESOURCE_TYPES:
        raise ValueError(f"Unknown resource type '{type_name}'")

    cls = RESOURCE_TYPES[type_name]
    sig = inspect.signature(cls.__init__)
    kwargs = {}

    for param in sig.parameters.values():

        if param.name == "self":
            continue

        # Inject resource.name automatically
        if param.name == "name":
            kwargs["name"] = name
            continue

        # *args / **kwargs ignored safely
        if param.kind in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        ):
            continue

        # YAML-provided?
        if param.name in spec:
            raw = spec[param.name]
            # Enum resolution
            kwargs[param.name] = resolve_enum_for_class(cls, raw)
            continue

        # Default available?
        if param.default is not inspect._empty:
            kwargs[param.name] = param.default
            continue

        # Missing required parameter
        raise TypeError(
            f"Missing required parameter '{param.name}' "
            f"for resource '{name}' (type={type_name}). "
            f"Available YAML: {list(spec.keys())}"
        )

    # Instantiate the resource
    try:
        return cls(**kwargs)
    except Exception as e:
        raise TypeError(f"Error constructing resource '{name}' ({type_name}): {e}")



# ------------------------------------------------------------
# Resolve reference fields (dynamic based on class.ref_fields)
# ------------------------------------------------------------
def auto_resolve_references(resources, specs):
    """
    Automatically detect reference fields based on YAML values:
        - If field is a list of resource names → convert to list[Resource]
        - If field is a string that matches a resource → convert to Resource
        - Otherwise leave it alone
    """
    for name, spec in specs.items():
        obj = resources[name]

        for field, raw in spec.items():


            # --- CASE 1: LIST OF REFERENCES ---
            if isinstance(raw, list) and all(isinstance(x, str) for x in raw):
                if all(x in resources for x in raw):
                    setattr(obj, field, [resources[x] for x in raw])
                    continue  # go next field


# ------------------------------------------------------------
# YAML Loader (Terraform-style)
# ------------------------------------------------------------
def load_iac_yaml(path: str) -> Dict[str, Resource]:
    # Import all plug-ins
    autodiscover_resources()
    # Load resource tree from configuration file
    data = yaml.safe_load(open(path))
    specs = data["resources"]

    resources = {}

    # Pass 1: Instantiate everything
    for name, spec in specs.items():
        resources[name] = construct_resource(name, spec)
    # Pass 2: Resolve links
    auto_resolve_references(resources, specs)
    return resources

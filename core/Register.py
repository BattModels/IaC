import importlib
import pkgutil
from typing import Dict, Type
try:
    from .Resource import Resource
except Exception as e:
    from Resource import Resource
import os, sys

RESOURCE_TYPES: Dict[str, Type] = {}
current_dir = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(current_dir, ".."))
sys.path.insert(0, PROJECT_ROOT)

device_path = os.path.join(current_dir, '..', 'devices')
endpoint_path = os.path.join(current_dir, '..', 'endpoints')


def register_resource(type_name: str):
    """Decorator to register a resource class automatically."""
    def wrapper(cls):
        RESOURCE_TYPES[type_name] = cls
        return cls
    return wrapper

def autodiscover_resources():
    """Auto-import all modules inside devices/ so decorators run."""
    
    for module_info in pkgutil.iter_modules([device_path]):
        module_name = module_info.name
        importlib.import_module(f"devices.{module_name}")
    for module_info in pkgutil.iter_modules([endpoint_path]):
        module_name = module_info.name
        importlib.import_module(f"endpoints.{module_name}")
    for name, cls in RESOURCE_TYPES.items():
        print(f"{name} → {cls}")


if __name__ == '__main__':
    autodiscover_resources()
    for name, cls in RESOURCE_TYPES.items():
        print(f"{name} → {cls}")
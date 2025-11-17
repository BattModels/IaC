import sys
import os

# ------------------------------------------------
# Ensure project root is on PYTHONPATH
# ------------------------------------------------
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "devices"))

from core.Loader import load_iac_yaml
from core.Resource import Resource

# ------------------------------------------------
# TREE PRINTER (SELF-CONTAINED HERE)
# ------------------------------------------------
def print_tree(resources, root, indent=0):
    """
    Dynamic resource tree printer.
    Supports:
        • root as a Resource object
        • root as a resource name string
        • children as Python Resource objects

    resources: dict[str, Resource]
    root: str or Resource
    """

    visited = set()

    def get_attr(obj, key, default=None):
        """Safe attribute getter."""
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    def get_fields(obj):
        """Return a dictionary of public fields for printing."""
        if isinstance(obj, dict):
            return obj
        raw = {}
        for k, v in vars(obj).items():
            if k.startswith("_"):
                continue
            raw[k] = v
        return raw

    def obj_name(obj):
        """Return name of resource regardless of dict/object."""
        if isinstance(obj, str):
            return obj
        return getattr(obj, "name", "<unnamed>")

    def _print(obj, indent):
        obj_id = id(obj)
        if obj_id in visited:
            prefix = "  " * indent
            print(f"{prefix}{obj_name(obj)} (already shown)")
            return

        visited.add(obj_id)

        # If obj is a name string, convert to actual resource
        if isinstance(obj, str):
            obj = resources[obj]

        fields = get_fields(obj)
        prefix = "  " * indent

        rtype = obj.__class__.__name__
        rid = get_attr(obj, "id", "?")

        print(f"{prefix}{obj_name(obj)}  (type={rtype}, id={rid})")

        # Print scalar fields
        for key, val in fields.items():
            if key in ("id", "name"):
                continue
            if callable(val):
                continue
            if isinstance(val, list):
                continue
            print(f"{prefix}  {key}: {val}")

        # Print list fields as children
        for key, val in fields.items():
            if not isinstance(val, list):
                continue

            # Filter list items: only Resource subclasses
            children = [v for v in val if isinstance(v, Resource)]

            if not children:
                # Not children → print raw list
                print(f"{prefix}  {key}: {val}")
                continue

            # Print child subtree
            print(f"{prefix}  {key}:")
            for child in children:
                _print(child, indent + 2)

    # --- determine root object ---
    if isinstance(root, str):
        root_obj = resources[root]
    else:
        root_obj = root

    _print(root_obj, indent)




# ------------------------------------------------
# LOAD YAML AND PRINT TREE
# ------------------------------------------------
if __name__ == "__main__":
    yaml_path = os.path.join(ROOT, "config", "lab_config.yaml")
    resources = load_iac_yaml(yaml_path)
    print("\n==== RESOURCE TREE ====")
    print_tree(resources, resources["lab_network"])

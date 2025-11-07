import yaml
import os
import base64
try:
    # Try importing relative modules if running as part of a package
    from Resource import Resource
    from Instrument import Instrument, ConnectionType, Status
    from Pump import Pump
    from Viscometer import Viscometer
    from Potentiostat import Potentiostat
    from Balance import Balance
    from Valve import Valve
    from Relay import Relay
    from Thermometer import Thermometer
    from Inventory_Manager import InventoryManager
    from Utils import current_dir
except Exception as e:
    # Fallback import for when the file is executed directly (not as a package)
    from .Resource import Resource
    from .Instrument import Instrument, ConnectionType, Status
    from .Pump import Pump
    from .Viscometer import Viscometer
    from .Potentiostat import Potentiostat
    from .Balance import Balance
    from .Valve import Valve
    from .Relay import Relay
    from .Thermometer import Thermometer
    from .Inventory_Manager import InventoryManager
    from .Utils import current_dir

# Map the "type" field in YAML to the corresponding Instrument subclass
INSTRUMENT_CLASSES = {
    "pump": Pump,
    "viscometer": Viscometer,
    "potentiostat": Potentiostat,
    "balance": Balance,
    "valve": Valve,
    "relay": Relay,
    "thermometer": Thermometer,
}

# Mapping for other resource endpoints (non-instruments)
ENDPOINT_CLASSES = {
    "inventory_manager": InventoryManager
}

# Global dictionary to store all resources by their unique ID
resource_map = {}

def build_resource_tree(node, parent=None):
    """
    Recursively builds a tree of Resource objects from a YAML node.

    This function supports nested configurations of lab equipment (e.g., pumps, valves, etc.)
    and other resource endpoints.

    It performs the following steps:
    1. Determines the resource type (instrument, endpoint, or generic Resource)
    2. Instantiates the corresponding class
    3. Recursively processes any child nodes
    4. Adds the resource to a global resource_map if it has an ID

    :param node: Dictionary representing a YAML node.
    :param parent: Parent Resource object, if any.
    :return: The constructed Resource object (root of the subtree).
    """
    if not isinstance(node, dict):
        return None

    # Extract attributes from YAML
    name = node.get("name")
    id_ = node.get("id")
    status_str = node.get("status")

    # Default to AVAILABLE if not specified
    status = Status[status_str.upper()] if status_str else Status.AVAILABLE

    # Determine the type of resource to instantiate
    res_type = node.get("type")

    if res_type and res_type.lower() in INSTRUMENT_CLASSES:
        # The node corresponds to a specific instrument class
        ResourceClass = INSTRUMENT_CLASSES[res_type.lower()]

        # Determine connection type and identifier
        connection_type = node.get("connection_type", "serial").lower()
        if connection_type == "serial":
            identifier = node.get("com_port")  # e.g., "COM3"
        else:  # HID device connection
            identifier = node.get("address")
            identifier = base64.b64decode(identifier)  # Decode Base64-encoded HID address

        # Create instrument instance
        resource = ResourceClass(
            name=name,
            identifier=identifier,
            status=status
        )

    else:
        # Handle generic resources or special endpoint resources
        if res_type and res_type.lower() in ENDPOINT_CLASSES:
            ResourceClass = ENDPOINT_CLASSES[res_type.lower()]
        else:
            ResourceClass = Resource

        # Pass through additional attributes dynamically
        attributes = {k: v for k, v in node.items() if k not in ["name", "id", "status", "type"]}
        resource = ResourceClass(name=name, id=id_, status=status, parent=parent, **attributes)

    # Store resource globally if it has an ID (for later lookup)
    if id_:
        resource_map[id_] = resource

    # Attach this resource as a child of its parent (if any)
    if parent:
        parent.add_child(resource)

    # Recursively build any child nodes under this resource
    for key, value in node.items():
        if isinstance(value, list):
            # Some YAML keys (like "equipment") may contain lists of child resources
            for item in value:
                if isinstance(item, dict):
                    build_resource_tree(item, parent=resource)
        elif isinstance(value, dict):
            # Handle nested child dictionaries
            build_resource_tree(value, parent=resource)

    return resource


def load_lab_config(path=None):
    """
    Loads the entire laboratory configuration from a YAML file
    and constructs a tree of interconnected Resource objects.

    :param path: Optional path to a YAML configuration file.
                 Defaults to "<current_dir>/lab_config.yaml"
    :return: A list of top-level (root) Resource objects.
    """
    path = path or os.path.join(current_dir, "lab_config.yaml")
    with open(path, "r") as f:
        data = yaml.safe_load(f)

    roots = []
    # Each top-level key in YAML corresponds to a separate root resource
    for key, node in data.items():
        root_resource = build_resource_tree(node)
        if root_resource:
            roots.append(root_resource)
    return roots


if __name__ == "__main__":
    # When run directly, load the configuration and print the resource hierarchy
    labs = load_lab_config()

    # Helper function to print the resource tree recursively
    def print_tree(resource, indent=0):
        print("  " * indent + f"- {resource.name} (status={resource.status})")
        for child in resource.children:
            print_tree(child, indent + 1)

    # Print all loaded lab resource trees
    for lab in labs:
        print_tree(lab)

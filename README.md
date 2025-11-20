# IaC-Driven Laboratory Automation Framework

This project implements a lightweight **Infrastructure-as-Code (IaC)** model for automated laboratory workflows.  
Users describe hardware, interconnections, and experiments in YAML.  
The system dynamically loads hardware plugins, constructs resource objects, resolves references, and executes procedures.

---

## 🚀 Features

- **Dynamic plugin discovery**  
  Devices and endpoints are auto-loaded from `devices/` and `endpoints/` via decorators.

- **Fully dynamic YAML loader**  
  No field is hard-coded. Constructor signatures determine how resources are built.

- **Automatic reference resolution**  
  Any YAML list of resource names is automatically converted into live Python objects.

- **Enum auto-detection**  
  YAML strings are converted into Enum values based on the class hierarchy.

- **Supports hierarchical lab structure**  
  `LabNetwork → ControlModule → Device`

---

## 🔌 Adding a New Device Plugin

To add a new device:

### 1. Create a file in **devices/**  
Example: `devices/MySensor.py`

```python
from core.Instrument import Instrument, ConnectionType
from core.Register import register_resource
from core.Resource import Status

@register_resource("my_sensor")
class MySensor(Instrument):
    def __init__(self, name: str, identifier: int, status=Status.AVAILABLE):
        super().__init__(name=name,
                         connection_type=ConnectionType.SERIAL,
                         identifier=identifier,
                         status=status)

    def create(self):
        ...

    def read(self):
        return {"data": "..."}   # must return dict

    def update(self, *args, **kwargs):
        ...

    def delete(self):
        ...
```
### 2. Define Lab Resources in YAML **devices/**
```yaml
my_sensor_1:
  type: my_sensor
  identifier: 6
  status: available
```
Done — the loader will auto-discover it.

---
## Video demo
[![Demo Video](https://img.youtube.com/vi/p8mHIt13qwc/0.jpg)](https://youtu.be/p8mHIt13qwc)

from core.Register import register_resource
from core.Resource import Resource


@register_resource("control_module")
class ControlModule(Resource):
    """
    Represents a Clio control module in your IaC system.
    This resource manages references to:
      - endpoints []
      - equipment []
    Loader will populate these lists dynamically.
    """


    def __init__(self, name, type_name, module_type, id, status=Resource.Status.AVAILABLE, **kwargs):
        super().__init__(name, type_name=type_name, id=id)
        self.status = status
        self.module_type = module_type
        self.endpoints = []
        self.equipment = []


    def update(self, config):
        return self.read()


    def __repr__(self):
        return f"<ControlModule name={self.name}, id={self.id}>"
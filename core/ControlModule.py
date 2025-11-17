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


    def __init__(self, name, id, status=Resource.Status.AVAILABLE, **kwargs):
        super().__init__(name, id=id)
        self.status = status
        self.endpoints = []
        self.equipment = []

    # -------- Terraform-style lifecycle -------- #
    def create(self, config=None):
        return {
            "id": self.id,
            "endpoint_count": len(self.endpoints),
            "equipment_count": len(self.equipment),
        }

    def read(self):
        return {
            "id": self.id,
            "endpoint_count": len(self.endpoints),
            "equipment_count": len(self.equipment),
        }

    def update(self, config):
        return self.read()

    def delete(self):
        # Nothing to delete — virtual construct
        pass

    def __repr__(self):
        return f"<ControlModule name={self.name}, id={self.id}>"
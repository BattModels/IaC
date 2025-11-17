from core.Register import register_resource
from core.Resource import Resource

@register_resource("lab_network")
class LabNetwork(Resource):

    def __init__(self, name, id, location=None, control_modules=None, **kwargs):
        super().__init__(name=name, id=id)

        self.id = id
        self.type = "LabNetwork"
        self.location = location
        self.control_modules = control_modules or []

    def create(self, config=None):
        self.update_status(Resource.Status.AVAILABLE)
        return self.read()

    def read(self):
        return {
            "id": self.id,
            "location": self.location,
            "control_module_count": len(self.control_modules),
        }

    def update(self, config):
        if "location" in config:
            self.location = config["location"]
        return self.read()

    def delete(self):
        # Lab network is virtual — nothing to delete
        pass

    def __repr__(self):
        return f"<LabNetwork name={self.name}, id={self.id}, location={self.location}>"

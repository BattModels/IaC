from core.Register import register_resource
from core.Resource import Resource

@register_resource("lab_network")
class LabNetwork(Resource):

    def __init__(self, name, id, type_name, location=None, control_modules=None, **kwargs):
        super().__init__(name=name, id=id, type_name=type_name)
        self.id = id
        self.location = location
        self.control_modules = control_modules or []

    def create(self, config=None):
        self.update_status(Resource.Status.AVAILABLE)
        return self.read()


    def update(self, config):
        if "location" in config:
            self.location = config["location"]
        return self.read()

    def delete(self):
        # Lab network is virtual — nothing to delete
        pass

    def __repr__(self):
        return f"<LabNetwork name={self.name}, id={self.id}, location={self.location}>"

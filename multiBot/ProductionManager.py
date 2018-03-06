import battlecode as bc
import random


class ProductionManager:
    def __init__(self, gc):
        self.gc = gc
        self.factories = []
        self.workers = []

    def update(self):
        print('--- Production manager update')
        print(f'Karbonite: {self.gc.karbonite()}')

        self.update_units()
        self.manage_build()

    def update_units(self):
        for unit in self.gc.my_units():
            if unit.unit_type == bc.UnitType.Factory:
                self.factories.append(unit)
            elif unit.unit_type == bc.UnitType.Worker and unit.location.is_on_map():
                self.workers.append(unit)

    def manage_build(self):
        self.produce_units()
        self.build_structures()

    def produce_units(self):
        for f in self.factories:
            if self.gc.can_produce_robot(f.id, bc.UnitType.Ranger):
                self.gc.produce_robot(f.id, bc.UnitType.Ranger)

    def build_structures(self):
        for worker in self.workers:

            # Build nearby blueprints
            nearby = self.gc.sense_nearby_units(worker.location.map_location(), 2)
            for other in nearby:
                if self.gc.can_build(worker.id, other.id):
                    self.gc.build(worker.id, other.id)
                    continue

            # Blueprint new things
            d = random.choice(list(bc.Direction))
            if (self.gc.karbonite() > bc.UnitType.Factory.blueprint_cost()
                    and self.gc.can_blueprint(worker.id, bc.UnitType.Factory, d)):
                self.gc.blueprint(worker.id, bc.UnitType.Factory, d)

    def get_next_build_loc(self):
        # TODO implement next location lookup
        pass


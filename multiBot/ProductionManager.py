from collections import namedtuple
import battlecode as bc
import sys
import random
from LocationUtil import is_empty, cross_directions, find_empty_loc_near
from HashableMapLocation import HashableMapLocation
from functools import reduce
from Pathfinder import a_star_search
from typing import List, Dict, NamedTuple

from UnitController import navigate_unit_to


class Project:
    def __init__(self, karbonite: int, is_in_progress: bool, workers_assigned: int, building_type: bc.UnitType):
        self.karbonite = karbonite  # type: int
        self.is_in_progress = is_in_progress  # type: bool
        self.workers_assigned = workers_assigned  # type: int
        self.building_type = building_type  # type: bc.UnitType


directions = list(bc.Direction)


class ProductionManager:
    def __init__(self, gc: bc.GameController) -> None:
        self.gc = gc  # type: bc.GameController
        self.factories = []  # type: List[bc.Unit]
        self.rockets = []  # type: List[bc.Unit]
        self.idle_workers = []  # type: List[bc.Unit]
        self.figters = []  # type: List[bc.Unit]
        self.projects = dict()  # type: Dict[HashableMapLocation, Project]
        self.karbonite_locations = self.initialize_karbonite_locations()  # type: List[List[int]]
        self.fighter_types = [bc.UnitType.Ranger, bc.UnitType.Knight, bc.UnitType.Mage, bc.UnitType.Healer]

    def initialize_karbonite_locations(self):
        starting_earth_map = self.gc.starting_map(bc.Planet.Earth)  # type: bc.PlanetMap
        width = starting_earth_map.width
        height = starting_earth_map.height
        result = [[0 for _ in range(height)] for _ in range(width)]
        for i in range(width):
            for j in range(height):
                map_location = bc.MapLocation(bc.Planet.Earth, i, j)  # type: bc.MapLocation
                initial_karbonite = starting_earth_map.initial_karbonite_at(map_location)
                if initial_karbonite > 0:
                    result[i][j] = initial_karbonite
        return result

    def available_karbonite(self) -> int:
        return self.gc.karbonite() - reduce(
            lambda x, y: x + (0 if y.is_in_progress else y.karbonite),
            self.projects.values(),
            0
        )

    def update(self) -> None:
        print('--- Production manager update')
        print(f'Karbonite: {self.gc.karbonite()}')
        print(f'Available karbonite: {self.available_karbonite()}')
        print(f'Projects: {self.projects}')

        self.update_projects()
        self.update_units()
        self.manage_production()
        self.update_karbonite()

    def update_projects(self) -> None:
        for f in self.factories + self.rockets:
            loc = HashableMapLocation(f.location.map_location())
            if f.structure_is_built() and loc in self.projects:
                print(f'Project complete at {f.location.map_location()}')
                self.projects.pop(loc)
        for p in self.projects.values():
            p.workers_assigned = 0

    def update_karbonite(self):
        for i in range(len(self.karbonite_locations)):
            for j in range(len(self.karbonite_locations[i])):
                current_location = bc.MapLocation(bc.Planet.Earth, i, j)
                try:
                    current_carbonite = self.gc.karbonite_at(current_location)
                    self.karbonite_locations[i][j] = current_carbonite
                except Exception as e:
                    assert True

    def update_units(self) -> None:
        self.idle_workers = []
        self.factories = []
        for unit in self.gc.my_units():
            if unit.unit_type == bc.UnitType.Factory:
                self.factories.append(unit)
            elif unit.unit_type == bc.UnitType.Worker and unit.location.is_on_map():
                self.idle_workers.append(unit)
            elif unit.unit_type == bc.UnitType.Rocket:
                self.rockets.append(unit)
            elif unit.unit_type in self.fighter_types:
                self.figters.append(unit)
        # print(f'Total workers: {len(self.idle_workers)}')
        # print(f'Total factories: {len(self.factories)}')

    def manage_production(self) -> None:
        self.produce_units()
        self.build_projects()
        self.manage_workers()

    def produce_units(self) -> None:
        if self.should_build_rocket():
            return
        worker_factories_count = len(self.factories) / 3  # type: float
        i = 0  # type: int
        for f in self.factories:
            if i < worker_factories_count and len(self.idle_workers) < 8:
                if self.gc.can_produce_robot(f.id, bc.UnitType.Worker):
                    self.gc.produce_robot(f.id, bc.UnitType.Worker)
            elif self.gc.can_produce_robot(f.id, bc.UnitType.Ranger):
                print('Producing a Ranger')
                self.gc.produce_robot(f.id, bc.UnitType.Ranger)
            garrison = f.structure_garrison()
            if len(garrison) > 0:
                d = random.choice(directions)
                if self.gc.can_unload(f.id, d):
                    print('Unloaded a Ranger!')
                    self.gc.unload(f.id, d)

    def build_projects(self) -> None:
        while self.should_build_rocket():
            if not self.available_karbonite() >= bc.UnitType.Rocket.blueprint_cost():
                break
            if not self.create_build_project(bc.UnitType.Rocket):
                break

        while not self.should_build_rocket() and self.should_build_factory():
            if not self.available_karbonite() >= bc.UnitType.Factory.blueprint_cost():
                break
            if not self.create_build_project(bc.UnitType.Factory):
                break

    def create_build_project(self, building_type: bc.UnitType) -> bool:
        print('Creating factory build project')
        next_loc = self.get_next_build_loc()
        if next_loc is not None:
            self.projects[HashableMapLocation(next_loc)] = Project(
                building_type.blueprint_cost(),
                False,
                0,
                building_type
            )
            return True
        else:
            print('No available spcae for build found')
            return False

    def manage_workers(self) -> None:
        if len(self.idle_workers) == 0:
            print('No workers found')
            return

        # Assign a worker to each project
        print('Managing workers')
        self.build_incomplete_projects()

        self.assign_builders()
        self.assign_miners()
        # Assign remaining idle workers
        self.assign_idle_workers()

    def build_incomplete_projects(self) -> None:
        if len(self.idle_workers) == 0:
            return

        for p_loc, project in {k: v for k, v in self.projects.items() if not v.is_in_progress}.items():
            worker = min(
                self.idle_workers,
                key=lambda w: w.location.map_location().distance_squared_to(p_loc.map_location)
            )
            # print(f'Closest worker to project {p_loc.map_location} is {worker.location.map_location()}')
            self.idle_workers.remove(worker)
            # Send this worker to build
            worker_loc = worker.location.map_location()
            if not worker_loc.is_adjacent_to(p_loc.map_location):
                # Worker is too far, move it closer
                self.move_close_to(worker, p_loc.map_location)

            if worker_loc.is_adjacent_to(p_loc.map_location):
                # print('Worker is close enough')
                # Worker is close enough and can build
                d = worker_loc.direction_to(p_loc.map_location)
                if (self.gc.karbonite() > project.building_type.blueprint_cost()
                        and self.gc.can_blueprint(worker.id, project.building_type, d)):
                    self.gc.blueprint(worker.id, project.building_type, d)
                    self.projects[p_loc].is_in_progress = True
                    self.projects[p_loc].workers_assigned += 1

    def assign_idle_workers(self) -> None:
        pass

    def assign_builders(self):
        # print(f'--- Assign builders')
        for k, p in self.projects.items():
            while p.is_in_progress and p.workers_assigned < 4 and len(self.idle_workers) > 0:
                # print(f'--- Workers assigned = {p.workers_assigned}, idle: {len(self.idle_workers)}')
                worker = min(
                    self.idle_workers,
                    key=lambda w: w.location.map_location().distance_squared_to(k.map_location)
                )
                p.workers_assigned += 1
                self.idle_workers.remove(worker)
                if not worker.location.map_location().is_adjacent_to(k.map_location):
                    # Worker is too far, move it closer
                    self.move_close_to(worker, k.map_location)
                if worker.location.map_location().is_adjacent_to(k.map_location):
                    # Worker is close enough and can build
                    self.try_to_build_at(worker, k.map_location)

    def assign_miners(self) -> None:
        for miner in self.idle_workers:
            miner_location = miner.location.map_location()
            closest_karbonite_location = self.find_closest_karbonite(miner_location)
            if miner_location == closest_karbonite_location:
                # print(f'Worker {miner.id} is already at karbonite location -> {miner_location} ')
                self.harvest(miner, closest_karbonite_location)
            else:
                # print(f'navigate to {closest_karbonite_location}')
                reached_carbonite = navigate_unit_to(self.gc, miner, closest_karbonite_location)
                if reached_carbonite:
                    self.harvest(miner, closest_karbonite_location)
                else:
                    pass
                    # print(
                    #     f'Worker {miner.id} at {miner_location} '
                    #     f'navigating to carbonite at {closest_karbonite_location}'
                    # )

    def try_to_build_at(self, worker: bc.Unit, p_loc: bc.MapLocation) -> None:
        units = self.gc.sense_nearby_units(p_loc, 1)
        for building in units:
            if self.gc.can_build(worker.id, building.id):
                # print(f'Working on a blueprint {building}')
                self.gc.build(worker.id, building.id)
                break

    def move_close_to(self, worker: bc.Unit, p_loc: bc.MapLocation) -> None:
        worker_loc = worker.location.map_location()
        loc_near = find_empty_loc_near(self.gc, self.gc.starting_map(bc.Planet.Earth), p_loc)
        if loc_near is not None:
            # print(f'Try to move worker from {worker.location.map_location()} to {loc_near}')
            path_to_loc = a_star_search(
                self.gc,
                self.gc.starting_map(bc.Planet.Earth),
                worker_loc,
                loc_near
            )
            if path_to_loc is not None:
                path_to_loc = list(path_to_loc)
            else:
                print(f'Path not found {worker.location.map_location()} to {loc_near}')
            if path_to_loc is not None and len(path_to_loc) > 1:
                # print(f'Path found {path_to_loc}')
                next_node = path_to_loc[1]
                next_dir = worker_loc.direction_to(bc.MapLocation(self.gc.planet(), next_node[0], next_node[1]))
                if self.gc.can_move(worker.id, next_dir) and self.gc.is_move_ready(worker.id):
                    # print('Worker move')
                    self.gc.move_robot(worker.id, next_dir)

    def get_next_build_loc(self) -> bc.MapLocation:
        # No factories yet, find a neraby place
        if len(self.factories) == 0:
            for w in self.idle_workers:
                for d in bc.Direction:
                    new_loc = w.location.map_location().add(d)
                    if is_empty(self.gc, self.gc.starting_map(bc.Planet.Earth), new_loc):
                        return new_loc
        # Find a place close to other factories
        else:
            for f in self.factories:
                for d in cross_directions:
                    new_loc = f.location.map_location().add(d)
                    if is_empty(self.gc, self.gc.starting_map(bc.Planet.Earth), new_loc):
                        return new_loc
        return None

    def should_build_factory(self) -> bool:
        return len(self.projects) == 0

    def should_build_rocket(self) -> bool:
        return (len(self.projects) == 0
                and len(self.rockets) == 0
                and len(self.idle_workers) > 5
                and len(self.figters) > 5)

    def harvest(self, worker, karbonite_location):  # type: (bc.Unit, bc.MapLocation) -> None
        worker_location = worker.location.map_location()
        direction = worker_location.direction_to(karbonite_location)
        if self.gc.can_harvest(worker.id, direction):
            self.gc.harvest(worker.id, direction)
            print(f'Worker {worker.id} at {worker_location} HARVESTING at {karbonite_location}')
        else:
            print(f'Worker {worker.id} at {worker_location} CANNOT harvest at {karbonite_location}')

    def find_closest_karbonite(self, location):  # type: (bc.MapLocation) -> bc.MapLocation
        closest_location = location  # type: bc.MapLocation
        closest_distance = sys.maxsize

        for i in range(len(self.karbonite_locations)):
            for j in range(len(self.karbonite_locations[i])):
                karbonite_location = bc.MapLocation(location.planet, i, j)
                potential_distance = karbonite_location.distance_squared_to(location)
                if self.karbonite_locations[i][j] > 0 and potential_distance < closest_distance:
                    closest_distance = potential_distance
                    closest_location = karbonite_location

        return closest_location

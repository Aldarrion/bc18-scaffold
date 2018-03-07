from collections import namedtuple
import battlecode as bc
from LocationUtil import is_empty, cross_directions, find_empty_loc_near
from HashableMapLocation import HashableMapLocation
from functools import reduce
from Pathfinder import a_star_search
from typing import List, Dict, NamedTuple


Project = NamedTuple('Project', [('karbonite', int), ('is_in_progress', bool)])


class ProductionManager:
    def __init__(self, gc: bc.GameController) -> None:
        self.gc = gc  # type: bc.GameController
        self.factories = []  # type: List[bc.Unit]
        self.idle_workers = []  # type: List[bc.Unit]
        self.projects = dict()  # type: Dict[HashableMapLocation, Project]

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

    def update_projects(self) -> None:
        for f in self.factories:
            loc = HashableMapLocation(f.location.map_location())
            if f.structure_is_built() and loc in self.projects:
                print(f'Project complete at {f.location.map_location()}')
                self.projects.pop(loc)

    def update_units(self) -> None:
        self.idle_workers = []
        self.factories = []
        for unit in self.gc.my_units():
            if unit.unit_type == bc.UnitType.Factory:
                self.factories.append(unit)
            elif unit.unit_type == bc.UnitType.Worker and unit.location.is_on_map():
                self.idle_workers.append(unit)

    def manage_production(self) -> None:
        self.produce_units()
        self.build_projects()
        self.manage_workers()

    def produce_units(self) -> None:
        for f in self.factories:
            if self.gc.can_produce_robot(f.id, bc.UnitType.Ranger):
                print('Producing a Ranger')
                self.gc.produce_robot(f.id, bc.UnitType.Ranger)

    def build_projects(self) -> None:
        while self.should_build_factory():
            print('Creating factory build project')
            next_loc = self.get_next_build_loc()
            if next_loc is not None:
                self.projects[HashableMapLocation(next_loc)] = Project(
                    bc.UnitType.Factory.blueprint_cost(),
                    False
                )
            else:
                print('No available spcae for build found')
                break

    def manage_workers(self) -> None:
        if len(self.idle_workers) == 0:
            print('No workers found')
            return

        # Assign a worker to each project
        print('Managing workers')
        self.build_incomplete_projects()

        # Assign remaining idle workers
        self.assign_idle_workers()

    def build_incomplete_projects(self) -> None:
        for p_loc, project in {k: v for k, v in self.projects.items() if not v.is_in_progress}.items():
            worker = min(
                self.idle_workers,
                key=lambda w: w.location.map_location().distance_squared_to(p_loc.map_location)
            )
            # print(f'Closest worker to project {p_loc.map_location} is {worker.location.map_location()}')
            self.idle_workers.remove(worker)
            # Send this worker to build
            worker_loc = worker.location.map_location()
            if worker_loc.is_adjacent_to(p_loc.map_location):
                # print('Worker is close enough')
                # Worker is close enough and can build
                d = worker_loc.direction_to(p_loc.map_location)
                if (self.gc.karbonite() > bc.UnitType.Factory.blueprint_cost()
                        and self.gc.can_blueprint(worker.id, bc.UnitType.Factory, d)):
                    self.gc.blueprint(worker.id, bc.UnitType.Factory, d)
                    self.projects[p_loc] = Project(project.karbonite, True)
            else:
                # Worker is too far, move it closer
                self.move_close_to(worker, p_loc.map_location)

    def assign_idle_workers(self) -> None:
        for worker in self.idle_workers:
            projects_in_progress = [k for k, v in self.projects.items() if v.is_in_progress]
            if len(projects_in_progress) > 0:
                closest_project = min(
                    projects_in_progress,
                    key=lambda p: p.map_location.distance_squared_to(worker.location.map_location())
                )

                if worker.location.map_location().is_adjacent_to(closest_project.map_location):
                    # Worker is close enough and can build
                    self.try_to_build_at(worker, closest_project.map_location)
                else:
                    # Worker is too far, move it closer
                    self.move_close_to(worker, closest_project.map_location)

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
        return len(self.projects) == 0 and self.available_karbonite() >= bc.UnitType.Factory.blueprint_cost()

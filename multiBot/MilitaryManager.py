from collections import namedtuple
import battlecode as bc
from LocationUtil import is_empty, cross_directions, find_empty_loc_near
from enum import Enum
import random
from UnitController import navigate_unit_to
import sys
import time

from builtins import print

Action = namedtuple('Action', ['id', 'action_type', "location", "round", "group_id"])
Group = namedtuple('Group', ['id', 'soldiers', 'action'])
Part_group = namedtuple('Part_group', ['id', 'rangers', 'rangers_count', 'healers', 'healers_count',
                                       'mages', 'mages_count', 'knights', 'knights_count'])

directions = list(bc.Direction)


class ActionType(Enum):
    ATTACK = 1
    DEFENSE = 2
    MOVE = 3
    MARS_HOLLIDAY = 4


class Demands(Enum):
    EXPLORER = 1


class MilitaryManager:
    def __init__(self, gc: bc.GameController, pm: bc.PlanetMap):
        self.gc = gc
        self.pm = pm
        self.planned_actions = []
        self.soldiers_in_action = dict()
        self.group_ids = 0
        self.action_ids = 0
        self.groups = dict()
        self.next_actions = dict()
        self.free_groups = []
        if gc.team() == bc.Team.Blue:
            self.enemy_team = bc.Team.Red
        else:
            self.enemy_team = bc.Team.Blue
        self.enemy_factories = []
        self.enemy_workers = []
        self.enemy_rockets = []
        self.enemy_soldiers = []
        self.soldiers_group = dict()
        self.explorers = []
        self.explorerQueue = []
        self.rockets_in_processing = []
        self.loaded_rockets = []

    def move_soldiers_inside_group(self, group):
        ret_count = 0
        for type in group.soldiers:
            for soldier_id in group.soldiers[type]:
                if self.move_soldier(soldier_id):
                    ret_count += 1
        if ret_count > 0:
            return True
        return False

    def move_soldier(self, soldier_id):
        if soldier_id in self.soldiers_in_action:
            unit = self.gc.unit(soldier_id)
            if self.soldiers_in_action[soldier_id] is not None and \
                            unit.location.map_location().distance_squared_to(
                                self.soldiers_in_action[soldier_id]) > unit.attack_range():
                start = time.time()
                if navigate_unit_to(self.gc, unit, self.soldiers_in_action[soldier_id]):
                    self.soldiers_in_action.pop(soldier_id, None)
                    end = time.time()
                    return False
                else:
                    end = time.time()
                    return True
            else:
                self.soldiers_in_action.pop(soldier_id, None)
        return False

    def service_groups(self):
        for group_id in self.groups:
            group = self.groups[group_id]
            if group_id not in self.free_groups:
                if not self.move_soldiers_inside_group(group):
                    if group_id in self.next_actions:
                        action = self.next_actions.pop(group_id, None)
                        self.new_action(action.action_type, action.location, action.round, action.group_id)
                    else:
                        self.free_groups.append(group_id)
            else:
                for type in group.soldiers:
                    for soldier_id in group.soldiers[type]:
                        try:
                            if not self.fight_with_soldier(soldier_id):
                                self.go_somewhere(soldier_id)
                        except Exception as exc:
                            print(exc)

    def fight_with_soldier(self, soldier_id):
        soldier = self.gc.unit(soldier_id)
        for unit in self.gc.sense_nearby_units_by_team(soldier.location.map_location(), soldier.attack_range(),
                                                       self.enemy_team):
            if self.gc.is_attack_ready(soldier_id) and unit.team != self.gc.team() and \
                    self.gc.can_attack(soldier_id, unit.id):
                self.gc.attack(soldier_id, unit.id)
                return True
        return False

    def get_new_group(self):
        self.group_ids += 1
        n_group = Group(self.group_ids, {'ranger': [], 'healer': [], 'mage': [], 'knight': []}, None)
        return n_group

    # checks robots, creates new group and add it to free groups
    def distribute_soldiers(self):
        group = None
        for unit in self.gc.my_units():
            if unit.location.is_in_garrison():
                continue
            if self.is_soldier(unit.unit_type):
                if unit.id not in self.soldiers_group:
                    if len(self.explorerQueue) > 0 and self.get_unit_type(
                            unit) == "ranger" and unit.id not in self.explorers:
                        self.explorers.append(unit.id)
                        self.explorerQueue.pop()
                        continue
                    if group is None:
                        group = self.get_new_group()
                    group.soldiers[self.get_unit_type(unit)].append(unit.id)
                    self.soldiers_group[unit.id] = group
        if group is not None:
            self.groups[group.id] = group
            self.free_groups.append(group.id)

    # unit_type for list
    def get_unit_type(self, unit):
        if unit.unit_type == bc.UnitType.Rocket:
            return 'rocket'
        elif unit.unit_type == bc.UnitType.Factory:
            return 'factory'
        elif unit.unit_type == bc.UnitType.Worker:
            return 'worker'
        elif unit.unit_type == bc.UnitType.Knight:
            return 'knight'
        elif unit.unit_type == bc.UnitType.Mage:
            return 'mage'
        elif unit.unit_type == bc.UnitType.Healer:
            return 'healer'
        elif unit.unit_type == bc.UnitType.Ranger:
            return 'ranger'
        else:
            return 'None'

    def is_soldier(self, unit_type):
        if unit_type == bc.UnitType.Knight or unit_type == bc.UnitType.Ranger or \
                        unit_type == bc.UnitType.Mage or unit_type == bc.UnitType.Healer or \
                        unit_type == "Knight" or unit_type == "Ranger" or \
                        unit_type == "Mage" or unit_type == "Healer":
            return True
        else:
            return False

    def is_healer(self, unit_type):
        if unit_type == bc.UnitType.Healer or unit_type == "Healer":
            return True
        else:
            return False

    # adds new action to planned actions
    def new_action(self, action_type, location, round, group_id=None):
        self.planned_actions.append(Action(self.get_action_id(), action_type, location, round, group_id))

    def get_action_id(self):
        self.action_ids += 1
        return self.action_ids

    def attack_action(self, action, group):
        nearby = self.gc.sense_nearby_units(action.location, 4)
        enemy_count = 0
        for type in group.soldiers:
            if not self.is_healer(type):
                for soldier_id in group.soldiers[type]:
                    attacked = False
                    if soldier_id not in self.soldiers_in_action:
                        for other in nearby:
                            if other.team != self.gc.team():
                                enemy_count += 1
                                if self.gc.is_attack_ready(soldier_id) and \
                                        self.gc.can_attack(soldier_id, other.id):
                                    self.gc.attack(soldier_id, other.id)
                                    attacked = True
                                    continue
                    if not attacked:
                        pass
            else:
                for soldier_id in group.soldiers[type]:
                    healed = False
                    if soldier_id not in self.soldiers_in_action:
                        for other in nearby:
                            if self.gc.is_heal_ready(soldier_id) \
                                    and other.team == self.gc.team() and \
                                    self.gc.can_heal(soldier_id, other.id):
                                self.gc.heal(soldier_id, other.id)
                                healed = True
                                continue
                    if not healed:
                        pass
        if enemy_count == 0:
            self.planned_actions.remove(action)
            self.free_groups.append(group.id)

    def holliday_action(self, action):
        nearby = self.gc.sense_nearby_units_by_team(action.location, 3, self.gc.team())
        rocket = None
        for other in nearby:
            if other.unit_type == bc.UnitType.Rocket and other.location.map_location() == action.location:
                rocket = other
        if rocket is not None:
            loaded_soldiers = 0
            for near in nearby:
                if (self.is_soldier(
                        near.unit_type) or near.unit_type == bc.UnitType.Worker) and near.id not in self.soldiers_in_action:
                    if self.gc.can_load(rocket.id, near.id):
                        self.gc.load(rocket.id, near.id)
                        if not near.unit_type == bc.UnitType.Worker:
                            try:
                                self.soldiers_group[near.id].soldiers[self.get_unit_type(self.gc.unit(near.id))].remove(
                                    near.id)
                            except Exception as exc:
                                print(exc)
                        self.soldiers_group.pop(near.id, None)
                        loaded_soldiers += 1
            garrison = rocket.structure_garrison()
            if len(garrison) >= 2:
                try:
                    self.planned_actions.remove(action)
                except:
                    print("Action already removed")
                # self.loaded_rockets(rocket.id) # TODO this will crash - list is not callable, should be remove?
                self.rockets_in_processing.remove(rocket.id)
                self.launch_rocket(rocket.id)
        else:
            self.planned_actions.remove(action)

    def execute_actions(self):
        for action in self.planned_actions:
            if action.action_type == ActionType.MARS_HOLLIDAY:
                self.holliday_action(action)
                continue
            group = None
            if action.group_id is not None:
                group = self.groups[action.group_id]
            else:
                if len(self.free_groups) > 0:
                    group = self.groups[self.free_groups.pop()]
            if group is None:
                continue
            if action.action_type == ActionType.MOVE:
                for type in group.soldiers:
                    for soldier_id in group.soldiers[type]:
                        self.soldiers_in_action[soldier_id] = action.location
                self.planned_actions.remove(action)
                if action.round == -1:
                    self.next_actions[group.id] = Action(self.get_action_id(), ActionType.ATTACK, action.location, 0,
                                                         group.id)
                if action.round == -2:
                    self.next_actions[group.id] = Action(self.get_action_id(), ActionType.MARS_HOLLIDAY,
                                                         action.location, 0,
                                                         group.id)
            if action.action_type == ActionType.ATTACK:
                self.attack_action(action, group)

    # exploration
    def exploration(self, ranger_id):
        try:
            ranger = self.gc.unit(ranger_id)
            if ranger_id not in self.soldiers_in_action:
                self.go_somewhere(ranger_id, False)
            if navigate_unit_to(self.gc, ranger, self.soldiers_in_action[ranger_id]):
                self.soldiers_in_action.pop(ranger_id, None)
            for unit in self.gc.sense_nearby_units_by_team(ranger.location.map_location(), ranger.attack_range(),
                                                           self.enemy_team):
                if unit.unit_type == bc.UnitType.Rocket:
                    if unit.location.map_location() not in self.enemy_rockets:
                        self.enemy_rockets.append(unit.location.map_location())
                elif unit.unit_type == bc.UnitType.Factory:
                    if unit.location.map_location() not in self.enemy_factories:
                        self.enemy_factories.append(unit.location.map_location())
                elif unit.unit_type == bc.UnitType.Worker:
                    if unit.location.map_location() not in self.enemy_workers:
                        self.enemy_workers.append(unit.location.map_location())
                else:
                    self.enemy_soldiers.append(unit.location.map_location())
        except Exception as exc:
            print(exc)
            return None

    def explore(self):
        demands_count = 0
        for ranger_id in self.explorers:
            try:
                ranger = self.gc.unit(ranger_id)
                self.exploration(ranger_id)
            except Exception as exc:
                print(exc)
                self.explorers.remove(ranger_id)
                self.explorerQueue.append(Demands.EXPLORER)
                demands_count += 1

        if demands_count + len(self.explorers) + len(self.explorerQueue) < 4:
            for i in range(0, 4 - demands_count + len(self.explorers)):
                self.explorerQueue.append(Demands.EXPLORER)

    def go_somewhere(self, unit_id, exploration=False):
        try:
            unit = self.gc.unit(unit_id)
            if exploration:
                self.soldiers_in_action[unit_id] = self.get_random_position(self.gc.planet(), None, None)
            else:
                d = random.choice(directions)
                if self.gc.is_move_ready(unit.id) and self.gc.can_move(unit.id, d):
                    self.gc.move_robot(unit.id, d)
                    return True
            return False
        except Exception as exc:
            print(exc)
            return False

    def make_plans(self):
        while len(self.enemy_rockets) > 0:
            self.new_action(ActionType.MOVE, self.enemy_rockets.pop(), -1)
        while len(self.enemy_factories) > 0:
            self.new_action(ActionType.MOVE, self.enemy_factories.pop(), -1)
        while len(self.enemy_workers) > 0:
            self.new_action(ActionType.MOVE, self.enemy_workers.pop(), -1)

    def check_rockets(self):
        for unit in self.gc.my_units():
            if unit.unit_type == bc.UnitType.Rocket and unit.id not in self.rockets_in_processing and unit.id not in self.loaded_rockets:
                if unit.rocket_is_used():
                    garrison = unit.structure_garrison()
                    max_unloads = 8
                    act_unloads = 0
                    while len(garrison) > 0:
                        if act_unloads > max_unloads:
                            break
                        act_unloads += 1
                        d = random.choice(directions)
                        if self.gc.can_unload(unit.id, d):
                            self.gc.unload(unit.id, d)
                else:
                    self.rockets_in_processing.append(unit.id)
                    self.new_action(ActionType.MARS_HOLLIDAY, unit.location.map_location(), -2)

    def launch_rocket(self, rocket_id):
        self.gc.launch_rocket(rocket_id, self.get_next_rocket_destination())

    def get_next_rocket_destination(self) -> bc.MapLocation:
        mars_map = self.gc.starting_map(bc.Planet.Mars)  # type: bc.PlanetMap
        while True:
            x = random.randint(0, mars_map.width - 1)
            y = random.randint(0, mars_map.height - 1)
            map_loc = bc.MapLocation(bc.Planet.Mars, x, y)
            if mars_map.is_passable_terrain_at(map_loc):
                return map_loc

    def get_random_position(self, planet, location=None, radius=None) -> bc.MapLocation:
        map = self.gc.starting_map(planet)  # type: bc.PlanetMap
        min_x, min_y, max_x, max_y = self.get_random_parameters(location, radius, map)
        if radius is not None:
            max_tries = radius * 2
        else:
            max_tries = 20
        act_tries = 0
        while True:
            if max_tries < act_tries:
                min_x, min_y, max_x, max_y = self.get_random_parameters(None, None, map)
            x = random.randint(min_x, max_x)
            y = random.randint(min_y, max_y)
            map_loc = bc.MapLocation(planet, x, y)
            act_tries += 1
            if map.is_passable_terrain_at(map_loc):
                return map_loc

    def get_random_parameters(self, location, radius, map):
        if location is not None and radius is not None:
            if location.x + radius > map.width - 1:
                max_x = map.width - 1
            else:
                max_x = location.x + radius
            if location.y + radius > map.height - 1:
                max_y = map.height - 1
            else:
                max_y = location.y + radius
            if location.x - radius < 0:
                min_x = 0
            else:
                min_x = location.x - radius
            if location.y - radius < 0:
                min_y = 0
            else:
                min_y = location.y - radius
        else:
            min_y = 0
            min_x = 0
            max_x = map.width - 1
            max_y = map.height - 1
        return min_x, min_y, max_x, max_y

    def attack_when_possible(self):
        for unit in self.gc.my_units():
            if (not self.gc.is_attack_ready(unit.id)
                or not unit.location.is_on_map()):
                continue
            nearby = self.gc.sense_nearby_units_by_team(
                unit.location.map_location(),
                unit.attack_range(),
                self.enemy_team
            )
            for n in nearby:
                if self.gc.can_attack(unit.id, n.id):
                    self.gc.attack(unit.id, n.id)
                    break

    def remove_dead_soldiers(self):
        my_unit_ids = [u.id for u in self.gc.my_units()]
        for k, g in self.groups.items():
            self.groups[k] = Group(g.id, {t: [x for x in v if x in my_unit_ids] for t, v in g.soldiers.items()},
                                   g.action)

    def update(self):
        self.remove_dead_soldiers()
        self.check_rockets()
        self.explore()
        self.distribute_soldiers()
        self.make_plans()
        self.execute_actions()
        self.service_groups()
        self.attack_when_possible()

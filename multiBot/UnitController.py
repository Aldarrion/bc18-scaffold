import battlecode as bc

from LocationUtil import find_empty_loc_near
from Pathfinder import a_star_search
from enum import Enum

def navigate_unit_to(gc, unit, target_location):
    print (f'navigating to {target_location}')
    unit_location = unit.location.map_location()
    if unit_location.is_adjacent_to(target_location):
        print('Unit is adjacent to target location.')
        return True;
    else:
        # Worker is too far, move it closer
        print('Unit is too far, move it closer')
        loc_near = find_empty_loc_near(gc, gc.starting_map(bc.Planet.Earth), target_location)
        if loc_near is not None:
            print(f'Try to move unit from {unit.location.map_location()} to {loc_near}')
            a_star_result = a_star_search(
                gc,
                gc.starting_map(bc.Planet.Earth),
                unit_location,
                target_location
            )
            if (a_star_result is None):
                path_to_loc = None
            else:
                path_to_loc = list(a_star_result)
            if path_to_loc is not None and len(path_to_loc) > 1:
                print(f'Path found {path_to_loc}')
                next_node = path_to_loc[1]
                next_dir = unit_location.direction_to(bc.MapLocation(gc.planet(), next_node[0], next_node[1]))
                if gc.can_move(unit.id, next_dir) and gc.is_move_ready(unit.id):
                    print('Unit move')
                    gc.move_robot(unit.id, next_dir)
        return False
"""Explicit implementation factors for the selected v28 design only."""
from redirect_implementation_profiles import PROFILES as LEGACY

PROFILES={name:list(LEGACY[name]) for name in ('default','refine40','routing99')}
PROFILES['route_iterate3']=['-enable_route_constraint_iterate',
    '-route_constraint_iterate_times','3','-route_constraint_slack','0',
    '-route_constraint_max_timing_path','3']
PROFILES['packing3']=['-logic_optimize_enable','TRUE',
    '-logic_optimize_lut6d_combing_strategy','3']
PROFILES['module_planning']=['-planning_before_place','TRUE']
PROFILES['compact0']=['-plc_decongestion','0']
PROFILES['packing3_compact0']=PROFILES['packing3']+PROFILES['compact0']
PROFILES['packing3_nodup']=PROFILES['packing3']+['-dc_duplication','FALSE']
PROFILES['compact0_routing99']=PROFILES['compact0']+PROFILES['routing99']
PROFILES['compact0_route_iterate3']=PROFILES['compact0']+PROFILES['route_iterate3']


def command(profile,seed):
    if profile not in PROFILES or seed not in (1,2,3): raise ValueError('Unsupported selected profile/seed')
    return 'pnr -gplace_seed '+str(seed)+((' '+' '.join(PROFILES[profile])) if PROFILES[profile] else '')

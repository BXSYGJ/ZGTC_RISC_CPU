"""Predeclared, separately measured PNR options; never alter target constraints."""
PROFILES = {'default': [], 'routing100': ['-slack_weight', '100'],
            'refine40': ['-refineplacement_iteration', '40'],
            'routing99': ['-slack_weight', '99']}


def command(profile, seed):
    if profile not in PROFILES or seed not in (1, 2, 3):
        raise ValueError('Unsupported implementation profile/seed')
    return 'pnr -gplace_seed ' + str(seed) + ((' ' + ' '.join(PROFILES[profile])) if PROFILES[profile] else '')

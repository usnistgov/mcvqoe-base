from .IRIGB_decode import IRIGB_decode
from .soft_timecode import soft_time_decode

"""Types of timecodes and their decode function"""

timecode_types = {'IRIGB_timecode' : IRIGB_decode,'soft_timecode' : soft_time_decode}

def time_decode(tc_type, timecode_audio, fs, decode_args={}):
    """Decode a timecode of the given type."""
    
    try:
        tc_func = timecode_types[tc_type]
    except KeyError:
        raise ValueError(f'\'{tc_type}\' must be one of {list(timecode_types.keys())}')
    
    return tc_func(timecode_audio, fs, **decode_args)
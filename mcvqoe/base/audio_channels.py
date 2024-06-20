import re

def audio_channels_to_string(channels):
    '''
    Convert a channels list to string for use in csv's.
    
    This is the revers of parse_audio_channels.
    
    Parameters
    ----------
    channels : list or tuple of strings
        List of strings describing the recorded channels as returned by
        `play_record`.
    
    Returns
    -------
    string
        a string representation of the channels
    
    See Also
    --------
    mcvqoe.hardware.audio_player : Hardware implementation of play_record.
    mcvqoe.hardware.QoEsim : Simulation implementation of play_record.
    mcvqoe.base.parse_audio_channels : Inverse of this function.
    '''
    
    if isinstance(channels, str):
        raise TypeError('channels can not be a string')
    
    # channel string
    return '('+(';'.join(channels))+')'


def parse_audio_channels(csv_str):
    '''
    Parse audio channels from string.
    
    This is the revers of audio_channels_to_string.
    
    Parameters
    ----------
    csv_str : string
        String with channel info as returned by audio_channels_to_string.
    
    Returns
    -------
    tuple of strings
        A tuple of strings similar to what would have been returned by
        `play_record`.
    
    See Also
    --------
    mcvqoe.hardware.audio_player : Hardware implementation of play_record.
    mcvqoe.hardware.QoEsim : Simulation implementation of play_record.
    mcvqoe.base.audio_channels_to_string : Inverse of this function.
    '''
    
    match = re.search('\((?P<channels>[^)]+)\)', csv_str)

    if(not match):
        raise ValueError(f'Unable to parse channels {csv_str}, expected in the form "(chan1;chan2;...)"')

    return tuple(match.group('channels').split(';'))
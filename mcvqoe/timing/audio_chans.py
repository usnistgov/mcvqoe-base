from .timecode import timecode_types


def require_timecode(audio_player):
    """
    Throw error if a timecode will not be recorded.

    This function is used to make sure that a timecode will be recorded for
    a two location test.
    
    Parameters
    ----------
    audio_player: AudioPlayer or QoEsim class
        object to check recording channels on.
    
    Raises
    ------
    ValueError
        If there are no timecode channels

    See Also
    --------
    mcvqoe.mouth2ear : Two location m2e tests use timecodes.
    mcvqoe.intelligibility : Two location tests use timecodes.
    mcvqoe.accesstime : Two location tests use timecodes.

    Examples
    --------

    By default there is no timecode recorded by AudioPlayer.

    >>> import mcvqoe.hardware.AudioPlayer as AudioPlayer
    >>> ap = AudioPlayer()
    >>> ap.require_timecode()
    ValueError: Timecode channel not found in ('rx_voice',)

    If a timecode is recorded, no error is raised.
    >>> import mcvqoe.hardware.AudioPlayer as AudioPlayer
    >>> ap = AudioPlayer(rec_chans={'rx_voice':0, 'IRIGB_timecode':1})
    >>> ap.require_timecode()

    """
    
    for chan in audio_player.rec_chans:
        if 'timecode' in chan:
            #found! we are done
            break
    else:
        #not found, raise error
        chans=tuple(audio_player.rec_chans.keys())
        raise ValueError(f'Timecode channel not found in {chans}')

def timecode_chans(chans,tc_priority=tuple(timecode_types.keys())):
    """
    Return the indices of the timecode recording channels.
    
    Finds the channels that contain timecode. Sorts timecodes based on
    tc_priority.
    
    Parameters
    ----------
    chans : tuple of strings
        Recording channels to search.
    tc_priority : tuple of strings, default=('IRIGB_timecode', 'soft_timecode')
        Matching timecodes in this array get sorted first based on order in array.
    """
    
    tc=[]
    order=[]
    
    for n,chan in enumerate(chans):
        if('timecode' in chan):
            #found timecode, append to array
            tc.append(n)
            try:
                p=tc_priority.index(chan)
            except ValueError:
                #not found, lowest priority
                p=len(tc_priority)
            order.append(p)
            
    #TODO : sort by order
    return tc
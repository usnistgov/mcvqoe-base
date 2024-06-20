from mcvqoe.base import audio_float

import numpy as np

import datetime


soft_time_fmt = "TM%j-%Y_%H-%M-%S.%f"


def soft_time_decode(audio, fs):
    if len(audio.shape) != 1:
        raise ValueError("Input must be a numpy vector")
    
    # Get prefix from time format
    prefix = soft_time_fmt[: soft_time_fmt.index("%")]

    # TODO : raise error if prefix is zero length???

    # convert to integer values
    audio = np.round(audio_float(audio) * 255.0).astype(int)

    # convert sequence to numpy array
    npPre = np.array([ord(c) for c in prefix])

    # indicies for sliding window
    winIdx = np.arange(audio.size - len(prefix) + 1)[:, None] + np.arange(len(prefix))

    # find where the window matches
    tc_idx = (audio[winIdx] == npPre).all(1).nonzero()[0]
    
    #initialize empty arrays
    times = []
    samples = []

    for n,idx in enumerate(tc_idx):
        #audio index of string
        idx_str = idx
        #initialize time str
        tc_str = ''
        #loop till end of string
        while audio[idx_str] != 0:
            #get char from string
            tc_str += chr(audio[idx_str])
            #next index
            idx_str += 1
        
        time = datetime.datetime.strptime(tc_str, soft_time_fmt)
        # append time and index to array
        times.append(time)
        samples.append(idx)

    return np.array(times), np.array(samples)
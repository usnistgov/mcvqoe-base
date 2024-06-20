import csv
import scipy.io.wavfile

import numpy as np
import pandas as pd
import scipy.signal as sig


def audio_float(dat):
    """
    Convert audio data to float with standard scale.

    Data read with scipi.io.wavefile can be returned in a number of number
    formats. `audio_float` returns audio data in floating point for scaled to =/-1

    Parameters
    ----------
    dat : numpy array
        Audio data to convert to float.

    Returns
    -------
    numpy array
        Floating point audio data scaled to a range of +/-1.

    See Also
    --------
    scipi.io.wavefile : Functions for reading and writing .wav files.
    mcvqoe.audio_type : General function for converting audio to any valid type

    Examples
    --------
    load audio and ensure that it is on the -1 to +1 range

    >>> fs, dat = scipy.io.wavfile('audio.wav')
    >>> float_dat = audio_float(dat)
    """
    
    return audio_type(dat, dtype=np.dtype('float'))

def audio_type(dat, dtype=np.dtype('int16')):
    """
    Convert audio data to different data type with standard scale.

    Data read and written with scipi.io.wavefile can be in a variety of 
    different formats. `audio_type` returns audio data in different data types
    to ensure the proper format data is used for reading and writing.
    

    Parameters
    ----------
    dat : numpy array
        Audio data to convert.
    dtype : np.dtype, optional
        Output data type. The default is np.dtype('int16').

    Returns
    -------
    numpy array
        Array with audio scaled to appropriate values for new data type.
        
    See Also
    --------
    scipy.io.wavfile : Functions for reading and writing .wav files
    mcvqoe.audio_float : Convenience function for converting audio to float

    """
    
    # Return audio if it's already the right type
    if(dat.dtype == dtype):
        return(dat)
        
    #---------------------[Convert to float]------------------
    if np.issubdtype(dat.dtype, np.floating):
        dat = dat
    elif(dat.dtype is np.dtype('uint8')):
        dat = (dat.astype('float')-64)/64
    elif(dat.dtype is np.dtype('int16')):
        dat = dat.astype('float')/(2**15)
    elif(dat.dtype is np.dtype('int32')):
        dat = dat.astype('float')/(2**31)
    else:
        raise RuntimeError(f'unknown audio type \'{dat.dtype}\'')
        
    #-----------------[Convert to output]------------------------
    if np.issubdtype(dtype, np.floating):
        return(dat.astype(dtype))
    elif(dtype is np.dtype('uint8')):
        out_dat = 64*dat + 64
        return out_dat.astype('uint8')
    elif(dtype is np.dtype('int16')):
        out_dat = 2**15 * dat
        return out_dat.astype('int16')
    elif(dtype is np.dtype('int32')):
        out_dat = 2**31 * dat
        return out_dat.astype('int32')
    else:
        raise RuntimeError(f'unknown audio type \'{dat.dtype}\'')

def audio_read(filename):
    """
    Open a WAV file.

    Return the sample rate (in samples/sec) and data from a WAV file.
    Regardless of original WAV file format, data is returned as float32 numpy
    array.

    Parameters
    ----------
    fname : str
        Input WAV file.

    Returns
    -------
    sample_rate : int
        Sample rate of WAV file

    audio_data : numpy array
        Data read from WAV file. Data is 1-D for 1-channel WAV, or 2-D of
        shape (Nsamples, Nchannels) otherwise. Numpy data type is always set
        to float.

    See Also
    --------
    mcvqoe.base.audio_write

    mcvqoe.base.audio_type

    """
    
    sample_rate, audio_data = scipy.io.wavfile.read(filename)
    audio_data = audio_type(audio_data, dtype=np.dtype('float32'))
    
    return sample_rate, audio_data

def audio_write(filename, rate, data):
    """
    Write a NumPy array as a WAV file.

    Regardless of type of data, writes wavfile as 16 bit PCM.

    Parameters
    ----------
    filename : TYPE
        DESCRIPTION.
    rate : int
        The sample rate (in samples/sec).
    data : ndarray
        A 1-D or 2-D NumPy array of either integer or float data-type.

    Returns
    -------
    None.

    See Also
    --------
    mcvqoe.base.audio_read

    mcvqoe.base.audio_type

    """
    
    data = audio_type(data, dtype=np.dtype('int16'))
    scipy.io.wavfile.write(filename, rate, data)

def svp56_fast(x, fs=8000):
    """
    Digital Speech Voltmeter function for audio.

    This code implements the "Speech Voltmeter" given in CCITT Rec. P.56.
    It is a fast version of svp56.m which was written from the description in
    the hard copy doc that came with UGST STL 96.  svp56.m results have been
    verified against results of the C code from UGST.

    svp56_fast.m agrees with with svp56.m as follows.  It either agrees
    exactly (the integer counts in all 16 bits of "a" match exactly at
    inspection point A) or almost exactly (the integer counts in some of the
    16 bits of "a" are off by one at inspection point A, and the asl and saf
    differ in the 4th or 5th decimal place)
    Note that on a fixed platform svp56_fast.m requires about 8# of the
    running time that svp56.m requires

    Written by S. Voran, in mid 1990's

    Usage:  [asl, saf, active] = svp56_fast(x, fs)

    Parameters
    ----------
    x : list or str
        Speech signal or file name of a .wav file.
    fs : number, default=8000
        Sample rate of x.

    Returns
    -------
    asl : number
        Active speech level in dB (relative to 16 bits).
    saf : float
        Speech activity factor (0 to 1).
    active : tuple
        Same length as the speech signal. Contains 1's in active areas, 0's else.
        "active" is an approximation, and the average absolute error:
        mean(abs( saf - sum(active)/n )) is about 0.2# or 0.3#.

    See Also
    --------
    mcvqoe.a_weighted_power : Human ear model power level meter.

    Examples
    --------
    Measure the active speech level of a .wav file

    >>> (asl, _, _) = svp56_fast('speech.wav')
    
    """
    
    # if x is a filename, extact data from the wav file
    if isinstance(x, str):
        fs, x = scipy.io.wavfile(x)
    elif not isinstance(x, (list, np.ndarray)):
        raise ValueError("Invalid input for x")

    x = np.array(x)
    # only keep first channel in 2-channel audio
    if len(np.shape(x)) != 1:
        x = x[:, 0]

    # convert the signal to 16 bit integers in range [-32768, +32767]
    r = 2 ** 15
    # scale [-1, +1]
    if type(x[0]) == np.float32:
        x = np.asarray(x * r, dtype=np.int16)
    # scale [-2147483648, +2147483647]
    elif type(x[0]) == np.int32:
        x = np.asarray(x / r / 2, dtype=np.int16)
    # data is already in specified format
    elif type(x[0]) == np.int16:
        pass
    # scale [0, 255]
    elif type(x[0]) == np.uint8:
        offset = -((2 ** 8) - 1) / 2
        scale = (2 ** 8) + 1
        x = np.asarray((x + offset) * scale, dtype=np.int16)

    x = x - np.mean(x)  # mean removal is not in P56, but it should be

    r = 2 ** 15
    sq = np.sum(x ** 2)
    if sq == 0:
        raise ValueError("No signal")
    x = np.abs(x)  # rectify
    n = len(x)
    g = np.e ** (-1 / (fs * 0.03))

    q = sig.lfilter([(1 - g) ** 2], [1, -2 * g, g * g], x)  # smooth

    c = 2 ** np.arange(16)
    a = np.zeros(16)
    hs = round(0.2 * fs)  # 200 ms hang time

    # take log 2, with handling that gives log2(0)=-100 instead of error
    good = np.nonzero(0 < q)[0]
    lq = -100 * np.ones(len(q))
    lq[good] = np.floor(
        np.log2(q[good])
    )  # these 3 lines protect against log2(0), defining it to be log2(0)=-100
    # print(lq.tolist())
    for i in range(16):
        active = i <= lq  # compare log2 of env. with integer values 0 to 15
        trans = np.nonzero(np.abs(np.diff(active)))[0]
        for j in range(len(trans)):
            active[
                trans[j] : (min(trans[j] + hs - 1, n) + 1)
            ] = 1  # extend activity 200 ms
            # after each transition
        a[i] = np.sum(active)  # total number of log2(env) samples above a
        # threshold of i-1
    # ------------------Inspection point A-----------------------------

    L = (10 * np.log10(sq / n)) - (
        20 * np.log10(r)
    )  # average power relative to clip point (in dB)
    c = (20 * np.log10(c)) - (
        20 * np.log10(r)
    )  # binary thresholds relative to clip point (in dB)
    A = np.zeros(len(c))
    for i in range(16):
        if a[i] > 0:
            A[i] = 10 * np.log10(sq / a[i]) - 20 * np.log10(r)
        else:
            A[i] = 200
    d = A - c

    Afinal = 0
    for i in range(15):
        if d[i] >= 15.9 and d[i + 1] <= 15.9:
            if d[i] - d[i + 1] == 0:
                Afinal = A[i]
            else:
                s = (d[i] - 15.9) / (d[i] - d[i + 1])
                Afinal = (1 - s) * A[i] + (s * A[i + 1])

    saf = 10 ** ((L - Afinal) / 10)
    asl = Afinal

    # To get to a target active speech level, you can scale speech based
    # on the output of this code but you might have to iterate a bit to hit
    # an exact value.  This is because the
    # Speech Voltmeter is not exactly linear.  For example, scaling speech by
    # 2.0 does not produce exactly 20*log10(2)=6.02 dB increase in Speech
    # Voltmeter output. But it does typically produce a value in the range
    # 6.02 +/- 0.25 dB.

    # Here ends the code that emulates the ITU-T P.56 Speech Voltmeter.  Below is code to
    # create an activity mask.  It is the intuitive, reasonable extension of the above.
    # Specifically, if sum(a(i)) for some i goes to n, then we have 100# speech activity.
    # This says that the a(i)'s are the speech activities masks.  The a(i)'s are
    # calculated from floor(log2(envelope)).  The floor operation means that non-integral
    # thresholds on this "integer-log-envelope" are not meaningful.  Thus it remains
    # to simply pick the best i value and a(i) is the mask. We recaculate a(i) instead of
    # saving all 16, which could use a lot of memory for long speech files.

    dud = np.min(np.abs(d - 15.9))
    loc = np.argmin(np.abs(d - 15.9))
    active = loc <= lq
    trans = np.nonzero(np.abs(np.diff(active)))[0]
    for j in range(len(trans)):
        active[trans[j] : min(trans[j] + hs - 1, n) + 1] = 1
    return asl, saf, active

def load_cp(fname):
    """
    Read in cutpoints from file.

    Read cutpoints from the file with the given filename. Convert cutpoint
    indices from 1 based indices to zero based indices. Returns a tuple containing
    a dict for each segment of the file.

    Parameters
    ----------
    fname : str
        Name of cutpoint file to read.

    Returns
    -------
    tuple of dicts
        Tuple of dicts each with keys ['Clip', 'Start', 'End'].

    See Also
    --------
    mcvqoe.write_cp : Function to write cutpoints.

    Examples
    --------
    Example of loading cutpoints

    >>> load_cp('cp.csv')
    
    """
    
    # field names for cutpoints
    cp_fields = ["Clip", "Start", "End"]
    # open cutpoints file
    with open(fname, "rt") as csv_f:
        # create dict reader
        reader = csv.DictReader(csv_f)
        # check for correct fieldnames
        if reader.fieldnames != cp_fields:
            raise RuntimeError(f"Cutpoint columns do not match {cp_fields}")
        # create empty list
        cp = []
        # append each line
        for row in reader:
            # convert values to float
            for k in row:
                if k == "Clip":
                    # float is needed to represent NaN
                    row[k] = float(row[k])
                    # convert non nan fields to int
                    if not np.isnan(row[k]):
                        row[k] = int(row[k])
                else:
                    # make indexes zero based
                    row[k] = int(row[k]) - 1

            # append row to
            cp.append(row)
        return tuple(cp)

def write_cp(fname, cutpoints):
    """
    Write cutpoints to file.

    Write cutpoints from `cutpoints` to the file named `fname`.

    Parameters
    ----------
    fname : str
        Name of cutpoint file to read.
    cutpoints : tuple of dicts
        Tuple of dicts each with keys ['Clip', 'Start', 'End'].

    See Also
    --------
    mcvqoe.load_cp : Function to write cutpoints.

    Examples
    --------
    Example of saving cutpoints

    >>> cutpoints = ({'Clip': 24, 'Start': 0, 'End': 41970})
    >>> write_cp('cp.csv', cutpoints)
    
    """
    
    # field names for cutpoints
    cp_fields = ["Clip", "Start", "End"]
    # open cutpoints file
    with open(fname, "wt", newline="\n", encoding="utf-8") as csv_f:
        # create dict writer
        writer = csv.DictWriter(csv_f, fieldnames=cp_fields)
        # write header row
        writer.writeheader()
        # write each row
        for wcp in cutpoints:
            # convert back to 1 based index
            wcp["Start"] += 1
            wcp["End"] += 1
            # write each row
            writer.writerow(wcp)

def a_weighted_power(x, fs=48000):
    """
    Calculate A-weighted power level for audio vector.

    Calculates an A-weighted power level in dB for the input audio vector x.
    This is a good approximation to relative loudness because the A-weighting
    function emulates a fundamental attribute of human hearing.

    The filter coefficients come from dsprelated.com and the resulting
    frequency response agrees with those shown in the literature.
    Getting filter coefficients for sample rates other than 48000 proved
    difficult so this code just converts input signals to 48000 instead.
    -S. Voran, Sept. 25, 2012

    Parameters
    ----------
    x : NumPy Array
        The audio in NumPy array format.
    fs : numeric, default=48000
        Sample rate for audio. Must be one of [8000, 16000, 24000, 32000,48000].

    Returns
    -------
    float
        A-weighted power for audio vector.

    See Also
    --------
    mcvqoe.svp56_fast : Speech Voltmeter function.

    Examples
    --------
    Calculate the A-weighted power for a 48 kHz audio vector

    >>> a_weighted_power(audio)
    
    """

    # Coefficients for A-weighting filter with fs=48000
    b = np.array(
        [
            0.01147155239724,
            -0.0248548824653166,
            0.0323052801494283,
            -0.0555571372813964,
            0.233784933167266,
            0.392882400411297,
            -0.633249911806281,
            -0.479494344932334,
            0.322061493940389,
            0.197659563091056,
            0.00299879461389451,
        ]
    )

    a = np.array(
        [
            1,
            -0.925699454182466,
            -0.992471193943543,
            0.837650096562845,
            0.22307303912603,
            -0.158404327757755,
            0.0184103295763937,
        ]
    )

    # Set gain at 1kHz to 0dB
    b = b * 1.1389

    # Resample audio
    if fs == 8000:
        x = sig.resample_poly(x, 6, 1)
    elif fs == 16000:
        x = sig.resample_poly(x, 3, 1)
    elif fs == 24000:
        x = sig.resample_poly(x, 2, 1)
    elif fs == 32000:
        x = sig.resample_poly(x, 3, 2)
    elif fs != 48000:
        raise ValueError(f"Unsupported sample rate of {fs}.\n")

    x = sig.lfilter(b, a, x)
    return 10 * (np.log10(np.mean(np.square(x))))

def get_measurement_from_file(filepath, module=True):
    """
    Determine measurement type from file header.

    Parameters
    ----------
    filepath : str
        Path to file.
    module : bool, optional
        If True returns the module name instead of evaluation shortened 
        measurement string (e.g. 'mcvqoe.mouth2ear' vs 'm2e'). The default is 
        True.

    Returns
    -------
    measurement : str
        Measurement type. Returns None if it could not be determined.

    """
    
    # Initialize measurement
    measurement = None
    try:
        # Read in csv
        df = pd.read_csv(filepath)
        # Get column names
        colnames = df.columns
        
        if 'W0_Int' in colnames:
            # All psud tests have to have at least one word so W0_Int should always be there
            measurement = 'psud'
        elif 'Intelligibility' in colnames:
            # Intelligibility only in intelligibility tests
            measurement = 'intell'
        elif 'ptt_st_dly' in colnames:
            # ptt_st_dly only in access time
            measurement = 'access'
        elif 'm2e_latency' in colnames:
            # m2e_latency in many tests, but if it's here and the others didn't work it's probably m2e latency
            measurement = 'm2e'
        elif 'FSF_flag' in colnames:
            measurement = 'diagnostics'
    except pd.errors.ParserError:
        # If parsing failed, check access data, skip 3 rows
        df = pd.read_csv(filepath, skiprows=3)
        if 'P1_Int' in df.columns:
            measurement = 'access'
        else:
            # Check if TVO data
            df = pd.read_csv(filepath, skiprows=2)
            if 'FSF' in df.columns:
                measurement = 'tvo'
        
    if module and measurement is not None:
        measurement_dir_modules = {    
            'access' : 'mcvqoe.accesstime',
            'intell' : 'mcvqoe.intelligibility',
            'm2e' : 'mcvqoe.mouth2ear',
            'psud' : 'mcvqoe.psud',
            'tvo': 'mcvqoe.tvo',
            'diagnostics': 'mcvqoe.diagnostics'
        }
        measurement = measurement_dir_modules[measurement]
        
    return measurement
import datetime

import numpy as np

from scipy.cluster.vq import kmeans2
from warnings import warn


# This software was developed by employees of the National Institute of
# Standards and Technology (NIST), an agency of the Federal Government.
# Pursuant to title 17 United States Code Section 105, works of NIST
# employees are not subject to copyright protection in the United States and
# are considered to be in the public domain. Permission to freely use, copy,
# modify, and distribute this software and its documentation without fee is
# hereby granted, provided that this notice and disclaimer of warranty
# appears in all copies.

# THE SOFTWARE IS PROVIDED 'AS IS' WITHOUT ANY WARRANTY OF ANY KIND, EITHER
# EXPRESSED, IMPLIED, OR STATUTORY, INCLUDING, BUT NOT LIMITED TO, ANY
# WARRANTY THAT THE SOFTWARE WILL CONFORM TO SPECIFICATIONS, ANY IMPLIED
# WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND
# FREEDOM FROM INFRINGEMENT, AND ANY WARRANTY THAT THE DOCUMENTATION WILL
# CONFORM TO THE SOFTWARE, OR ANY WARRANTY THAT THE SOFTWARE WILL BE ERROR
# FREE. IN NO EVENT SHALL NIST BE LIABLE FOR ANY DAMAGES, INCLUDING, BUT NOT
# LIMITED TO, DIRECT, INDIRECT, SPECIAL OR CONSEQUENTIAL DAMAGES, ARISING
# OUT OF, RESULTING FROM, OR IN ANY WAY CONNECTED WITH THIS SOFTWARE,
# WHETHER OR NOT BASED UPON WARRANTY, CONTRACT, TORT, OR OTHERWISE, WHETHER
# OR NOT INJURY WAS SUSTAINED BY PERSONS OR PROPERTY OR OTHERWISE, AND
# WHETHER OR NOT LOSS WAS SUSTAINED FROM, OR AROSE OUT OF THE RESULTS OF, OR
# USE OF, THE SOFTWARE OR SERVICES PROVIDED HEREUNDER.


def IRIGB_decode(tca, fs, tc_tol=0.05):
    """
    decodes an IRIG-B timecode
    
    Parameters
    ----------
    tca : numpy array
        timecode audio data
    fs : int
        the audio sample rate for tca.
    tc_tol: float, default=0.05
        Time code tolerance. This changes the thresholds for what bit periods
        are considered a one, zero and frame marker.
    
    Returns
    -------
    dates : tuple of datetime
        Tuple of decode times.
    fsamp : list of ints
        Sample numbers that decoded times came from.
    """
    
    #make sure that time code input is a numpy array
    tca = np.array(tca, dtype="float64")

    #tc_tol must be in [0, 0.5]
    if not (isinstance(tc_tol, (int, float)) and tc_tol >= 0 and tc_tol <= 0.5):
        raise ValueError(f'tc_tol must be > 0 and < 0.5. Got tc_tol = {tc_tol}')

    #calculate the upper envelope
    env = envelope(tca, 40)

    #use kmeans to threshold the envelope into 2 clusters
    #use 0 and max as the starting centroids
     # init = (0, 1) # gsh3, reconfigured initial centeroids
    init = (min(env), max(env)) # gsh3  reconfigured initial centeroids

    #take the cluster indices, raise an error if we don't have 2 centroids
    _, env_th = kmeans2(env, init, missing='raise')

    #find edges assume that signal starts high so that we see the first real
    edges = np.append([0], 1+np.nonzero(np.diff(env_th))[0])
    #edges = 1 + np.where(edges!=0)[0]

    #rising edges
    r_edg = edges[env_th[edges] == 1] - 1

    #falling edges
    f_edg = np.append([1], edges[env_th[edges] == 0][1:]) - 1

    #get the first and last rising edge
    startRise = r_edg[0]
    endRise = r_edg[-1]

    #remove falling edges that happen before the first rising edge and after
    #the last
    f_edg = f_edg[np.logical_and(f_edg > startRise, f_edg < endRise)]

    #calculate period
    T = np.diff(r_edg) / fs

    #calculate the pulse width
    #there is one more rising edge than falling edge so ignore last rising edge
    pw = (f_edg - r_edg[:-1]) / fs

    bits = pw_to_bits(pw, 10e-3, tc_tol)
    Tbit = 10e-3

    #find invalid periods
    invalid = np.logical_or((T < Tbit * (1-tc_tol)), (T > Tbit *(1+tc_tol)))


    #mark bits with invalid periods as invalid
    for x in range(0, len(invalid)):
        if invalid[x]:
            bits[x] = -2
    #index within a frame -1 means invalid frame
    frame_idx = -1

    weight = [1, 2, 4, 8, 0, 10, 20, 40, -1, 1, 2, 4, 8, 0, 10, 20, 40, 0, -1,
              1, 2, 4, 8, 0, 10, 20, 0, 0, -1, 1, 2, 4, 8, 0, 10, 20, 40, 80, -1,
              100, 200, 0, 0, 0, 0.1, 0.2, 0.4, 0.8, -1, 1, 2, 4, 8, 0, 10, 20, 40, 80, -1,
              1, 2, 4, 8, 16, 32, 64, 128, 256, -1, 1, 2, 4, 8, 16, 32, 64, 128, 256, -1,
              1, 2, 4, 8, 16, 32, 64, 128, 256, -1, 512, 1024, 2048, 4096, 8192, 16384, 32768, 65536, 0, -1]

    value=[1,1,1,1,1,1,1,1,-1,2,2,2,2,2,2,2,2,2,-1,
           3,3,3,3,3,3,3,3,3,-1,4,4,4,4,4,4,4,4,4,-1,
           4,4,4,4,4,5,5,5,5,-1,6,6,6,6,6,6,6,6,6,-1,
           7,7,7,7,7,7,7,7,7,-1,8,8,8,8,8,8,8,8,8,-1,
           9,9,9,9,9,9,9,9,9,-1,9,9,9,9,9,9,9,9,9,-1]

    #preallocate frames to hold the maximum number of frames
    frames = np.zeros((int(np.floor(len(bits)/100)), max(value)))
    #preallocate frame bits
    fbits = np.zeros((int(np.floor(len(bits)/100)), 100))
    #sample number of the first rising edge in the frame
    fsamp = np.zeros((int(np.floor(len(bits)/100)), ), dtype=int) # gsh3: np.int--> int

    #frame number
    fnum = 0

    for k in range(1, len(bits)):
        #check if current flame is invalid
        if(frame_idx==-1):
            #check for a frame start
            if(bits[k]==2 and bits[k-1]==2):
                #set new frame index
                frame_idx = 0
                #zero frame data
                frame = np.zeros(max(value))
        else:
            #check if this should be a marker bit
            if(frame_idx % 10) == 8:
                #check if marker is found
                if (bits[k]!=2):
                    #give warning for missing marker
                    warn('Marker not found at frame index %i' % frame_idx)
                    #reset frame index
                    frame_idx = -1
                    #restart loop
                    continue
            else:
                #check that bit is a 1 or zero
                if(bits[k]!=1 and bits[k]!=0):
                    #give warning based on bit value
                    bit = bits[k]
                    if (bit == -2):
                        #give warning for invalid period
                        warn('Invalid bit period at frame index %i' % frame_idx)
                    elif(bit == -1):
                        #give warning for invalid bit value
                        warn('Invalid bit at frame index %i' % frame_idx)
                            
                    elif(bit == 2):
                        #give warning for unexpected marker
                        warn('Unexpected marker at frame index %i' % frame_idx)
                    else:
                        #give warning for invalid bit value
                        warn('Unexpected bit value %i at frame index %i' %(bits[k],frame_idx))
                    #reset frame index
                    frame_idx = -1
                    #restart loop
                    continue
                #get value idx
                vi = value[frame_idx]
                #otherwise get bit value
                frame[vi-1] = frame[vi-1]+bits[k]*weight[frame_idx]
            #increment frame index
            frame_idx = frame_idx+1
            #check if frame is complete
            if(frame_idx>=99):
                #store decoded frame data
                frames[fnum] = frame
                #store decoded frame bits
                fbits[fnum] = bits[(k-99):k+1]
                #get sample number of the first rising edge after frame marker
                fsamp[fnum] = r_edg[k-98]
                #search for next frame
                frame_idx = -1
                #increment frame number
                fnum = fnum+1

    #remove extra data
    frames = frames[0:fnum]
    fbits = fbits[0:fnum]
    fsamp = fsamp[0:fnum]



    #create date vectors
    #IRIG B does not give month or day of month so use a empty part of the
    #frame for month and fix it to 1 later. Day of year will wrap to the
    #correct month

    dvec = frames[:, [5, 4, 3, 2, 1, 0]]
    
    #add in year digits from current year
    dvec[:, 0] = dvec[:, 0] + np.floor(datetime.datetime.now().year / 100) * 100
    
    #set month to 1
    dvec[:, 1] = 1

    dates = []
    for d in dvec:
        year, month, day, hour, minute, second = tuple(int(d[i]) for i in (0, 1, 2, 3, 4, 5))
        date = datetime.datetime(year, month, 1, hour, minute, second)
        #create a dummy time delta of the days, which will be added to each time
        #make sure to subtract 1 from days because default day value of 1 was used
        dummyTime = datetime.timedelta(days=day-1)
        #format the datetime into a string
        dates += [date + dummyTime]

    #this version returns the dates as a string instead of a datetime object
    #this can be used for testing purposes
    '''dates = []
    for d in dvec:
        year, month, day, hour, minute, second = tuple(int(d[i]) for i in (0, 1, 2, 3, 4, 5))
        date = datetime.datetime(year, month, 1, hour, minute, second)
        #create a dummy time delta of the days, which will be added to each time
        #make sure to subtract 1 from days because default day value of 1 was used
        dummyTime = datetime.timedelta(days=day-1)
        #format the datetime into a string
        dates += [(date + dummyTime).strftime("%d-%b-%Y %H:%M:%S")]'''

    return np.array(dates), fsamp


    
    
#helper function used in envelope()
#calulates amplitudes in singal x using N-tap Hilbert filter
def envFIR(x, n):

    #construct ideal hilbert filter truncated to desired length
    fc = 1
    t = (fc/2) * np.arange((1-n)/2, ((n-1)/2) + 1)
    
    hfilt = np.sinc(t) * np.exp(1j*np.pi * t)

    #multiply ideal filter with tapered window
    beta = 8
    firFilter = hfilt * np.kaiser(n,beta)
    firFilter = firFilter / sum(np.real(firFilter))

    #apply filter and take the magnitude
    y = np.abs(np.convolve(x, firFilter, 'same'))
    return(y)
    

    #although the following code affected the output of envFIR, it did not affect
    #the final result of time_decode as it is negligible
    '''Due to differences in convolution algorithims for even-length inputs
    in python and MATLAB, we must delete the first sample data point of the 
    signal, and append an additonal sample data point onto the end - 
    calculated from the result of the 'full' convolution. 
    This yields the MATLAB equivalent
    y = y[1:]
    temp = np.abs(np.convolve(x,firFilter,'full')).tolist()
    y = np.append(y, temp[temp.index(y[-1])+1])
    return(y)'''


#uses an N-tap Hilbert filter to compute the upper envelope of X
def envelope(x, n):
    xmean = np.mean(x)
    xcentered = x - xmean
    xampl = envFIR(xcentered, n)
    yupper = xmean + xampl

    return yupper


#validates the pulse width with an array of bools
def is_valid_pw(val, th):
    return np.logical_and(val > th[0], val < th[1])

#helps to ensure that thresholds don't overlap
def fix_overlap(t1, t2):
    #check if thresholds overlap    
    if(t1>t2):
        #set thresholds to average
        t1 = np.mean([t1, t2])
        #this calculates machine epsilon
        t2 = t1+np.finfo(float).eps
    return t1, t2


def pw_to_bits(pw, Tb, tol):
    #thresholds for ones
    Th1 = 0.5 * Tb + Tb * np.array([-tol, tol])
    #thresholds for zeros
    Th0 = 0.2 * Tb + Tb * np.array([-tol, tol])
    #thresholds for marker
    Thm = 0.8 * Tb + Tb * np.array([-tol, tol])
    #make sure thresholds don't overlap
    Th0[1], Th1[0] = fix_overlap(Th0[1], Th1[0])
    Th1[1], Thm[0] = fix_overlap(Th1[1], Thm[0])
    #check for valid pulse width for a one
    valid1 = is_valid_pw(pw, Th1)
    #check for valid pulse width for a zero
    valid0 = is_valid_pw(pw, Th0)
    #check for valid marker pulse width
    validmk = is_valid_pw(pw, Thm)
    #print(validmk.tolist())
    
    #return 0 for zero 1 for one 2 for mark and -1 for invalid
    bits = valid1 + (2 * validmk) - np.logical_not(np.logical_or.reduce((validmk, valid1, valid0)))
    return bits
# TODO: add abcmrt as mcvqoe requirement (pypi abcmrt16)
# This should already be the case
import abcmrt
import csv
import glob
import json
import math
import mcvqoe.base
import os
import re
import shutil

import numpy as np

from mcvqoe.timing.audio_chans import timecode_chans
from datetime import datetime, timedelta
from mcvqoe.base.terminal_user import terminal_progress_update
from mcvqoe.delay import ITS_delay_est
from mcvqoe.timing.timecode import time_decode 
from mcvqoe.utilities.reprocess import get_module, reprocess_file


# This should break up the folder name to determine Tx/Rx, date, and test type
def test_name_parts(folder):
    
    # Regular expression extraction of folder naming parts "date" and "test"
    parts = re.match(r"(?P<date>\d{2}-\w{3}-\d{4}_\d{2}-\d{2}-\d{2})_(?P<test>[a-zA-Z0-9]+)",
                 folder
                 )
    if not parts:
        raise RuntimeError(f'Unable to find test name parts from \'{folder}\'')
        
    # Rx/Tx extraction from "test"
    t_r = None
    for i in ["Tx2Loc", "Rx2Loc"]:
        if i in parts.group("test"):
            t_r = i
    # If we haven't found a 2 location tx or rx test
    if t_r == None:
        raise RuntimeError(f"Unable to process from folder: {folder}. Make sure"+
                               " it's a 2 location test.")
            
    # Test type extraction from given "test"
    testtype = None
    for i in ["Access", "Intelligibility", "M2E", "PSuD", "TVO"]:
        if i in parts.group("test"):
            testtype = i
    # If we haven't found a proper test
    if testtype == None:
        raise RuntimeError(f"Unable to determine test type from '{folder}'\n"+
                           "Ensure the proper naming convention.")
        
    return (t_r, testtype, parts.group('date'))

def timedelta_total_seconds(time):
    try:
        # Try it as if it's an array
        return [timedelta_total_seconds(t) for t in time]
    except TypeError:
        # Not an array, must be scalar time
        return time.days*(24*60*60) + time.seconds + time.microseconds*1e-6

# Function to quickly find the index of the nearest value
# From https://stackoverflow.com/a/26026189
def find_nearest(array,value):
    idx = np.searchsorted(array, value, side="left")
    if idx > 0 and (idx == len(array) or math.fabs(value - array[idx-1]) < math.fabs(value - array[idx])):
        return idx-1
    else:
        return idx

# TODO: remove default argument for rx_name and make required here and in argparse below.
# TODO: allow for relative paths to tx_name and rx_name, now it gives: RuntimeError: unable to extract wav folder from 'Tx_capture_Intell_18-Jan-2024_15-19-04.csv'

def twoloc_process(tx_name, extra_play=0, 
                        rx_name = None, 
                        outdir="",
                        progress_update=terminal_progress_update,
                        align_mode='fixed', 
                        **kwargs       #get kwargs to accept arbitrary arguments
                   ):
    """
    Process rx and tx files for a two location test.
    
    This writes a .csv file to ~home\documents\MCV-QoE\<test type>\<test>Reprocess
    and .wav files to ~home\documents\MCV-QoE\<test type>\<test>Reprocess\wav
    for a test. 

    Parameters
    ----------
    tx_name : string
        Path to the transmit .csv. User is forced to select a csv file
    extra_play : float, default=0
        Extra audio to add after tx clip stopped. This maybe used, in some
        cases, to correct for data that was recorded with a poorly chosen
        overplay.
    rx_name : string, None
        Name of the receive .wav. User is forced to choose a wave file.
    outdir : string, default=""
        Directory that contains the `data/` folder where data will be read from
        and written to. This is auto defaulted to our standard
        ~home\documents\MCV-QoE folder to avoid errors.
    test_type : string, default='intelligibility'
        Either 'intelligibility' or 'm2e'. Intelligibility also estimates m2e latency.
    align_mode : string, defualt = 'fixed'
        Method used to align sent and received audio signals. Fixed is best behaving.
    progress_update : function, default=terminal_user
        Function to call with updates on processing progress. 
        
    Returns
    -------
    csv_out_name : string
        The path to the reprocessed data csv file
        
    See Also
    --------
        mcvqoe.mouth2ear : mouth to ear code, can produce 2 location data.
        mcvqoe.intelligibility : Gathers two location code to be reprocessed.
    """

    #This software was developed by employees of the National Institute of
    #Standards and Technology (NIST), an agency of the Federal Government.
    #Pursuant to title 17 United States Code Section 105, works of NIST
    #employees are not subject to copyright protection in the United States and
    #are considered to be in the public domain. Permission to freely use, copy,
    #modify, and distribute this software and its documentation without fee is
    #hereby granted, provided that this notice and disclaimer of warranty
    #appears in all copies.
    #
    #THE SOFTWARE IS PROVIDED 'AS IS' WITHOUT ANY WARRANTY OF ANY KIND, EITHER
    #EXPRESSED, IMPLIED, OR STATUTORY, INCLUDING, BUT NOT LIMITED TO, ANY
    #WARRANTY THAT THE SOFTWARE WILL CONFORM TO SPECIFICATIONS, ANY IMPLIED
    #WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, AND
    #FREEDOM FROM INFRINGEMENT, AND ANY WARRANTY THAT THE DOCUMENTATION WILL
    #CONFORM TO THE SOFTWARE, OR ANY WARRANTY THAT THE SOFTWARE WILL BE ERROR
    #FREE. IN NO EVENT SHALL NIST BE LIABLE FOR ANY DAMAGES, INCLUDING, BUT NOT
    #LIMITED TO, DIRECT, INDIRECT, SPECIAL OR CONSEQUENTIAL DAMAGES, ARISING
    #OUT OF, RESULTING FROM, OR IN ANY WAY CONNECTED WITH THIS SOFTWARE,
    #WHETHER OR NOT BASED UPON WARRANTY, CONTRACT, TORT, OR OTHERWISE, WHETHER
    #OR NOT INJURY WAS SUSTAINED BY PERSONS OR PROPERTY OR OTHERWISE, AND
    #WHETHER OR NOT LOSS WAS SUSTAINED FROM, OR AROSE OUT OF THE RESULTS OF, OR
    #USE OF, THE SOFTWARE OR SERVICES PROVIDED HEREUNDER.
   
    #-----------------------------Validate inputs-----------------------------

    # Normalize path
    tx_name = os.path.normpath(tx_name)

    # Shouldn't be allowed to give directory
    # This code is just safety
    if os.path.isdir(tx_name):
        
        # Given directory, assume this is the ran test directory
        tx_path = tx_name
        # Find .csv files in the directory
        csvs = glob.glob(os.path.join(tx_path, '*.csv'))

        if not csvs:
            raise RuntimeError(f'No .csv files found in \'{tx_path}\'')
        elif len(csvs) > 1:
            raise RuntimeError(f'More than one .csv file found in \'{tx_path}\'')

        tx_name = csvs[0]
        
    else:
        # Get folder path from filename
        tx_path = os.path.dirname(tx_name)

    # Get folder name (just name, no path)
    tx_fold = os.path.basename(tx_path)

    if not tx_fold:
        raise RuntimeError(f'unable to extract wav folder from \'{tx_name}\'')

    # Extract parts of tx name for validation
    (tx_prefix, tx_tt, tx_date) = test_name_parts(tx_fold)
    
    # Get ran Tx wav folder
    tx_wav_path = os.path.join(tx_path, "wav")
    
    # Check prefix
    if(tx_prefix != 'Tx2Loc'):
        raise ValueError(f'Unexpected filename prefix \'{tx_prefix}\' for tx file')
    
    # extra_play must be non-neg
    if extra_play < 0:
        raise ValueError("extra_play must be non negative")

    # Tolerance for timecode variation
    tc_warn_tol = 0.0001

    # Determine test type 
    if tx_tt not in ('M2E', 'Intelligibility'):
            raise RuntimeError(f"'test_type' argument must be 'M2E' or 'Intelligibility' not {tx_tt}")
    
    if tx_tt== 'Intelligibility':
        if align_mode != 'fixed':
            progress_update('warning', 0, 0, msg="Only align_mode='fixed' gives reliable intelligibility scores." )
    # Should be in same test folder as all other data
    # --------------------------[Locate input data]--------------------------
    
    # Go one level up from .csv file
    rx_dir = os.path.dirname(tx_name)

    # -----------------------[Setup Files and folders]-----------------------

    # # generate data dir names
    # data_dir = os.path.join(outdir, "data")
    # wav_data_dir = os.path.join(data_dir, "wav")
    # csv_data_dir = os.path.join(data_dir, "csv")

    # # create data directories
    # os.makedirs(csv_data_dir, exist_ok=True)
    # os.makedirs(wav_data_dir, exist_ok=True)

    # # generate base file name to use for all files
    # base_filename = '_'.join(('capture2', tx_tt, tx_date))

    # # generate test dir names
    # wavdir = os.path.join(wav_data_dir, base_filename)

    # # create test dir
    # os.makedirs(wavdir, exist_ok=True)

    # # generate csv name
    # csv_out_name = os.path.join(csv_data_dir, f"{base_filename}.csv")
    
    ############################################ My new code
    
    # Generate base filename to use for folder/files
    base_filename = '_'.join((tx_date, tx_tt, '2LocReprocess'))
    
    # Generate data folder
    data_dir = os.path.join(outdir, base_filename)
    os.makedirs(data_dir, exist_ok=True)
    
    # Generate wav folder
    wav_data_dir = os.path.join(data_dir, "wav")
    os.makedirs(wav_data_dir, exist_ok=True)
    
    # Generate csv name
    csv_out_name = os.path.join(data_dir, f"{base_filename}.csv")
    
    #------------------Find appropriate rx file by timecode------------------
    #if a rx file name is not specified, find the appropriate file in rx-dat 
    #folder. if there are more than one suitable rx files based on timecode, 
    #this will find the one with the smallest delay, with delay defined as 
    #difference between the start times of the rx and tx recordings
    
    # If no file was specified for the rx file, search for it in rx-dat
    # TODO: Make it so that you have to input an rx-file
    # Currently I don't believe we should ever enter this "if" statement block
    if not rx_name:
    
        # Attempt to get date from tx filename
        print(f'The tx date is {tx_date}')
        tx_date = datetime.strptime(tx_date, '%d-%b-%Y_%H-%M-%S')
        
        # rx_files is a dict with the delays as keys, and the rx path as values
        rx_files = {}
        progress_update('status', 0, 0, msg=f'looking for rx files in \'{rx_dir}\'')
        
        # Loop thru all rx 
        for rx_file_name in glob.glob(os.path.join(rx_dir, '*.wav')):
            progress_update('status', 0, 0, msg=f'Looking at {rx_file_name}')
            # Strip leading folders
            rx_basename = os.path.basename(rx_file_name)
            # Split into parts
            (rx_prefix, rx_tt, rx_date) = test_name_parts(rx_basename)
            
            # Validate that this is a correct rx file
            if rx_prefix != 'Rx2Loc':
                # Give error
                progress_update('warning', 0, 0, msg=f'Rx filename "{rx_basename}" is not in the proper form.'+
                                ' Can not determine Rx filename')
                # If not a correct rx file, skip this file and go to next one
                continue
            
            rx_start_date = datetime.strptime(rx_date, '%d-%b-%Y_%H-%M-%S')
            # Add to the rx_file dict, with delays as the key, and full path as value
            rx_files[tx_date-rx_start_date] = rx_file_name
    
        # Create a np array of all of delays
        delays = np.array(list(rx_files), dtype=timedelta)
        
        # Find the smallest positive delay
        minDelay = min(delays[delays > timedelta()])
        
        # Find the file with the the smallest delay
        rx_name = rx_files[minDelay]

        progress_update('status', 0, 0, msg=f'Loading {rx_name}')

        # Read file
        #rx_fs, rx_dat = v
        rx_fs, rx_dat = mcvqoe.base.audio_read(rx_name)
    
        # Find the duration of the rx file
        duration = timedelta(seconds=len(rx_dat)/rx_fs)
        
        print(duration)
        
        # Check that tx date falls within rx file time
        if minDelay < duration:
            rx_name = rx_files[minDelay]
        # Otherwise there is no suitable rx file
        else:
            raise ValueError("Could not find suitable Rx file")
    
    else:
        rx_fs, rx_dat = mcvqoe.base.audio_read(rx_name)
    
    rx_dat = mcvqoe.base.audio_float(rx_dat)

    # check fs
    if tx_tt == 'Intelligibility':
        if(abcmrt.fs != rx_fs):
               raise RuntimeError('Recorded intelligibility sample rate does not match abcmrt!')
    
    #--------------------Prep work for calculating delays--------------------

    rx_info_name = os.path.splitext(rx_name)[0]+'.json'
    rx_align_rec = os.path.splitext(rx_name)[0]+'_align_rec.wav' #+gsh3
    
    with open(rx_info_name) as info_f:
        rx_info = json.load(info_f)
        
    tc_chans = timecode_chans(rx_info['channels'])
    if not tc_chans:
        raise ValueError(f'Timecode channel could not be found in {rx_info["channels"]}')
    
    # Use the first one
    rx_tc_idx = tc_chans[0]
    
    # Timecode type
    rx_tc_type = rx_info['channels'][rx_tc_idx]
    
    # Get channels
    rx_extra_chans = rx_info['channels']
    # Remove timecode channel
    del rx_extra_chans[rx_tc_idx]
    
    # Decode the rx timecode
    # try:
    rx_tca = rx_dat[:, rx_tc_idx]
    rx_time, rx_snum = time_decode(rx_tc_type, rx_tca, rx_fs)
    
    
    ###### This block outputs for diagnostic purposes gsh3#######
    # def time_formatter(dt_s):
    #     days = []
    #     seconds = []
    #     for dt in dt_s:
    #         day = f"{dt.year}_{dt.month}_{dt.day}"  
    #         days.append(day)
    #         second = dt.hour*60*60 + dt.minute*60 + dt.second
    #         seconds.append(second)
    #     days = set(days)
    #     return days, seconds
        
    # days, seconds = time_formatter(rx_time) #
    
    # rx_dict = {'rx_date': list(days), 
    #            'rx_times': seconds,  # +gsh3
    #            'rx_snum': rx_snum.tolist()           # +gsh3
    #           } 
    # rx_time_name = os.path.splitext(rx_name)[0]+'_time.json'     
    # output_json = json.dumps(rx_dict)        # +gsh3            
    # with open(rx_time_name, 'w') as output:  # +gsh3            
    #     output.write(output_json)            # +gsh3            
   ##############################################################
    
    # Make rx_time a numpy array
    rx_time = np.array(rx_time)
    
    if align_mode == 'interpolate':
        # We are interpolating, get reference time
        ref_time =  rx_time[0]
        # Interpolate so we have intermediate values
        rx_interp = np.interp(range(len(rx_dat)), rx_snum,timedelta_total_seconds(rx_time-ref_time))
    elif align_mode == 'fit':
        # We are fitting, get reference time
        ref_time =  rx_time[0]
        # Fit index vs time
        # Do a linear fit of the timecode data to get time vs index
        rx_fit = np.polyfit(timedelta_total_seconds(rx_time-ref_time), rx_snum, 1)
        # Get model
        rx_idx_fun = np.poly1d(rx_fit)

    extra_samples = extra_play * rx_fs

    ### Iterate through the TX CSV rows to find the timing code and align with the RX codes
    with open(tx_name, 'rt') as tx_csv_f, open(csv_out_name, 'wt', newline='') as out_csv_f:
        
        # Create dict reader
        reader = csv.DictReader(tx_csv_f)
        header = reader.fieldnames

        if tx_tt == 'Intelligibility':
            header.append('m2e_latency')
        
        # Create dict writer, same fields as input
        writer = csv.DictWriter(out_csv_f, reader.fieldnames)
        
        # Write output header
        writer.writeheader()
        
        # Get data from file
        #NOTE : this may not work well for large files! but should, typically, be fine
        rows = tuple(reader)
        
        # Get total trials for progress
        total_trials = len(rows)
    
        # Loop through all tx recordings
        for trial, row in enumerate(rows):
            
            progress_update('proc', total_trials, trial)
            
            tx_rec_name = f'Rx{trial+1}_{row["Filename"]}.wav'
            full_tx_rec_name = os.path.join(tx_wav_path, tx_rec_name)

            # Check if file exists
            # If not os.path.exists(clip_path): gsh3
            if not os.path.exists(full_tx_rec_name): #+gsh3
                # Update progress
                progress_update('status', total_trials, trial,
                msg = f"{full_tx_rec_name} not found")
                # Unzip audio if it exists
                # mcvqoe.base.Measure.unzip_audio(audio_path) #-gsh3

            tx_rec_fs, tx_rec_dat = mcvqoe.base.audio_read(full_tx_rec_name)

            # Check that audio sampling rate is the same  +gsh3
            if rx_fs != tx_rec_fs:
                 raise ValueError(f'RX and TX sampling not the same for {full_tx_rec_name}')

            # Make floating point for processing purposes
            tx_rec_dat = mcvqoe.base.audio_float(tx_rec_dat)
            
            tx_rec_chans = mcvqoe.base.parse_audio_channels(row['channels'])
            
            if(len(tx_rec_chans)==1):
                # Only one channel, make sure that it's a timecode
                if('timecode' not in tx_rec_chans[0]):
                    raise ValueError(f'Expected timecode channel but got {row["channels"][0]}')
                
                # Make sure that timecode types match
                if rx_tc_type != tx_rec_chans[0]:
                    raise ValueError(f'Tx timecode type is {tx_rec_chans[0]} but Rx timecode type is {rx_tc_type}')
                
                # One channel, only timecode
                tx_rec_tca = tx_rec_dat
                
                tx_extra_audio = None
                tx_extra_chans = None
            else:                
                # Grab the same type of timecode we used for Rx
                tx_time_idx = tx_rec_chans.index(rx_tc_type)

                tx_rec_tca = tx_rec_dat[:, tx_time_idx]

                # Extra channels
                tx_extra_audio = np.delete(tx_rec_dat, tx_time_idx, 1)

                # Copy to new array without timecode channel
                tx_extra_chans = list(tx_rec_chans)
                del tx_extra_chans[tx_time_idx]
                
            
            # Decode timecode
            try:
                tx_time, tx_snum = time_decode(rx_tc_type, tx_rec_tca, tx_rec_fs)
                
                
                if align_mode == 'fixed':
                    # Array for matching sample numbers
                    tx_match_samples = []
                    rx_match_samples = []


                    for time, snum in zip(tx_time, tx_snum):
                        
                        # Calculate difference from rx timecode
                        time_diff = abs(rx_time - time)
                        
                        # Find minimum difference
                        min_v = np.amin(time_diff)

                        # Check that difference is small
                        if min_v < timedelta(seconds=0.5):

                            # Get matching index
                            idx = np.argmin(time_diff)

                            # Append sample number
                            tx_match_samples.append(snum)
                            rx_match_samples.append(rx_snum[idx])

                    # Get matching frame start indicies
                    mfr = np.column_stack((tx_match_samples, rx_match_samples))

                    # Get difference between matching timecodes
                    mfd = np.diff(mfr, axis=0)


                    # Get ratio of samples between matches
                    mfdr = mfd[:, 0] / mfd[:, 1]

                
                    if not np.all(np.logical_and(mfdr < (1+tc_warn_tol), mfdr>(1-tc_warn_tol))):
                        progress_update('warning', total_trials, trial, f'Timecodes out of tolerence for trial {trial+1}. {mfdr}')

                    # Calculate first rx sample to use
                    first = mfr[0, 1]-mfr[0, 0]

                    # Calculate last rx sample to use
                    last = mfr[-1,1] + len(tx_rec_tca) - mfr[-1, 0] + extra_samples - 1
                elif align_mode == 'interpolate' or align_mode =='fit':
                    tx_tnum = timedelta_total_seconds(tx_time - ref_time)

                    # Do a linear fit of the timecode data to get index vs time
                    fit = np.polyfit(tx_snum, tx_tnum, 1)
                    # Get model
                    tc_fun = np.poly1d(fit)

                    # Get time of start and end of tx clip
                    tx_start_time = tc_fun(0)
                    tx_end_time = tc_fun(len(tx_rec_tca) + extra_samples - 1)

                    if align_mode == 'interpolate':
                        # Get indices in the Rx array
                        first = find_nearest(rx_interp, tx_start_time)
                        last  = find_nearest(rx_interp, tx_end_time)
                    elif align_mode == 'fit':
                        first = math.floor(rx_idx_fun(tx_start_time))
                        last  = math.ceil(rx_idx_fun(tx_end_time))

                else:
                    raise ValueError(f'Invalid value, \'{align_mode}\' for align_mode')
                # Get rx recording data from big array
                rx_rec = rx_dat[first:last+1, :]
                # Remove timecode
                rx_rec = np.delete(rx_rec, rx_tc_idx, 1)
                # Diagnostic output gsh3
                mcvqoe.base.audio_write(rx_align_rec, 48000, rx_rec)
                
                if tx_extra_chans:
                    # Add tx extra chans to rx extra chans
                    out_chans = tuple(rx_extra_chans+tx_extra_chans)

                    # Get the length of the longest array
                    new_len = np.max((rx_rec.shape[0], tx_extra_audio.shape[0]))

                    # Resize recording
                    rec_shape = list(rx_rec.shape)
                    rec_shape[0] = new_len
                    rx_rec.resize(tuple(rec_shape))

                    # Resize tx extra
                    tx_shape = list(tx_extra_audio.shape)
                    tx_shape[0] = new_len
                    tx_extra_audio.resize(tuple(tx_shape))

                    # Both arrays should now be the same length (in time)
                    out_audio = np.column_stack((rx_rec, tx_extra_audio))
                else:
                    # No extra chans, all out chans from rx
                    out_chans = rx_extra_chans
                    out_audio = rx_rec
                
                # Overwrite new channels to csv
                row['channels'] = mcvqoe.base.audio_channels_to_string(out_chans)
                
                ## Find the phrase file if only the timing is present
                if tx_extra_audio is None:
                    full_tx_phrase_name = os.path.join(tx_wav_path, 'Tx_' + row['Filename'] + '.wav')
                    if not os.path.exists(full_tx_phrase_name):
                        raise ValueError(f'cannot find {full_tx_phrase_name}')
                    
                    tx_phrase_fs, tx_phrase_dat = mcvqoe.base.audio_read(full_tx_phrase_name)
                    if tx_phrase_fs != rx_fs:
                        raise ValueError(f'RX and TX sampling not the same for {full_tx_phrase_name}')
                    tx_extra_chans = mcvqoe.base.audio_float(tx_phrase_dat)
                
                rx_phrase = np.concatenate(rx_rec)
           
                ###### m2e estimates ########
                
                # Run delay with final position, and the number of samples at which audio aligns
                (pos, delay_points) = ITS_delay_est(tx_extra_chans, 
                                                    rx_phrase, 
                                                    'f', 
                                                    fs=rx_fs, 
                                                    dlyBounds=[np.NINF, np.inf], 
                                                    min_corr=0)

                delay_time = delay_points/tx_phrase_fs 
                row['m2e_latency'] = delay_time 
                ###################################

                ########## intelligibility calculation  ##############################
                if tx_tt == 'Intelligibility':
                    try:
                        ### latency estimate to adjust time capture
                        first     = first + delay_points*3//2
                        last      = last + delay_points*3//2
                        rx_rec    = rx_dat[first:last+1,:]
                        rx_rec = np.delete(rx_rec,rx_tc_idx,1)
                        rx_phrase = np.concatenate(rx_rec)
                         
                        word_num=abcmrt.file2number(full_tx_rec_name)  ### TX FILE NAME GOES HERE
                    except:
                        raise ValueError(f'cannot inturrpert {full_tx_rec_name} as an abcmrt phrase number')

                    phi_hat, intelligibility=abcmrt.process(rx_phrase, word_num) ##RX VOICE AUDIO GOES HERE
                    row['Intelligibility'] = intelligibility[0] #only a single list element

            except Exception as err:
                # TODO: Figure out a way to keep the test going if this happens? (Probably due to low Timecode audio)
                print(f"\n\n{err}\n\n")
                progress_update('warning', 0, 0, msg=f'failed to align {row}')
                pass
                    ##################################

            # Create audiofile name/path for recording
            audioname = f'Rx{trial+1}_{row["Filename"]}.wav'
            audioname = os.path.join(wav_data_dir, audioname)

            # Save out Rx recording as given data type
            mcvqoe.base.audio_write(audioname, rx_fs, out_audio)
                
            # Write row to new .csv
            writer.writerow(row)
        
        # Copy Tx files into destination folder
        for name in glob.glob(os.path.join(tx_wav_path, 'Tx_*')):
            # Get clip name from path
            clip_name = os.path.basename(name)
            # Construct destination name
            destname = os.path.join(wav_data_dir, clip_name)
            # Copy file
            shutil.copyfile(name, destname)

    # Return output filename
    return csv_out_name


def main():
    import argparse

    parser = argparse.ArgumentParser()

    parser.add_argument("tx_name",
                        type=str,
                        help='Name of the Tx .csv file to process/'
                        )
    parser.add_argument("--extra-play",
                        type=int,
                        default=0,
                        help='Duration of extra audio to add after tx clip '+
                        'stopped. This mayb be used, in some cases, to correct '+
                        'for data that was recorded with a poorly chosen overplay.'
                        )
    parser.add_argument("--rx-name",
                        type=str,
                        default=None,
                        help='Filename of the rx file to use. If a directory '+
                        'is given, it will be searched for files'
                        )
    parser.add_argument("--outdir",
                        type=str,
                        default="",
                        help='Root of directory structure where data will be stored'
                        )
    parser.add_argument('-m', '--measurement',
                        type=str,
                        default=None,
                        metavar='M',
                        help='measurement to use to do reprocessing'
                        )

    args = parser.parse_args()

    # Try to load measurement class
    try:
        measurement_class = get_module(module_name=args.measurement, datafile=args.tx_name)
    except (RuntimeError, KeyError):
        terminal_progress_update('warning', 0, 0, msg='Unable to determine measurement. Output file will not be processed')
        # Set measurement class for later
        measurement_class = None

    out_name = twoloc_process(**vars(args))

    if measurement_class:
        # Create test obj to reprocess with
        test_obj = measurement_class()

        reprocess_file(test_obj, out_name, out_name)

        print(f'Reprocessing complete for \'{out_name}\'')

if __name__ == '__main__':
    main()
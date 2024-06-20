import argparse
import fnmatch
import math
import mcvqoe.base
import os
import re

import numpy as np
import pandas as pd

from mcvqoe.base.terminal_user import terminal_progress_update


class Diagnose():
    """
    Diagnose Class to perform diagnostic evaluation of received
    audio data wav files and confirm data integrity.
     
    Use a-weight, FSF, and clipping checks to inform
    user of potential problems in collected data. Flags
    trials that may require further investigation.
    
    Parameters
    ----------
    wav_dir : string
        directory of WAV files
    progress_update : function, default=mcvqoe.base.terminal_user.terminal_progress_update
        function to call to provide updates on test progress. This function
        takes three positional arguments, prog_type, total number of trials, 
        current trial number. Depending on prog_type, different information is 
        displayed to the user.

    Attributes
    ----------
    tx_filename : list
        names of tx audio files
    tx_wavs   :  list
        audio for tx audio
    Trials : int
        number of trials 
    rx_rec : list 
        audio for rx recordings   
    fs : int 
        sampling rate of rx recordings       
    rx_dat : list
        names of rx recordings

    """
    
    def __init__(self, 
                 wav_dir = '',
                 progress_update=terminal_progress_update,
                 ):
        # Assign wav_dir
        self.wav_dir = wav_dir
        # Assign progress update
        self.progress_update = progress_update
        self.trials = None
        
        # Create empty list for rx recordings 
        self.rx_rec = []
        self.rx_dat = []
            
        self.outname = None
        
    def load_audio(self):
        """
        Loads in Rx data and the associated Tx files. Rx files are read in 
        order into a list of arrays.
    
        """
        
        # Read in a directory of test trial wav files.
        # Get all the Rx wav files 
        dir_files = os.listdir(self.wav_dir)
        naming = 'Rx*'
        all_wavs = fnmatch.filter(dir_files, naming)
        # Get total number of trials
        self.trials = len(all_wavs)
        if self.trials == 0:
            raise RuntimeError(f'No recorded audio detected in {self.wav_dir}')
        # If an access time test, naming varies. Rx numbering resets by talker
        if 'Access' in self.wav_dir:
            # Get unique talker lists
            f1_list = [s for s in all_wavs if 'F1' in s]
            f3_list = [s for s in all_wavs if 'F3' in s]
            m3_list = [s for s in all_wavs if 'M3' in s]
            m4_list = [s for s in all_wavs if 'M4' in s]
            # Store the lists together
            talkers_dat = [f1_list, f3_list, m3_list, m4_list]
            # Iterate through each talker's set and read in separately
            for talkers in talkers_dat:
                talker_trials = len(talkers)
                # Cycle through Rx files in order
                for n in range(1,talker_trials+1):
                    self.progress_update(
                        prog_type="diagnose",
                        num_trials=talker_trials,
                        current_trial=n,
                        msg='Loading Audio',
                        )
                    start = 'Rx'+str(n)+'_'
                    rx_name = [s for s in talkers if start in s]
                    rx_path = self.wav_dir + '/' + rx_name[0]
                    # Check how many channels we have 
                    self.fs,y_rec = mcvqoe.base.audio_read(rx_path)
                    if len(y_rec.shape) > 1:
                        # If more than one channel, just grab the first channel
                        y_rec = y_rec[:, 0]
                    self.rx_rec.append(y_rec[:]) 
                    self.rx_dat.append(rx_name[0])
            
        else:     
            # Cycle through Rx files, in order, for all other measurements
            for n in range(1,self.trials+1):
                self.progress_update(
                    prog_type="diagnose",
                    num_trials=self.trials,
                    current_trial=n,
                    msg='Loading Audio',
                    )
                start = 'Rx'+str(n)+'_'
                rx_name = [s for s in all_wavs if start in s]
                rx_path = self.wav_dir + '/' + rx_name[0]
                # Check how many channels we have
                try:
                    self.fs, y_rec = mcvqoe.base.audio_read(rx_path)
                except ValueError:
                    # Most likely an empty WAV file, skip
                    continue
                if len(y_rec.shape) > 1:
                    # If more than one channel, just grab the first channel
                    y_rec = y_rec[:, 0]
                self.rx_rec.append(y_rec[:]) 
                self.rx_dat.append(rx_name[0])
        # Find all the Tx files in the wav_dir, strip the Tx and .wav off 
        tx_names = 'Tx*'
        tx_obj = fnmatch.filter(dir_files, tx_names)
        self.tx_filename =fnmatch.filter(tx_obj, '*.wav')
        # Create empty list for tx wavs 
        self.tx_wavs = []
        if tx_obj:
            # Cycle through and get all the TX files
            for k in range(0,len(self.tx_filename)):
                tx_path = self.wav_dir + '/' + self.tx_filename[k]
                self.fs,tx_wavfile = mcvqoe.base.audio_read(tx_path)
                self.tx_wavs.append(tx_wavfile)

    def aw_calc(self):
        """
        Calculates the a-weight (dBA) of each trial.
    
        Returns
        -------
        A_Weight : list
            A_Weight of every trial 
        """
          
        # Get A-weight
        self.progress_update(
                prog_type="status",
                msg='Calculating A-weight power'
                )
            
        a_weight =  [mcvqoe.base.a_weighted_power(k,self.fs) for k in self.rx_rec]
        
        return a_weight
    
    def fsf_calc(self):   
        """
        Calculate FSF scores of each trial. 
    
        Returns
        -------
        FSF_all : list
           FSF scores of every trial 
        """
        # Create empty list for FSF scores
        fsf_all = []
        
        # Cycle through, match RX names to tx names
        # Get just the names of tx files, remove the Tx and .wav 
        tx_base = []
        for n in range(0,len(self.tx_filename)):
            tx_justname = re.sub('\.wav$', '', self.tx_filename[n])
            tx_justname = tx_justname[3:]
            tx_base.append(tx_justname)   
        if tx_base == []:
            self.progress_update(
                prog_type='diagnose',
                num_trials=0,
                current_trial=0,
                msg='Unable to calculate FSF -- no transmit audio found'
                )
            return -np.Inf
        for j in range(0,self.trials): 
            self.progress_update(
                prog_type="diagnose",
                num_trials=self.trials,
                current_trial=j,
                msg='Calculating FSF',
                )
            # Find RX files with the matching TX name, create groups 
            match_wavs = re.match(r'(Rx\d+_(?P<tx_base_name>[^.]+))',self.rx_dat[j])
            
            # Find the index of the TX and RX clips to match with the lists of 
            # wav data
            tx_idx = tx_base.index(match_wavs.group('tx_base_name'))
            tx_wav = self.tx_wavs[tx_idx]
            rx_wav = self.rx_rec[j]
            
            # Get FSF scores for each tx-rx pair
            get_fsf = mcvqoe.base.fsf(rx_wav,tx_wav,self.fs)
            # Get just the FSF score
            fsf_all.append(get_fsf[0])   
    
        return fsf_all

    def peak_amp_calc(self):
        """
        Cycle through all rx recordings and get peak amplitude.

        Returns
        ------- 
        peak_dbfs : list
            Peak amplitude of each trial, dB relative to full 
            scale
            
        """
        
        # Create empty list for peak amplitude
        peak_dbfs = []
        for n in range(0,self.trials):
            self.progress_update(
                prog_type="diagnose",
                num_trials=self.trials,
                current_trial=n,
                msg='Calculating Peak Amplitude',
                )
            # Check for positive and negative clipping
            peak = max(abs(self.rx_rec[n]))
            peak_db = round(20 * math.log10(peak), 2)
            peak_dbfs.append(peak_db)
        
        return peak_dbfs
    
    def clip_flag(self,peak_dbfs):
        """
        Cycle through the peak amplitude and check
        for clipping.  
    
        Returns
        -------
        clip_flag : list
            Trials that clipped 
    
        """
        
        # Set up warning threshold
        vol_high = -1
        # Create empty list for setting flags
        clip_flag = []
        # Check for positive and negative clipping
        peak = np.array(peak_dbfs)
        for n in range(0,self.trials):
            # If approaching clipping, flag as a bad trial
            if peak[n] >= vol_high:
                # Flag as a clipped trial
                clip_wav = 1
                # Add it to the bad list
                clip_flag.append(clip_wav) 
            elif peak[n] < vol_high:   
                # Flag as a non-clipped trial
                clip_wav = 0
                # Add it to the list
                clip_flag.append(clip_wav)         
        
        return clip_flag   

    def fsf_flag(self,fsf_all):
        """
        Check for trials with an FSF a certain distance
        from the mean. Use this info to find trials that 
        may have lost audio.
            
        Returns
        -------
        fsf_flag : list
            Trials that have low FSF scores or otherwise deviate 
            from the patterns of the dataset
            
        """
        
        if np.isinf(fsf_all).all():
            return 0
        # Create empty list for FSF flag    
        fsf_flag = []
        # Gather metrics for FSF scores
        fsf_array = np.array(fsf_all)
        fsf_mean = round(np.mean(fsf_array),3)
        fsf_std = round(np.std(fsf_array),3)
        for m in range(0,self.trials):
            # Cycle through FSF scores, look for trials where the score
            # stands out by being a certain distance from the mean. Add a flag
            # for low FSF scores that may be a sign of dropped audio
            if abs(fsf_array[m]-fsf_mean) > 2*fsf_std or fsf_array[m] < 0.4:
                # Flag the trial due to FSF score
                fsf_flag_wav = 1
                # Add it to the bad list
                fsf_flag.append(fsf_flag_wav)
            elif abs(fsf_array[m]-fsf_mean) < 2*fsf_std:
                # Do not flag
                fsf_flag_wav = 0
                # Add it to the list
                fsf_flag.append(fsf_flag_wav)        
        
        return fsf_flag

    def aw_flag(self,a_weight):
        """
        Check for trials with a dBA less than -50 dBA. Check 
        for trials with a dBA a certain distance from the 
        mean.   
    
        Returns
        -------     
        aw_flag : list
            Trials that have low dBA values (and likely lost audio)
            or otherwise deviate from the patterns of the dataset 
    
        """
        
        # Create empty list for a-weight flag     
        aw_flag = []
        # Calculate mean a-weight, standard deviation.
        # Use this info to find trials that may have lost
        # audio. 
        aw_array = np.array(a_weight)
        aw_lin = 10**(aw_array/20)
        aw_low = 10**(-50/20)
        aw_mean = round(np.mean(aw_lin),3)
        aw_std = round(np.std(aw_lin),3)
        for m in range(0,self.trials):
            # Cycle through AW values, look for trials where the values
            # stand out by being a certain distance from the mean.
            # Add a flag if the a-weight is below -50 dBA
            if abs(aw_lin[m]-aw_mean) > 2*aw_std or aw_lin[m] < aw_low:
                aw_flagged = 1
                # Add it to the bad list
                aw_flag.append(aw_flagged)
            elif abs(aw_lin[m]-aw_mean) < 2*aw_std:
                # Do not flag
                aw_flagged = 0
                aw_flag.append(aw_flagged)        
        
        return aw_flag
        
    def gather_diagnostics(self, a_weight, fsf_all, peak_dbfs,
                           clip_flag, fsf_flag, aw_flag,
                           filename='diagnostics.csv'):
        """
        Create a dataframe of all diagnostic data. A-weighted power,
        FSF scores, max clip amplitude, and flags. Returns calculations
        as a csv.
        
        Parameters
        ----------
        A_Weight : list    
            A-Weight across all Rx trials 
        FSF_all : list
            FSF scores across all Rx trials
        peak_dbfs : list     
            Peak amplitude across all Rx trials   
        clip_flag : list
            Trials that clipped    
        fsf_flag : list
            Trials that have low FSF scores or otherwise deviate 
            from the patterns of the dataset
        aw_flag : list
            Trials that have low dBA values (and likely lost audio)
            or otherwise deviate from the patterns of the dataset         
        
        Returns
        -------
        diagnostics_csv : csv 
            CSV containing all the data for diagnostics measurements
            
        """
        
        outname = os.path.join(self.wav_dir, filename)
        self.progress_update(
               prog_type="status",
               msg=f'Writing {outname}',
               num_trials=0,
               current_trial=0,
           )

        # Create dataframe of info
        df_diagnostics = pd.DataFrame({"RX_Name":self.rx_dat, 
                     "A_Weight":a_weight,
                     "FSF_Scores":fsf_all,
                     "Peak_Amplitude":peak_dbfs,
                     "AW_flag":aw_flag,
                     "Clip_flag":clip_flag,
                     "FSF_flag":fsf_flag})
     
        outname = os.path.join(self.wav_dir, filename)
        # Write csv    
        df_diagnostics.to_csv(outname, index=False)
        
        return outname
    
    def run_diagnostics(self, filename='diagnostics.csv'):
        
        # Run through diagnostics measurements 
        a_weight = self.aw_calc()   
        aw_flag = self.aw_flag(a_weight)
        
        fsf_all = self.fsf_calc()
        fsf_flag = self.fsf_flag(fsf_all)
         
        peak_dbfs = self.peak_amp_calc()
        clip_flag = self.clip_flag(peak_dbfs)
        
        self.outname = self.gather_diagnostics(a_weight,
                                               fsf_all,
                                               peak_dbfs,
                                               clip_flag,
                                               fsf_flag,
                                               aw_flag,
                                               filename=filename,
                                               )
        

def main():   
    """
    Read in a directory of WAV files. 
    Use a-weight, FSF, and clipping checks to inform
    user of potential problems in collected data. Flags
    trials that may require further investigation.
    """
    
    # Input parsing
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "wav_dir",
        default=None,
        type=str,
        help="Directory to test data wav files",
    )
    # Parse input arguments
    args = parser.parse_args()
    obj = Diagnose(args.wav_dir)
    print("Measuring a-weight") 
    a_weight = obj.aw_calc()   
    aw_flag = obj.aw_flag(a_weight)
    print("Measuring FSF") 
    fsf_all = obj.fsf_calc()
    fsf_flag = obj.fsf_flag(fsf_all)
    print("Measuring peak amplitude") 
    peak_dbfs = obj.peak_amp_calc()
    clip_flag = obj.clip_flag(peak_dbfs)
    print("Creating json and csv") 
    obj.gather_diagnostics(a_weight,fsf_all,peak_dbfs,clip_flag,fsf_flag,aw_flag)

if __name__ == "__main__":
    main()
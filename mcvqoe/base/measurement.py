import csv
import glob
import datetime
import os
import json
import mcvqoe.timing
import re
import shutil
import string
import time
import zipfile

import numpy as np

from itertools import cycle
from .misc import audio_write, write_cp
from .naming import get_meas_basename
from .write_log import fill_log, pre as log_pre, post as log_post

class Measure:

    no_log = ()

    # measurement name, override in subclass
    measurement_name = "Base"

    required_chans = {
                    '1loc' : {
                                "rec" : ("rx_voice",),
                                "pb" : ("tx_voice",),
                             },
                    # NOTE : for 2 location, recording inputs will be checked
                    #        to see if they include a timecode channel
                    '2loc_tx' : {
                                "rec" : (),
                                "pb" : ("tx_voice",),
                                },
                    '2loc_rx' : {
                                "rec" : ("rx_voice",),
                                "pb" : (),
                             },
                      }

    # filename for zipped audio
    _zip_name = 'audio.zip'

    @staticmethod
    def channel_check(expected, given):
        missing = []
        for name in expected:
            if name not in given:
                missing.append(name)
        return missing

    def check_channels(self):
        rec_missing = self.channel_check(
                                    self.required_chans[self.test]['rec'],
                                    self.audio_interface.rec_chans.keys()
                                         )
        if rec_missing:
            raise ValueError(f"self.audio_interface missing recording channels for : {rec_missing}")

        pb_missing = self.channel_check(
                                    self.required_chans[self.test]['pb'],
                                    self.audio_interface.playback_chans.keys()
                                        )
        if pb_missing:
            raise ValueError(f"self.audio_interface missing playback channels for : {pb_missing}")

    def audio_clip_check(self):
        # dummy function, override if needed
        pass

    def log_extra(self):
        """
        A place to add test specific fields to the log
        """
        # dummy function, override if needed

        # Add blocksize and buffersize
        self.blocksize = self.audio_interface.blocksize
        self.buffersize = self.audio_interface.buffersize

    def param_check(self):
        """
        Check that parameters are correct.
        
        Raises
        ------
        ValueError
            If there is an incorrect parameter.
        """
        # dummy function, override if needed
        pass

    def test_setup(self):
        """
        Extra things that need to be setup for a specific test
        """
        # dummy function, override if needed
        pass

    def run(self, **kwargs):
        if self.test == "1loc":
            return self.run_1loc(**kwargs)
        elif self.test == "2loc_tx":
            return self.run_2loc_tx(**kwargs)
        elif self.test == "2loc_rx":
            return self.run_2loc_rx(**kwargs)
        else:
            raise ValueError(f'Unknown test type "{self.test}"')

    def run_1loc(self):
        """
        Run a generic test.
        """
        
        # -----------------[Try statement for ending post notes]---------------
        
        try:
        
            # ------------------[For loop for multiple iterations]-----------------
        
            for itr in range(self.iterations):    
        
                # ------------------------[Test specific setup]------------------------
                
                self.test_setup()
                
                # ------------------[Check for correct audio channels]------------------
                
                self.check_channels()
                
                # -------------------------[Get Test Start Time]-------------------------
        
                self.info["Tstart"] = datetime.datetime.now()
                dtn = self.info["Tstart"].strftime("%d-%b-%Y_%H-%M-%S")
        
                # --------------------------[Fill log entries]--------------------------
                
                # Set test name
                self.info["test"] = self.measurement_name
                
                # Add iteration number
                self.info["iteration #"] = f"{itr+1} of {self.iterations}"
                
                # Add any extra entries
                self.log_extra()
                
                # Fill in standard stuff
                self.info.update(fill_log(self))
        
                # -----------------------[Setup Files and folders]-----------------------
        
                # Generate this test's naming convention
                fold_file_name = f"{dtn}_{self.info['test']}"
                
                # Create data folder
                self.data_dirs.append(os.path.join(self.outdir, fold_file_name))
                os.makedirs(self.data_dirs[itr], exist_ok=True)
        
                # generate base file name to use for all files
                base_filename = fold_file_name
        
                # generate and create wav directory
                wavdir = os.path.join(self.data_dirs[itr], "wav")
                os.makedirs(wavdir, exist_ok=True)
        
                # generate csv name
                csv_name = os.path.join(self.data_dirs[itr], f"{base_filename}.csv")
                # self.data_filename.append(os.path.join(self.data_dirs[itr], f"{base_filename}.csv"))
        
                # generate temp csv name
                temp_data_filename = os.path.join(self.data_dirs[itr], f"{base_filename}_TEMP.csv")
                # Temporarily make the data filename the TEMP name
                self.data_filename.append(temp_data_filename)
        
                # ---------------------[Load Audio Files if Needed]---------------------
        
                if not hasattr(self, "y"):
                    self.load_audio()
        
                # check audio clips, and possibly, adjust the number of trials
                self.audio_clip_check()
        
                # generate clip index
                self.clipi = self.rng.permutation(self.trials) % len(self.y)
        
                # -----------------------[Add Tx audio to wav dir]-----------------------
        
                # get name with out path or ext
                clip_names = [os.path.basename(os.path.splitext(a)[0]) for a in self.audio_files]
        
        
                if hasattr(self, 'cutpoints'):
                    cutpoints = self.cutpoints
                else:
                    # placeholder for zip
                    cutpoints = cycle((None,))
                # write out Tx clips to files
                # cutpoints, if present, are always written
                for dat, name, cp in zip(self.y, clip_names, cutpoints):
                    out_name = os.path.join(wavdir, f"Tx_{name}")
                    if self.save_tx_audio and self.save_audio:
                        audio_write(out_name + ".wav", int(self.audio_interface.sample_rate), dat)
                    # write cutpoints, if present
                    if cp:
                        write_cp(out_name+'.csv',cp)
        
                # -------------------------[Generate CSV header]-------------------------
        
                header, dat_format = self.csv_header_fmt()
        
                # ---------------------------[write log entry]---------------------------
        
                # Add the log file to the outside folder and test specific folder
                log_pre(info=self.info, outdir=self.outdir, test_folder=self.data_dirs[itr])
        
                # ------------------[Save Time for Set Timing]---------------------
                
                set_start = datetime.datetime.now().replace(microsecond=0)
                
                # -------------------------[Turn on RI LED]-------------------------
                
                self.ri.led(1, True)
    
                # -----------------------[write initial csv file]-----------------------
                
                with open(temp_data_filename, "wt") as f:
                    f.write(header)
    
                # ------------------------[Measurement Loop]------------------------
    
                # zero pause count
                self._pause_count = 0
    
                if not hasattr(self, 'pause_trials'):
                    # if we don't have pause_trials, that means no pauses
                    self.pause_trials = np.inf
    
                for trial in range(self.trials):
                    
                    # -----------------------[Update progress]-------------------------
                    
                    if not self.progress_update("test", self.trials, trial, gui_extras=self.gui_extras):
                        # turn off LED
                        self.ri.led(1, False)
                        print("Exit from user")
                        break
                    
                    # -----------------------[Get Trial Timestamp]-----------------------
                    
                    ts = datetime.datetime.now().strftime("%d-%b-%Y %H:%M:%S")
    
                    # --------------------[Key Radio and play audio]--------------------
    
                    # Press the push to talk button
                    self.ri.ptt(True)
    
                    # Pause the indicated amount to allow the radio to access the system
                    time.sleep(self.ptt_wait)

                    clip_index = self.clipi[trial]
    
                    # Create audiofile name/path for recording
                    audioname = f"Rx{trial+1}_{clip_names[clip_index]}.wav"
                    audioname = os.path.join(wavdir, audioname)
    
                    # Play/Record
                    rec_chans = self.audio_interface.play_record(self.y[clip_index], audioname)
    
                    # Release the push to talk button
                    self.ri.ptt(False)
    
                    # -----------------------[Pause Between runs]-----------------------
    
                    time.sleep(self.ptt_gap)
    
                    # -----------------------------[Data Processing]----------------------------
    
                    trial_dat = self.process_audio(
                        clip_index,
                        audioname,
                        rec_chans,
                    )
    
                    # add extra info
                    trial_dat["Timestamp"] = ts
                    trial_dat["Filename"] = clip_names[clip_index]
    
                    # -------------------[Delete file if needed]-------------------
                    
                    if not self.save_audio:
                        os.remove(audioname)
    
                    # --------------------------[Write CSV]--------------------------
    
                    with open(temp_data_filename, "at") as f:
                        f.write(dat_format.format(**trial_dat))
    
                    #------------------[Check if we should pause]------------------
    
                    # increment pause count
                    self._pause_count += 1
    
                    if self._pause_count >= self.pause_trials:
    
                        # zero pause count
                        self._pause_count = 0
    
                        # Calculate set time
                        time_diff = datetime.datetime.now().replace(microsecond=0)
                        set_time = time_diff - set_start
    
                        # Turn on LED when waiting for user input
                        self.ri.led(2, True)
    
                        # wait for user
                        user_exit = self.user_check(
                                'normal-stop',
                                'check batteries.',
                                trials=self.pause_trials,
                                time=set_time,
                            )
    
                        # Turn off LED, resuming
                        self.ri.led(2, False)
    
                        if(user_exit):
                            raise SystemExit()
    
                        # Save time for next set
                        set_start = datetime.datetime.now().replace(microsecond=0)
    
                # -----------------------------[Cleanup]-----------------------------
                
                # Add csv_name to self.data_filename
                # This is done here just in case we abort during a test which causes
                # errors later on since only the TEMP filename has been created
                # ex.: FileNotFoundError when running through self.data_filename
                self.data_filename[itr] = csv_name
    
                # move temp file to real file
                shutil.move(temp_data_filename, self.data_filename[itr])
    
                # ---------------------------[Turn off RI LED]---------------------------
    
                self.ri.led(1, False)
            
        finally:
                
            # Try just in case we don't have directories yet
            try:
                # Sending lists so that post_write can handle multiple iterations
                self.post_write(test_folder=self.data_dirs, file=self.data_filename)
                    
            except AttributeError as e:
                # Haven't created the self.data_dirs yet
                print("Error occured before testing began")
                print(f"\n\n{e}\n\n")
                
        # Return filename list
        return self.data_filename

    def run_2loc_tx(self):
        """
        Run a two location test.

        This is a generic test function for tests like m2e, PSuD and
        Intelligibility.
        """

        # ------------------------[Test specific setup]------------------------
        
        self.test_setup()
        
        # ------------------[Check for correct audio channels]------------------
        
        self.check_channels()
        
        # We need to be recording a timecode
        mcvqoe.timing.require_timecode(self.audio_interface)
        
        # -------------------------[Get Test Start Time]-------------------------

        self.info["Tstart"] = datetime.datetime.now()
        dtn = self.info["Tstart"].strftime("%d-%b-%Y_%H-%M-%S")

        # --------------------------[Fill log entries]--------------------------
        
        # set test name, needs to match log_search.datafilenames
        self.info["test"] = f"{self.measurement_name}Tx2Loc"
        
        # add any extra entries
        self.log_extra()
        
        # fill in standard stuff
        self.info.update(fill_log(self))

        # -----------------------[Setup Files and folders]-----------------------
        
        # Create test's naming convention
        fold_file_name = f"{dtn}_{self.info['test']}"
        
        # Create data folder
        self.data_dir = os.path.join(self.outdir, fold_file_name)
        os.makedirs(self.data_dir, exist_ok=True)

        # Generate base file name to use for all files
        base_filename = fold_file_name

        # Generate and creat wav directory
        wavdir = os.path.join(self.data_dir, "wav")
        os.makedirs(wavdir, exist_ok=True)

        # generate csv name
        self.data_filename = os.path.join(self.data_dir, f"{base_filename}.csv")

        # generate temp csv name
        temp_data_filename = os.path.join(self.data_dir, f"{base_filename}_TEMP.csv")

        # ---------------------[Load Audio Files if Needed]---------------------

        if not hasattr(self, "y"):
            self.load_audio()

        self.audio_clip_check()

        # generate clip index
        self.clipi = self.rng.permutation(self.trials) % len(self.y)

        # -----------------------[Add Tx audio to wav dir]-----------------------

        # get name with out path or ext
        clip_names = [os.path.basename(os.path.splitext(a)[0]) for a in self.audio_files]

        if hasattr(self, 'cutpoints'):
            cutpoints = self.cutpoints
        else:
            # placeholder for zip
            cutpoints = cycle((None,))

        # write out Tx clips to files
        for dat, name, cp in zip(self.y, clip_names, cutpoints):
            out_name = os.path.join(wavdir, f"Tx_{name}")
            audio_write(out_name + ".wav", int(self.audio_interface.sample_rate), dat)
            # write cutpoints, if present
            if cp:
                write_cp(out_name+'.csv',cp)

        # -------------------------[Generate CSV header]-------------------------

        header, dat_format = self.csv_header_fmt()

        # ---------------------------[write log entry]---------------------------

        log_pre(info=self.info, outdir=self.outdir, test_folder=self.data_dir)

        # ---------------[Try block so we write notes at the end]---------------
        
        try:

            # ------------------[Save Time for Set Timing]---------------------
            
            set_start = datetime.datetime.now().replace(microsecond=0)            

            # -----------------------[write initial csv file]-----------------------
            
            with open(temp_data_filename, "wt") as f:
                f.write(header)

            # -------------------------[Turn on RI LED]-------------------------

            self.ri.led(1, True)

            # ------------------------[Measurement Loop]------------------------

            # zero pause count
            self._pause_count = 0

            if not hasattr(self, 'pause_trials'):
                # if we don't have pause_trials, that means no pauses
                self.pause_trials = np.inf

            for trial in range(self.trials):

                # -----------------------[Update progress]-------------------------
                if not self.progress_update("test", self.trials, trial):
                    # turn off LED
                    self.ri.led(1, False)
                    print("Exit from user")
                    break
                # -----------------------[Get Trial Timestamp]-----------------------
                ts = datetime.datetime.now().strftime("%d-%b-%Y %H:%M:%S")

                # --------------------[Key Radio and play audio]--------------------

                # Press the push to talk button
                self.ri.ptt(True)

                # Pause the indicated amount to allow the radio to access the system
                time.sleep(self.ptt_wait)

                clip_index = self.clipi[trial]

                # Create audiofile name/path for recording
                audioname = f"Rx{trial+1}_{clip_names[clip_index]}.wav"
                audioname = os.path.join(wavdir, audioname)

                # Play/Record
                rec_chans = self.audio_interface.play_record(self.y[clip_index], audioname)

                # Release the push to talk button
                self.ri.ptt(False)

                # -----------------------[Pause Between runs]-----------------------

                time.sleep(self.ptt_gap)

                # --------------------------[Write CSV]--------------------------

                chan_str = "(" + (";".join(rec_chans)) + ")"

                # generate dummy values for format
                trial_dat = {}
                for _, field, _, _ in string.Formatter().parse(dat_format):
                    if field not in self.data_fields:
                        if field is None:
                            # we got None, skip this one
                            continue
                        # check for array
                        m = re.match(r'(?P<name>.+)\[(?P<index>\d+)\]',field)
                        if not m:
                            # not in data fields, fill with NaN
                            trial_dat[field] = np.NaN
                        else:
                            field_name = m.group("name")
                            index = int(m.group("index"))
                            if field_name not in trial_dat or \
                                len(trial_dat[field_name]) < index + 1:
                                trial_dat[field_name] = (np.NaN,) * (index +1)
                    elif self.data_fields[field] is float:
                        # float, fill with NaN
                        trial_dat[field] = np.NaN
                    elif self.data_fields[field] is int:
                        # int, fill with zero
                        trial_dat[field] = 0
                    else:
                        # something else, fill with None
                        trial_dat[field] = None

                # fill in known values
                trial_dat['Timestamp'] = ts
                trial_dat['Filename'] = clip_names[clip_index]
                trial_dat['channels'] = chan_str

                with open(temp_data_filename, "at") as f:
                    f.write(
                        dat_format.format(
                            **trial_dat
                        )
                    )

                #------------------[Check if we should pause]------------------

                # increment pause count
                self._pause_count += 1

                if self._pause_count >= self.pause_trials:

                    # zero pause count
                    self._pause_count = 0

                    # Calculate set time
                    time_diff = datetime.datetime.now().replace(microsecond=0)
                    set_time = time_diff - set_start

                    # Turn on LED when waiting for user input
                    self.ri.led(2, True)

                    # wait for user
                    user_exit = self.user_check(
                            'normal-stop',
                            'check batteries.',
                            trials=self.pause_trials,
                            time=set_time,
                        )

                    # Turn off LED, resuming
                    self.ri.led(2, False)

                    if(user_exit):
                        raise SystemExit()

                    # Save time for next set
                    set_start = datetime.datetime.now().replace(microsecond=0)

            # -----------------------------[Cleanup]-----------------------------

            # move temp file to real file
            shutil.move(temp_data_filename, self.data_filename)

            # ---------------------------[Turn off RI LED]---------------------------

            self.ri.led(1, False)

            # -----------------------[Notify User of Completion]------------------------

            self.progress_update(
                "status",
                self.trials,
                self.trials,
                msg="Data collection complete, you may now stop data collection on" + " the receiving end",
            )

        finally:
            #self.post_write(test_folder=self.data_dir)
            if self.get_post_notes:
                # Get notes
                info = self.get_post_notes()
            else:
                info = {}
            # Finish log entry
            log_post(info=info, outdir=self.outdir, test_folder=self.data_dir)

        # return filename in a list
        return (self.data_filename,)

    def run_2loc_rx(self):
        """
        Two location receive basic test.

        This function just records audio with a little bit of logging. Should be
        usable by all 2 location tests.
        """

        # ------------------------[Test specific setup]------------------------
        
        self.test_setup()
        
        # ------------------[Check for correct audio channels]------------------
        
        self.check_channels()
        
        # We need to be recording a timecode
        mcvqoe.timing.require_timecode(self.audio_interface)

        # -------------------------[Get Test Start Time]-------------------------
        
        self.info["Tstart"] = datetime.datetime.now()
        dtn = self.info["Tstart"].strftime("%d-%b-%Y_%H-%M-%S")

        # --------------------------[Fill log entries]--------------------------

        # Set test name, needs to match log_search.datafilenames
        self.info["test"] = f"{self.measurement_name}Rx2Loc"
        
        # Add any extra entries
        self.log_extra()
        
        # Fill in standard stuff
        self.info.update(fill_log(self))

        # -----------------------[Setup Files and folders]-----------------------
        
        # Create naming convention
        fold_file_name = f"{dtn}_{self.info['test']}"
        
        # Create data folder
        self.data_dir = os.path.join(self.outdir, fold_file_name)
        os.makedirs(self.data_dir, exist_ok=True)

        # Create filename to use everywhere
        base_filename = fold_file_name

        self.data_filename = os.path.join(self.data_dir, "Rx_" + base_filename + ".wav")

        info_name = os.path.join(self.data_dir, "Rx_" + base_filename + ".json")

        # ---------------------------[write log entry]---------------------------

        log_pre(info=self.info, outdir=self.outdir, test_folder=self.data_dir)

        # ---------------[Try block so we write notes at the end]---------------
        
        try:
            
            # ----------------------[Send progress update]---------------------
            
            self.progress_update("status", 1, 0, msg="Two location receive recording running")

            # --------------------------[Record audio]--------------------------
            
            rec_names = self.audio_interface.record(self.data_filename)

            # ------------------------[Save audio info]------------------------

            with open(info_name, "wt") as info_f:
                json.dump({"channels": rec_names}, info_f)

        finally:
            #self.post_write(test_folder=self.data_dir)
            if self.get_post_notes:
                # Get notes
                info = self.get_post_notes()
            else:
                info = {}
            # Finish log entry
            log_post(info=info, outdir=self.outdir, test_folder=self.data_dir)

        # Return filename in a list
        return (self.data_filename,)

    def load_test_data(self, fname, load_audio=True, audio_path=None):
        """
        load test data from .csv file.

        Parameters
        ----------
        fname : string
            filename to load
        load_audio : bool, default=True
            if True, finds and loads audio clips and cutpoints based on fname
        audio_path : str, default=None
            Path to find audio files at. Guessed from fname if None.

        Returns
        -------
        list of dicts
            returns data from the .csv file

        """

        with open(fname, "rt") as csv_f:
            # create dict reader
            reader = csv.DictReader(csv_f)
            # create empty list
            data = []
            # create set for audio clips
            clips = set()
            for row in reader:
                # convert values proper datatype
                for k in row:
                    # check for clip name
                    if k == "Filename":
                        # save clips
                        clips.add(row[k])
                    try:
                        # check for None field
                        if row[k] == "None":
                            # handle None correctly
                            row[k] = None
                        else:
                            # convert using function from data_fields
                            row[k] = self.data_fields[k](row[k])
                    except KeyError:
                        # not in data_fields, convert to float
                        row[k] = float(row[k])

                # append row to data
                data.append(row)

        # set total number of trials, this gives better progress updates
        self.trials = len(data)

        # check if we should load audio
        if load_audio:
            # we do not want to load the full dir for reprocessing
            self.full_audio_dir = False

            # set audio file names to Tx file names
            self.audio_files = ["Tx_" + name + ".wav" for name in clips]

            print(f'Audio clip names : {self.audio_files}')

            dat_name = get_meas_basename(fname) + "Tx2Loc"

            if audio_path is not None:
                self.audio_path = audio_path
            else:
                # set audio_path based on filename
                self.audio_path = os.path.join(os.path.dirname(os.path.dirname(fname)), dat_name, "wav")

            # load audio data from files
            self.load_audio()
            self.audio_clip_check()

        return data

    # get the clip index given a partial clip name
    def find_clip_index(self, name):
        """
        find the inex of the matching transmit clip.

        Parameters
        ----------
        name : string
            base name of audio clip

        Returns
        -------
        int
            index of matching tx clip

        """

        # match a string that has the chars that are in name
        name_re = re.compile(re.escape(name) + "(?![^.])")
        
        # get all matching indices
        match = [idx for idx, clip in enumerate(self.audio_files) if name_re.search(clip)]
        
        # check that a match was found
        if not match:
            raise RuntimeError(f"no audio clips found matching '{name}' found in {self.audio_files}")
            
        # check that only one match was found
        if len(match) != 1:
            raise RuntimeError(f"multiple audio clips found matching '{name}' found in {self.audio_files}")
            
        # return matching index
        return match[0]

    @staticmethod
    def unzip_audio(audio_path):
        
        zip_path = os.path.join(audio_path,Measure._zip_name)
        
        if zipfile.is_zipfile(zip_path):
            audio_zip = zipfile.ZipFile(zip_path,mode='r')
            
            #extract all files into the audio dir
            audio_zip.extractall(audio_path)

    def zip_wavdir(self, path):
        """
        Replace the receive audio files in `path` with a zip file.

        Parameters
        ----------
        path : string
            A path to the directory where the test .wav files are stored.

        """
        
        with zipfile.ZipFile(
                    os.path.join(path,self._zip_name),
                    mode='w',
                    compression=zipfile.ZIP_LZMA,
                ) as audio_zip:
            
            # find all the rx wav files
            rx_wavs = glob.glob(os.path.join(path, 'Rx*.wav'))
            
            # fid all bad files
            bad_wavs = glob.glob(os.path.join(path, 'Bad*.wav'))
            
            # zip bad files and Rx files
            zip_wavs = rx_wavs + bad_wavs
            
            # get number of files
            num_zip_files = len(zip_wavs)
            for n, name in enumerate(zip_wavs):
                bname =  os.path.basename(name)
                self.progress_update('compress', num_zip_files, n)
                audio_zip.write(name, arcname=bname)

        # zip file has been written, delete files
        self.progress_update('status', num_zip_files, num_zip_files, msg='Deleting compressed audio...')
        for name in zip_wavs:
            os.remove(name)

    def post_process(self, test_dat, fname, audio_path):
        """
        process csv data.

        Parameters
        ----------
        test_data : list of dicts
            csv data for trials to process
        fname : string
            file name to write processed data to
        audio_path : string
            where to look for recorded audio clips

        Returns
        -------
        """

        # do extra setup things
        self.test_setup()

        # get .csv header and data format
        header, dat_format = self.csv_header_fmt()

        with open(fname, "wt") as f_out:

            f_out.write(header)

            for n, trial in enumerate(test_dat):

                # update progress
                self.progress_update("proc", self.trials, n)

                # find clip index
                clip_index = self.find_clip_index(trial["Filename"])
                # create clip file name
                clip_name = "Rx" + str(n + 1) + "_" + trial["Filename"] + ".wav"

                try:
                    # attempt to get channels from data
                    rec_chans = trial["channels"]
                except KeyError:
                    # fall back to only one channel
                    rec_chans = ("rx_voice",)
                    
                new_dat = self.process_audio(
                        clip_index,
                        os.path.join(audio_path, clip_name),
                        rec_chans
                        )

                # overwrite new data with old and merge
                merged_dat = {**trial, **new_dat}

                # write line with new data
                f_out.write(dat_format.format(**merged_dat))
                
    def post_write(self, test_folder="", file=""):
        """
        Provide a function to allow overwriting of post note function.
        
        This allows each test the ability to print the results into
        their repective tests.log file
        """

        if self.get_post_notes:
            # get notes
            info = self.get_post_notes()
        else:
            info = {}
        # finish log entry
        log_post(outdir=self.outdir, info=info, test_folder=test_folder)
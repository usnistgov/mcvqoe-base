import contextlib
import datetime
import queue
import sys
import threading

import numpy as np
import sounddevice as sd
import soundfile as sf

from mcvqoe.timing.soft_timecode import soft_time_fmt

try:
    import ctypes
    

    class ThreadRecStop:
        """
        Class for stopping audio recording

        This class uses a thread running `input()` to get input from the user.
        This a fallback RecStop method that should be available on most platforms

        See Also
        --------
        mcvqoe.hardware.AudioPlayer : ThreadRecStop works with AudioPlayer.record
        """

        def _input(self):
            
            print("Press enter to stop")
            # wait for input
            input()
            # user pressed enter, done
            self._done = True

        def __enter__(self):
            
            self._done = False
            self.thread = threading.Thread(target=self._input, name="Console_Rec_input")
            self.thread.start()
            return self

        def is_done(self):
            """
            Method to check if recording should stop

            Returns
            -------
            bool
                True if recording should stop, False otherwise
            """
            
            return self._done

        def __exit__(self, exc_type, exc_value, exc_traceback):
            
            if self.thread.is_alive():
                thread_id = self.thread.get_ident()
                res = ctypes.pythonapi.PyThreadState_SetAsyncExc(
                    thread_id, ctypes.py_object(SystemExit)
                )
                if res > 1:
                    ctypes.pythonapi.PyThreadState_SetAsyncExc(thread_id, 0)
                    print("Error while stopping thread")
            return False

except:
    ThreadRecStop = None

try:
    import msvcrt


    class WinRecStop:
        """
        Class for stopping audio recording

        This class uses msvcrt to get keypresses. This will only work on Windows.
        
        See Also
        --------
        mcvqoe.hardware.AudioPlayer : WinRecStop works with AudioPlayer.record
        """

        def __enter__(self):
            
            print("press any key to stop")
            return self

        def __exit__(self, exc_type, exc_value, exc_traceback):
            
            return False

        def is_done(self):
            """
            Method to check if recording should stop

            Returns
            -------
            bool
                True if recording should stop, False otherwise
            """
            
            if msvcrt.kbhit():
                # flush all keys
                while msvcrt.kbhit():
                    msvcrt.getch()
                # key pressed, we are done
                return True
            return False

except:
    # there was a problem, set to None
    WinRecStop = None

try:
    import termios
    import tty


    class TermiosRecStop:
        """
        Class for stopping audio recording

        This class uses termios.tcsetattr to put the terminal into raw mode to
        be able to check for characters in the input without blocking.
        The termios library is only available on Unix systems.
        
        See Also
        --------
        mcvqoe.hardware.AudioPlayer : TermiosRecStop works with AudioPlayer.record
        """

        def __enter__(self):
            
            print("press any key to stop")
            # get stdin file descriptor
            self.fd = sys.stdin.fileno()
            # save old settings to restore later
            self.old_settings = termios.tcgetattr(self.fd)
            # change settings for raw input
            tty.setraw(sys.stdin.fileno())
            return self

        def __exit__(self, exc_type, exc_value, exc_traceback):
            
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)
            return False

        def is_done(self):
            """
            Method to check if recording should stop

            Returns
            -------
            bool
                True if recording should stop, False otherwise
            """
            
            ch = sys.stdin.read(1)
            if len(ch) == 0:
                return True
            else:
                return False

except:
    TermiosRecStop = None

# set a sensible default for recording stop
if TermiosRecStop:
    DefaultRecStop = TermiosRecStop
elif WinRecStop:
    DefaultRecStop = WinRecStop
elif ThreadRecStop:
    DefaultRecStop = ThreadRecStop
else:
    # fallback to null context (terminate with ^C)
    DefaultRecStop = contextlib.nullcontext()


class AudioPlayer:
    """
    Class to play and record audio for test purposes.

    This class has functions for playing and recording audio and is used in QoE
    testing.

    Attributes
    ----------
    sample_rate : int
        Sample rate of audio in/out in samples per second.
    blocksize : int
        The size of the blocks that are sent/received to/from the audio device.
    buffersize : int
        The number of blocks in the output buffer.
    overplay : float
        The number of seconds of extra audio to play/record at the end of a clip.
    device : str
        Audio device to use. can be found with find_device().
    rec_chans : dict
        Dictionary describing the recording. Dictionary keys should be one of
        {'rx_voice','PTT_signal','IRIGB_timecode','tx_beep','soft_timecode'}. The
        value for each entry is the, zero based, channel number that should be
        recorded for each signal. For the special 'soft_timecode' channel, no
        audio recording channel is used and the channel number should be 0.
    playback_chans : dict
        Dictionary describing the playback channels. Dictionary keys must be one
        of {'tx_voice','start_signal'}. The value for each entry is the, zero
        based, channel number that each signal should be played on.
    rec_stop : ContextManager
        Context manager used to test when a recording should be stopped.
        `rec_stop` is used as a context manager that is entered when the recording
        starts and exited when the recording stops. The `is_done` method is called
        to check if the recording should be terminated.

    See Also
    --------
    mcvqoe.simulation.QoEsim : Simulated replacement for AudioPlayer.

    Examples
    --------

    Play audio in tx_voice and record in a file named 'test.wav'.
    note: "F1_harvard_phrases.wav" is found in the mouth2ear 'audio_clips' folder.

    >>> import mcvqoe.hardware.AudioPlayer
    >>> import mcvqoe.base.misc
    >>> rate, tx_voice = mcvqoe.base.audio_read("F1_harvard_phrases.wav")
    >>> ap = mcvqoe.hardware.AudioPlayer(fs=rate)
    >>> ap.play_record(tx_voice, 'test.wav')

    now do the same but also output the start signal on channel 1 and record the
    PTT signal on channel 1.

    >>> ap.playback_chans = {'tx_voice':0, 'start_signal':1}
    >>> ap.rec_chans = {'rx_voice':0, 'PTT_signal':1}
    >>> ap.play_record(tx_voice, 'test.wav')
    """

    def __init__(
        self,
        device_str="UMC",
        **kwargs
    ):

        self.sample_rate = int(48e3)
        self.blocksize = 512
        self.buffersize = 20
        self.overplay = 1.0
        self.rec_chans = {"rx_voice": 0}
        self.playback_chans = {"tx_voice": 0}
        self.rec_stop = DefaultRecStop()

        # get properties from kwargs
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
            # check if the 'fs' argument was given
            elif k == 'fs':
                # fs gets translated to sample_rate for legacy purposes
                self.sample_rate = v
            else:
                raise TypeError(f"{k} is not a valid keyword argument")

        try:
            self.device = self.find_device(device_str)
        except RuntimeError:
            # no device found
            self.device = None

    @staticmethod
    def find_device(device_str="UMC"):

        devs = sd.query_devices()

        for d in devs:
            if (
                d["max_input_channels"] > 0
                and d["max_output_channels"] > 0
                and device_str in d["name"]
            ):
                return d["name"]
        else:
            raise RuntimeError('No suitable audio interfaces found')

    def __repr__(self):
        
        string_props = ('device','sample_rate','overplay','rec_chans','playback_chans')

        props = []

        for prop in string_props:
            props.append(f'{prop} = {repr(getattr(self, prop))}')

        return f'{type(self).__name__}({", ".join(props)})'

    def record(self, filename):
        """
        Record audio based on rec_chans.

        Parameters
        ----------
        filename : str
            The file name to write audio to.
        """

        # check that device is set
        if not self.device:
            RuntimeError('No audio device found')

        # get the highest numbered channel
        # this will be the number of channels that will be played
        # account for zero based indexing
        chans = max(self.rec_chans.values()) + 1

        (rec_map, rec_names) = self._get_recording_map()

        # check if we are "recording" time data
        if "soft_timecode" in self.rec_chans:
            self._time_encode = True
            # find soft timecode channel
            soft_idx = rec_names.index("soft_timecode")
            # soft timecode will be appended
            # it's index will be the number of channels
            rec_map[soft_idx] = chans
        else:
            self._time_encode = False

        # Queue for recording input
        self._qr = queue.Queue()

        # set loop var to False (keep looping)
        rec_done = False

        # Make sure the file is opened before recording anything:
        with sf.SoundFile(
            filename, mode="x", samplerate=self.sample_rate, channels=len(rec_names)
        ) as file:
            with self.rec_stop, sd.InputStream(
                samplerate=self.sample_rate,
                device=self.device,
                channels=chans,
                callback=self._cb_rec,
            ):

                while not rec_done:
                    rx_dat = self._qr.get()
                    file.write(rx_dat[:, rec_map])

                    # check if we are done
                    rec_done = getattr(self.rec_stop, "is_done", lambda: False)()

            # Make sure to write any audio data still left in the recording queue
            while self._qr.empty() != True:
                rx_dat = self._qr.get()
                file.write(rx_dat[:, rec_map])

        # return the channels in the order recorded in the file
        return rec_names

    def _get_recording_map(self):
        """
        Get map and names for recording channels.

        Returns
        -------
        list of ints
            A channel map of the channel numbers used for each recording channel.
        list of strings
            A list of the names of the channels in the order they will be in in
            the recording file.
        """
        
        chan_map = []
        chan_names = []
        for k, v in self.rec_chans.items():
            chan_map.append(v)
            chan_names.append(k)
        return (chan_map, chan_names)

    def play_record(self, tx_voice, filename):
        """
        Play audio out the specified channels and record to 'filename'.

        Plays the audio specified by self.playback_chans on the respective
        channels. Records on the channels specified by self.rec_chans.

        Parameters
        ----------
        tx_voice : numpy array
            Voice audio to play through system. Needs to be in proper sample rate.
        filename : str
            The file extension to write audio data to.

        Returns
        -------
        list of strings
            A list of the recorded output channels in the order that they appear
            in the output file.

        See Also
        --------
        mcvqoe.simulation.QoEsim : Simulated replacement play_record.

        Examples
        --------

        play audio stored in tx_voice and record in a file named 'test.wav'.
        note: "F1_harvard_phrases.wav" is found in the mouth2ear 'audio_clips' folder.
    
        >>> import mcvqoe.hardware.AudioPlayer
        >>> import mcvqoe.base.misc
        >>> rate, tx_voice = mcvqoe.base.audio_read("F1_harvard_phrases.wav")
        >>> ap = mcvqoe.hardware.AudioPlayer(fs=rate)
        >>> ap.play_record(tx_voice, 'test.wav')
    
        now do the same but also output the start signal on channel 1 and record the
        PTT signal on channel 1.
    
        >>> ap.playback_chans = {'tx_voice':0, 'start_signal':1}
        >>> ap.rec_chans = {'rx_voice':0, 'PTT_signal':1}
        >>> ap.play_record(tx_voice, 'test.wav')
        """

        # check that device is set
        if not self.device:
            RuntimeError('No audio device found')

        if len(tx_voice.shape) == 2:
            if tx_voice.shape[1] != 1:
                # TODO : warn about dropping channels
                pass
            # only take one channel of input
            tx_voice = tx_voice[:, 0]

        audio = np.empty((tx_voice.shape[0], len(self.playback_chans)))

        # get the highest numbered playback channel
        # this will be the number of channels that will be played
        # account for zero based indexing
        pb_chan = max(self.playback_chans.values()) + 1
        rec_chan = max(self.rec_chans.values()) + 1

        self._playback_map = []
        self._playback_silent = set(range(pb_chan))

        for n, (k, v) in enumerate(self.playback_chans.items()):
            # add to playback map
            self._playback_map.append(v)
            # remove from silent map
            self._playback_silent.remove(v)
            # Add start signal to audio
            if k == "start_signal":
                # Signal frequency
                # Unused?
                # f_sig = 1e3
                # Signal time
                t_sig = 22e-3
                # Calculate time for playback
                t = np.arange(float(len(audio))) / self.sample_rate
                # Calculate clip start signal
                sig = np.where((t < t_sig), np.sin(2 * np.pi * 1000 * t), 0)
                # Add start signal to audio
                audio[:, n] = sig
            elif k == "tx_voice":
                audio[:, n] = tx_voice
            else:
                raise ValueError(f"Unknown output channel : {k}")

        # convert to tuple for callback usage
        self._playback_silent = tuple(self._playback_silent)

        (rec_map, rec_names) = self._get_recording_map()

        # check if we are "recording" time data
        if "soft_timecode" in self.rec_chans:
            self._time_encode = True
            # find soft timecode channel
            soft_idx = rec_names.index("soft_timecode")
            # soft timecode will be appended
            # it's index will be the number of channels
            rec_map[soft_idx] = rec_chan
        else:
            self._time_encode = False

        # check for 1D audio
        if len(audio.shape) == 1:
            # promote a 1D array to a 2D nx1 array
            audio.shape = (audio.shape[0], 1)

        # Add Overplay
        if self.overplay != 0:
            audio = np.pad(
                audio,
                ((0, int(self.sample_rate * self.overplay)), (0, 0)),
                mode="constant",
            )

        # Queue for recording input
        self._qr = queue.Queue()
        # Queue for playback output
        self._qpb = queue.Queue(maxsize=self.buffersize)

        # Thread for callback function
        event = threading.Event()

        # NumPy audio array placeholder
        arr_place = 0

        for x in range(self.buffersize):

            data_slice = audio[
                self.blocksize * x : (self.blocksize * x) + self.blocksize
            ]

            if data_slice.size == 0:
                break

            # Save place of NumPy array slice for next loop
            arr_place += self.blocksize

            # Pre-fill queue
            self._qpb.put_nowait(data_slice)

        # Output and input stream in one
        # Latency of zero to try and cut down delay
        stream = sd.Stream(
            blocksize=self.blocksize,
            samplerate=self.sample_rate,
            dtype="float32",
            device=self.device,
            channels=[rec_chan, pb_chan],
            callback=self._cb_play_rec,
            finished_callback=event.set,
            latency=0,
        )

        with sf.SoundFile(
            filename,
            mode="x",
            samplerate=self.sample_rate,
            channels=len(self.rec_chans),
        ) as rec_file:
            with stream:
                timeout = self.blocksize * self.buffersize / self.sample_rate

                # For grabbing next blocksize slice of the NumPy audio array
                itrr = 0

                while data_slice.size != 0:

                    data_slice = audio[
                        arr_place
                        + (self.blocksize * itrr) : arr_place
                        + (self.blocksize * itrr)
                        + self.blocksize
                    ]
                    itrr += 1

                    self._qpb.put(data_slice, timeout=timeout)

                    rx_dat = self._qr.get()
                    rec_file.write(rx_dat[:, rec_map])
                # Wait until playback is finished
                event.wait()

            # Make sure to write any audio data still left in the recording queue
            while self._qr.empty() != True:
                rx_dat = self._qr.get()
                rec_file.write(rx_dat[:, rec_map])

        # return the channels in the order recorded in the file
        return rec_names

    def _cb_play_rec(self, indata, outdata, frames, time, status):
        """
        Callback function for the stream.
        Will run as long as there is audio data to play.
        """
        
        if self._time_encode:
            # get time
            tobj = datetime.datetime.utcnow()
            tobj -= datetime.timedelta(
                seconds=time.currentTime - time.inputBufferAdcTime
            )
            tstr = tobj.strftime(soft_time_fmt)
            dat_len = indata.shape[0]
            # make new column for array
            tcode = np.empty((dat_len, 1), dtype=indata.dtype)
            # check for floating point types
            if np.issubdtype(indata.dtype, np.floating):
                # scale 8 bit char values to full range
                scale = 1 / (255.0)
            else:
                scale = 1
            # check if timecode can fit in our chunk
            if dat_len >= len(tstr):
                for i in range(len(tstr)):
                    tcode[i] = ord(tstr[i]) * scale
                tcode[len(tstr) :] = 0
            else:
                tcode.fill(0xFF)
            # queue values
            self._qr.put_nowait(np.hstack((indata, tcode)))
        else:
            # Record the output
            self._qr.put_nowait(indata.copy())

        if status.output_underflow:
            print("Output underflow: increase blocksize?", file=sys.stderr)
            raise sd.CallbackStop
        assert not status
        try:
            data = self._qpb.get_nowait()
        except queue.Empty:
            print("Buffer is empty: increase buffersize?", file=sys.stderr)
            raise sd.CallbackStop

        if data.shape[0] < outdata.shape[0]:
            outdata[: data.shape[0], self._playback_map] = data
            outdata[: data.shape[0], self._playback_silent] = 0
            outdata[data.shape[0] :, :] = 0
            raise sd.CallbackStop
        else:
            outdata[:, self._playback_map] = data
            outdata[:, self._playback_silent] = 0

    def _cb_rec(self, indata, frames, time, status):
        """
        Callback function for the stream.
        Will run as long as there is audio data to play.
        """

        if status:
            print(status, file=sys.stderr, flush=True)

        if self._time_encode:
            # get time
            tobj = datetime.datetime.utcnow()
            tobj -= datetime.timedelta(
                seconds=time.currentTime - time.inputBufferAdcTime
            )
            tstr = tobj.strftime(soft_time_fmt)
            dat_len = indata.shape[0]
            # make new column for array
            tcode = np.empty((dat_len, 1), dtype=indata.dtype)
            # check for floating point types
            if np.issubdtype(indata.dtype, np.floating):
                # scale 8 bit char values to full range
                scale = 1 / (255.0)
            else:
                scale = 1
            # check if timecode can fit in our chunk
            if dat_len >= len(tstr):
                for i in range(len(tstr)):
                    tcode[i] = ord(tstr[i]) * scale
                tcode[len(tstr) :] = 0
            else:
                tcode.fill(0xFF)
            # queue values
            self._qr.put_nowait(np.hstack((indata, tcode)))
        else:
            self._qr.put(indata.copy())
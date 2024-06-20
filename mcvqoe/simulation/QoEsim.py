import mcvqoe.base
import os.path
import sys
import warnings

import numpy as np

from mcvqoe.delay.ITS_delay import active_speech_level

try:
    # try to import importlib.metadata
    from importlib.metadata import entry_points
except ModuleNotFoundError:
    # fall back to importlib_metadata
    from importlib_metadata import entry_points


def _get_entry_points(group):
    if sys.version_info >= (3, 10):
        # use new selection mechanism
        return entry_points(group=group)
    else:
        # use the old way
        return entry_points()[group]


class QoEsim:
    """
    Class to use for simulations.

    This class simulates the functionalities of mcvqoe.hardware.AudioPlayer and
    mcvqoe.hardware.RadioInterface.

    Parameters
    ----------
    port : str, default=None
        For compatibility with 'RadioInterface'. Value has no effect on simulation.

    Attributes
    ----------
    debug : bool, default=False
        If true, print some extra 'RadioInterface' things.
    sample_rate : int, default=48000
        Sample rate of audio in/out in samples per second.
    blocksize : int, default=512
        For compatibility with 'AudioPlayer'. Value has no effect on simulation.
    buffersize : int, default=20
        For compatibility with 'AudioPlayer'. Value has no effect on simulation.
    overplay : float, default =1.0
        The number of seconds of extra audio to play/record at the end of a clip.
    device : str, default=__class__
        Device name for compatibility with 'AudioPlayer'. This is set to the
        string representation of the class instance by default. Changing has no
        effect on simulations.
    port_name : str, default='SIM'
        Serial port name. For compatibility with RadioInterface, changing has no
        effect on simulations.
    rec_chans : dict
        Dictionary describing the recording. Dictionary keys must be one of
        {'rx_voice','PTT_signal'. For simulation, the value is ignored, as this
        normally represents the physical channel number. At this time QoEsim can not
        simulate 'timecode' or 'tx_beep' audio.
    playback_chans : dict
        Dictionary describing the playback channels. Dictionary keys should be
        one of {'tx_voice','start_signal'}. For simulation, the value is ignored,
        as this normally represents the physical channel number.
    channel_tech : string, default='clean'
        Technology to use for the simulated channel. Must match the name of an
        installed channel plugin.
    channel_rate : int or str, default=None
        Rate to simulate channel at. Each channel tech handles this differently.
        When set to None the default rate is used.
    pre_impairment : function, default=None
        Impairment function to apply before the audio goes through the channel.
        This function is passed an audio vector and should return a audio vector,
        of the same length, with the impairments applied. A value of None skips
        applying an impairment.
    post_impairment : function, default=None
        Impairment function to apply after the audio goes through the channel.
        This function is passed an audio vector and should return a audio vector,
        of the same length, with the impairments applied. A value of None skips
        applying an impairment.
    channel_impairment : function, default=None
        Impairment to apply to the channel data. Callback function that is called
        on the channel data to simulate a less than perfect communication channel.
        A value of none skips applying an impairment.
    m2e_latency : float, default=None
        Simulated mouth to ear latency for the channel in seconds. If none than
        the minimum latency for the technology is used. Can be set to a callable
        object to return a different value each time.
    access_delay : float, default=0
        Delay between the time that the simulated push to talk button is pushed
        and when audio starts coming through the channel. If the 'ptt_delay'
        method is called before play_record is called, then the time given to
        'ptt_delay' is added to access_delay to get the time when access is
        granted. Otherwise access is granted 'access_delay' seconds after the
        clip starts. Can be set to a callable object to return a different value
        each time.
    device_delay : float, default=0
        Delay of simulated audio interface. This is added to m2e_latency and is
        the delay for the PTT signal. Can be set to a callable object to return
        a different value each time.
    rec_snr : float, default=60
        Signal to noise ratio, in dB, for audio channel.
    print_args : bool, default=False
        Print arguments to external programs.
    PTT_sig_freq : float, default=409.6
        Frequency of the PTT signal from the play_record method.
    PTT_sig_amplitude : float, default=0.7
        Amplitude of the PTT signal from the play_record method.
    default_radio : int, default=1
        For compatibility with RadioInterface, the number of the radio to use
        when none is given. Doesn't really have an effect on simulation, but the
        ptt_wait_delay is tracked for each radio.
    allow_all_rec : bool, default=False
        Accept all recording channels, even if we don't know how to generate
        data for them. If an unexpected channel is found, it will be filled with
        random data. This is useful for basic functionality tests for two
        location.

    See Also
    --------
    mcvqoe.hardware.AudioPlayer : Play audio on real hardware.
    mcvqoe.hardware.RadioInterface : Key real radios.

    Examples
    --------
    Play 48 kHz audio stored in tx_voice and record in a file named 'test.wav'.
    note: "F1_harvard_phrases.wav" is found in the mouth2ear 'audio_clips' folder.

    >>> import mcvqoe.simulation.QoEsim
    >>> import mcvqoe.base.misc
    >>> rate, tx_voice = mcvqoe.base.audio_read("F1_harvard_phrases.wav")
    >>> sim_obj = mcvqoe.simulation.QoEsim(fs=int(48e3))
    >>> sim_obj.play_record(tx_voice, 'test.wav')

    Now do the same but also output the start signal on channel 1 and record the
    PTT signal on channel 1.

    >>> import mcvqoe.simulation.QoEsim
    >>> import mcvqoe.base.misc
    >>> rate, tx_voice = mcvqoe.base.audio_read("F1_harvard_phrases.wav")
    >>> sim_obj = mcvqoe.simulation.QoEsim(fs=int(48e3))
    >>> sim_obj.playback_chans = {'tx_voice':0, 'start_signal':1}
    >>> sim_obj.rec_chans = {'rx_voice':0, 'PTT_signal':1}
    >>> sim_obj.play_record(tx_voice, 'test.wav')
    """

    def __init__(
        self,
        port=None,
        **kwargs
    ):

        # values for RadioInterface
        #NOTE : port, is added as an argument for compatibility, but is not used.
        self.debug = False
        self.PTT_state = [
            False,
        ] * 2
        self.LED_state = [
            False,
        ] * 2
        self.ptt_wait_delay = [
            -1.0,
        ] * 2
        # values for AudioPlayer
        self.sample_rate = int(48e3)
        self.blocksize = 512
        self.buffersize = 20
        self.overplay = 1.0
        self.device = str(__class__)  # fake device name
        self.port_name = 'SIM'   # fake serial port
        self.rec_chans = {"rx_voice": 0}
        self.playback_chans = {"tx_voice": 0}
        # channel variables
        self.channel_tech = "clean"
        self.channel_rate = None
        self.pre_impairment = None
        self.post_impairment = None
        self.channel_impairment = None
        # set to none to get min delay
        self.m2e_latency = None
        self.access_delay = 0
        self.device_delay = 0
        # SNR for audio in dB
        self.rec_snr = 60
        # print arguments sent to external programs for debugging
        self.print_args = False
        # PTT signal parameters
        self.PTT_sig_freq = 409.6  # TODO : VERIFY!
        self.PTT_sig_amplitude = 0.7
        self.default_radio = 1

        # allow any channel type to be recorded, fill with random data, if needed
        self.allow_all_rec = False

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

    def __repr__(self):
        string_props = ('sample_rate','overplay','rec_chans','playback_chans',
                        'channel_tech','channel_rate','m2e_latency','access_delay',
                        'device_delay','rec_snr')
        
        string_opt_props = ('pre_impairment','post_impairment','channel_impairment')

        props = []

        for prop in string_props:
            props.append(f'{prop} = {repr(getattr(self, prop))}')
        for prop in string_opt_props:
            if getattr(self, prop) is not None:
                props.append(f'{prop} = {repr(getattr(self, prop))}')

        return f'{type(self).__name__}({", ".join(props)})'

    def __enter__(self):

        return self

    def ptt(self, state, num=None):
        """
        Change the push-to-talk status of the radio interface.

        For 'RadioInterface' this would turn on or off the PTT outputs. For simulation,
        This function does not have much of an effect. It will clear any PTT time set by
        the 'ptt_delay' method.

        Parameters
        ----------
        state : bool
            State to set PTT output to.
        num : int, default=None
            PTT output number to use. If None, self.default_radio is used.

        See Also
        --------
        mcvqoe.hardware.RadioInterface.ptt : Same function but, for hardware.

        Examples
        --------
        Key a fake radio.

        >>> import mcvqoe.simulation.QoEsim
        >>> sim_obj = mcvqoe.simulation.QoEsim()
        >>> sim_obj.ptt(True)  # key radio
        >>> sim_obj.ptt(False) # de-key radio
        """

        if num is None:
            num = self.default_radio

        self.PTT_state[num] = bool(state)
        # clear wait delay
        self.ptt_wait_delay[num] = -1

    def led(self, num, state):
        """
        Turn on and off fake LEDs.

        For 'RadioInterface' this would turn on or off LEDs on the device. For simulation
        this function doesn't do much.

        Parameters
        ----------
        num : int
            LED number to set.
        state : bool
            The LED state to set. True is on, False is off.

        See Also
        --------
        mcvqoe.hardware.RadioInterface.led : Same function but, for hardware.

        Examples
        --------
        Turn on some fake LEDs.

        >>> import mcvqoe.simulation.QoEsim
        >>> sim_obj = mcvqoe.simulation.QoEsim()
        >>> sim_obj.led(1, True)
        >>> sim_obj.led(2, True)
        >>> sim_obj.led(1, False)
        """

        # check LED state
        if state:
            if self.debug:
                print("RadioInterface LED {%num} state is on")
        else:
            if self.debug:
                print("RadioInterface LED {%num} state is off")

        # set state in simulation object
        self.LED_state[num-1] = bool(state)

    def devtype(self):
        """
        Get the devicetype string from the fake radio interface.

        For 'RadioInterface' this would query the firmware version of the board.
        For simulation, this just returns a version string.

        Returns
        -------
        str
            A string pretending to come from a 'RadioInterface' board.

        See Also
        --------
        mcvqoe.hardware.RadioInterface.devtype : Same function but, for hardware.

        Examples
        --------
        Query a fake 'RadioInterface'.

        >>> import mcvqoe.simulation.QoEsim
        >>> sim_obj = mcvqoe.simulation.QoEsim()
        >>> print(sim_obj.devtype())
        """

        # TODO : simulate other versions??
        return "MCV radio interface : v1.2.1"

    def get_id(self):
        """
        Get the ID string from radio interface.

        For 'RadioInterface' this would query the firmware version of the board.
        For simulation, this just returns the filename.

        Returns
        -------
        str
            A string pretending to come from a 'RadioInterface' board.

        See Also
        --------
        mcvqoe.hardware.RadioInterface.get_id : Same function but, for hardware.

        Examples
        --------
        Query a fake 'RadioInterface'.
        
        >>> import mcvqoe.simulation.QoEsim
        >>> sim_obj = mcvqoe.simulation.QoEsim()
        >>> print(sim_obj.get_id())
        """

        return os.path.basename(__file__)

    def get_version(self):
        """
        Get the version string from fake 'RadioInterface'.

        For 'RadioInterface' this would query the firmware version of the board.
        For simulation, this just returns the mcvqoe library version.

        Returns
        -------
        str
            A string pretending to come from a 'RadioInterface' board.

        See Also
        --------
        mcvqoe.hardware.RadioInterface.get_version : Same function but, for hardware.

        Examples
        --------
        Query a fake 'RadioInterface'.

        >>> import mcvqoe.simulation.QoEsim
        >>> sim_obj = mcvqoe.simulation.QoEsim()
        >>> print(sim_obj.get_version())
        """

        return mcvqoe.base.version

    def pttState(self):
        """
        Get the PTT state from fake 'RadioInterface'.

        Return the state of the simulated PTT outputs.

        Returns
        -------
        bool array
            An array with the status of each simulated PTT output.

        See Also
        --------
        mcvqoe.hardware.RadioInterface.pttState : Same function but, for hardware.

        Examples
        --------
        Query a fake 'RadioInterface'.

        >>> import mcvqoe.simulation.QoEsim
        >>> sim_obj = mcvqoe.simulation.QoEsim()
        >>> print(sim_obj.pttState())
        >>> sim_obj.ptt(True)
        >>> print(sim_obj.pttState())
        """
        
        return self.PTT_state

    def waitState(self):
        """
        Get the PTT wait state from fake 'RadioInterface'.

        For 'RadioInterface' this would check if PTT outputs were waiting for a
        start signal. For simulation this always returns 'Idle'

        Returns
        -------
        str
            This function always returns 'Idle'.

        See Also
        --------
        mcvqoe.hardware.RadioInterface.waitState : Same function but, for hardware.

        Examples
        --------
        Query a fake 'RadioInterface'.

        >>> import mcvqoe.simulation.QoEsim
        >>> sim_obj = mcvqoe.simulation.QoEsim()
        >>> print(sim_obj.waitState())
        """

        # TODO: do we need to simulate this better?
        return "Idle"

    def ptt_delay(self, delay, num=None, use_signal=False):
        """
        Set how far into the clip to key the fake radio.

        For 'RadioInterface' this would setup the PTT output to key up with a
        specified delay. For simulation, this sets the time in the clip that
        'access_delay' is referenced to.

        Parameters
        ----------
        delay : float
            The number of seconds between the start of the clip and when the
            'access_delay' time starts counting.
        num : int, default=None
            The PTT output to use. If None, use self.default_radio.
        use_signal : bool, default=False
            For 'RadioInterface', this would control if the start signal is used
            to reference the 'delay' to the beginning of the clip. For simulation
            'delay' is always referenced to the beginning of the clip.

        See Also
        --------
        mcvqoe.hardware.RadioInterface.ptt_delay : Same function but, for hardware.
        mcvqoe.simulation.QoEsim.play_record : Where 'delay' times are used.

        Examples
        --------
        Generate a simulated clip where the radio is keyed up 1 second into the
        clip. 'tx_voice' has the 48k Hz voice vector. The result is stored in
        'test.wav'

        >>> import mcvqoe.simulation.QoEsim
        >>> sim_obj = mcvqoe.simulation.QoEsim(fs=int(48e3))
        >>> sim_obj.playback_chans = {'tx_voice':0, 'start_signal':1}
        >>> sim_obj.rec_chans = {'rx_voice':0, 'PTT_signal':1}
        >>> sim_obj.ptt_delay(1)
        >>> sim_obj.play_record(tx_voice, 'test.wav')
        """

        if num is None:
            num = self.default_radio

        self.ptt_wait_delay[num] = delay
        # set state to true, this isn't 100% correct but the delay will be used
        # for the sim so, it shouldn't matter
        self.PTT_state[num] = True

    def temp(self):
        """
        Read fake temperatures from fake hardware.

        For 'RadioInterface' this would read temperature from the microcontroller.
        For simulation, this returns some fake values.
        NOTE : the current hardware no longer supports temperature measurements,
        this may be removed in the future.

        Returns
        -------
        int array
            Two integers representing the internal temperature and external
            temperature.

        See Also
        --------
        mcvqoe.hardware.RadioInterface.temp : Same function but, for hardware.

        Examples
        --------
        Read some fake temperatures.

        >>> import mcvqoe.simulation.QoEsim
        >>> sim_obj = mcvqoe.simulation.QoEsim()
        >>> print(sim_obj.temp())
        """
        
        # TODO : generate better fake values??
        return (38, 1500)

    # delete method
    def __del__(self):
        # nothing to do here
        pass

    def __exit__(self, exc_type, exc_value, exc_traceback):

        self.ptt(False)
        self.led(1, False)

    # =====================[Find device function]=====================
    @staticmethod
    def find_device(device_str="UMC"):
        """
        Return fake device name.

        For 'AudioPlayer' this would return the name of the audio device to use.
        For simulation this just returns the string representation of the class.

        Arguments
        ---------
        device_str : str, default="UMC"
            For compatibility with AudioPlayer. For hardware this would look for
            device matching this. For simulations, it does nothing.

        Returns
        -------
        str
            The string representation of the class instance.

        See Also
        --------
        mcvqoe.hardware.AudioPlayer.find_device : Same function but for hardware.

        Examples
        --------
        Query a fake 'AudioPlayer'.

        >>> import mcvqoe.simulation.QoEsim
        >>> sim_obj = mcvqoe.simulation.QoEsim()
        >>> print(sim_obj.find_device())
        """
        
        return str(__class__)

    # =====================[Get Channel Technologies]=====================
    @staticmethod
    def get_channel_techs():
        """
        Return a list of channel technologies.

        This returns a list of the channel technologies that have been found.
        These can be used as values for the `channel_tech` property.

        Returns
        -------
        list of strings
            A list of the names of channel technologies.

        See Also
        --------
        mcvqoe.simulation.QoEsim.channel_tech : Channel technology to use.
        mcvqoe.simulation.QoEsim.play_record : Function to simulate a channel.

        Examples
        --------

        List channel technologies.

        >>> import mcvqoe.simulation.QoEsim as QoEsim
        >>> QoEsim.get_channel_techs()
        ('amr-nb', 'amr-wb', 'analog', 'clean', 'p25')
        """
        
        chan_types = []
        for c in _get_entry_points("mcvqoe.channel"):
            chan_types.append(c.name)

        return tuple(chan_types)

    # =====================[Get Channel Rates]=====================
    @staticmethod
    def get_channel_rates(tech):
        """
        Return possible rates for a given channel tech.

        This queries a channel plugin for the default rate and a list of unique
        rates that can be used on the channel.

        Returns
        -------
        default_rate : string or number
            Default rate for channel, if no rate is used, None is returned.
        rates : list
            A list of the names of channel technologies. If no rate is used, an
            empty list is returned.

        See Also
        --------
        mcvqoe.simulation.QoEsim.get_channel_techs : List of channel technologies.
        mcvqoe.simulation.QoEsim.channel_tech : Channel technology to use.
        mcvqoe.simulation.QoEsim.play_record : Function to simulate a channel.

        Examples
        --------
        Get rates for a clean channel

        >>> import mcvqoe.simulation.QoEsim as QoEsim
        >>> QoEsim.get_channel_techs('clean')
        (None, [])
        """
        
        mod = QoEsim._get_chan_mod(tech)
        return (mod.default_rate, mod.rates)

    # =====================[Get Channel Version]=====================
    @staticmethod
    def get_channel_version(tech):
        """
        Return version string for channel tech.

        This queries a channel plugin for the installed version.

        Returns
        -------
        string
            Channel version string.

        See Also
        --------
        mcvqoe.simulation.QoEsim.get_channel_techs : List of channel technologies.
        mcvqoe.simulation.QoEsim.channel_tech : Channel technology to use.
        mcvqoe.simulation.QoEsim.play_record : Function to simulate a channel.

        Examples
        --------
        Get version for a clean channel

        >>> import mcvqoe.simulation.QoEsim as QoEsim
        >>> QoEsim.get_channel_version('clean')
        <mcvqoe.base.version>
        """
        
        mod = QoEsim._get_chan_mod(tech)

        try:
            ver = mod.version
        except AttributeError:
            ver = 'Unknown'

        return ver

    # =====================[Get Channel Version]=====================
    @staticmethod
    def get_channel_type(tech):
        """
        Return channel type for channel tech.

        This queries a channel plugin for the channel type. Right now there are
        three defined channel types 'digital-channel', 'analog-channel' and
        'audio'.

        Digital channels should pass a boolean array to the channel impairment
        function. Where each element represents one bit in the stream.

        Analog channels should pass a floating point array to the channel
        impairment function. Where each element represents the voltage vs time in
        the channel.

        Audio channels are just audio channel data. Audio channels should pass a
        floating point array to the channel impairment function, where each
        sample represents voltage over time.

        Returns
        -------
        string
            Channel type string.

        See Also
        --------
        mcvqoe.simulation.QoEsim.get_channel_techs : List of channel technologies.
        mcvqoe.simulation.QoEsim.channel_tech : Channel technology to use.
        mcvqoe.simulation.QoEsim.play_record : Function to simulate a channel.

        Examples
        --------
        Get version for a clean channel

        >>> import mcvqoe.simulation.QoEsim as QoEsim
        >>> QoEsim.get_channel_type('clean')
        'audio'
        """
        
        mod = QoEsim._get_chan_mod(tech)

        try:
            chan_type = mod.channel_type
        except AttributeError:
            chan_type = 'Unknown'

        return chan_type
    
    # =====================[get channel module]=====================
    @staticmethod
    def _get_chan_mod(tech):
        """Get module for channel plugin."""

        chan_types = []
        # locate any channel plugins installed
        for c in _get_entry_points("mcvqoe.channel"):
            if c.name == tech:
                # load module and return
                return c.load()
            chan_types.append(c.name)
        # tech not found, raise error
        raise ValueError(f'Unknown channel tech "{tech}" valid channel technologies are {chan_types}')

    # =====================[get impairment plugins]=====================
    @staticmethod
    def _get_impairments():
        """
        Get installed impairments.

        Return a tuple of EntryPoint objects for the installed impairments.

        Returns
        -------
        tuple
            Tuple with one EntryPoint object for each impairment plugin.
        """
        
        # locate any impairment plugins installed
        return _get_entry_points("mcvqoe.impairment")

    # =========================[get impairment plugins]=========================
    def _get_impairment_module(name):
        """Get matching impairment module."""

        # locate any impairment plugins installed
        impairments = QoEsim._get_impairments()

        for i in impairments:
            if i.name == name:
                module = i.load()
                break
        else:
            raise ValueError(f'impairment name \'{name}\' is not installed')

        return module
    
    # =========================[get impairment plugins]=========================
    @staticmethod
    def get_impairment_names(plugin_type):
        """
        Return the names of all the impairments that match a given type.

        This imports all the impairment plugins, imports them and checks to see
        if their impairment type matches `plugin_type`.

        Parameters
        ----------
        plugin_type : str
            A string containing the plugin type to match. Should be one of :
            'Analog', 'Digital' or 'Audio'.

        Returns
        -------
        tuple
            A tuple containing the names of the plugins that match the given type.

        See Also
        --------
        mcvqoe.simulation.QoEsim.get_channel_type : Get the type of a channel.
        mcvqoe.simulation.QoEsim.get_channel_techs : List of channel technologies.
        mcvqoe.simulation.QoEsim.channel_tech : Channel technology to use.
        """

        # locate any impairment plugins installed
        impairments = QoEsim._get_impairments()

        names = []

        for i in impairments:
            #TODO : probably need a try in here somewhere
            # load module
            module = i.load()
            # check if type matches
            if plugin_type == module.impairment_type or 'generic' == module.impairment_type:
                names.append(i.name)

        return tuple(names)

    # =======================[get all impairment plugins]=======================
    @staticmethod
    def get_all_impairment_names():
        """
        Return the names of all the impairments that are installed.

        Returns
        -------
        tuple
            A tuple containing the names of the plugins that match the given type.

        See Also
        --------
        mcvqoe.simulation.QoEsim.get_impairment_names : Get matching impairments.
        """

        # locate any impairment plugins installed
        impairments = QoEsim._get_impairments()

        return tuple([i.name for i in impairments])

    # =======================[get impairment parameters]=======================
    @staticmethod
    def get_impairment_params(name):
        """
        Get the parameters for a given impairment.

        Returns a list containing an ImpairmentParam object for each impairment
        that the `create_impairment` function in the plugin takes.

        Returns
        -------
        list
            A list of ImpairmentParam objects describing the parameters.

        See Also
        --------
        mcvqoe.simulation.QoEsim.get_impairment_func : Create impairment function.
        """
        
        module = QoEsim._get_impairment_module(name)

        return module.parameters

    # =======================[get impairment Description]=======================
    @staticmethod
    def get_impairment_description(name):
        """
        Get the description from an impairment plugin.

        Parameters
        ----------
        name : str
            A string containing the impairment to get the description of.

        Returns
        -------
        str
            The description from the plugin.

        See Also
        --------
        mcvqoe.simulation.QoEsim.get_impairment_names : Get matching impairments.
        """
        
        module = QoEsim._get_impairment_module(name)

        return module.description

    # =======================[get impairment Version]=======================
    @staticmethod
    def get_impairment_version(name):
        """
        Get the version string of an impairment plugin

        Parameters
        ----------
        name : str
            A string containing the impairment to get the version of.

        Returns
        -------
        str
            The version string from the plugin.

        See Also
        --------
        mcvqoe.simulation.QoEsim.get_impairment_names : Get matching impairments.
        """

        module = QoEsim._get_impairment_module(name)

        try:
            ver = module.version
        except AttributeError:
            ver = 'Unknown'

        return ver

    # ========================[initialize an impairment]========================
    @staticmethod
    def get_impairment_func(name, **kwargs):
        """
        Return an impairment function.

        Return an impairment function for the named impairment with the given
        arguments. Possible keyword arguments are given by get_impairment_params.
        Arguments that are not given will have their default values used. Extra
        arguments that are given will be ignored.

        Parameters
        ----------
        name : str
            The plugin to create an impairment for.

        Returns
        -------
        object
            A callable object that can be used as an impairment for QoEsim.

        See Also
        --------
        mcvqoe.simulation.QoEsim.get_impairment_params : Get impairment parameters.
        """
        
        module = QoEsim._get_impairment_module(name)

        return module.create_impairment(**kwargs)

    # ========================[get delay value]========================
    def _get_delay_samples(self, value, name, offset=0):
        if value is None:
            delay_samples = 0
        elif callable(value):
            # correct for offset
            delay_samples = int((value() - offset) * self.sample_rate)
            # fix delay to zero
            if delay_samples<0:
                # give warning about change
                warnings.warn(f'{name} would be {delay_samples} samples, replacing with 0')
                # set to zero
                delay_samples = 0
        else:
            # correct for offset
            delay_samples = int((value - offset) * self.sample_rate)

        if delay_samples < 0:
            raise ValueError(
                f"Unable to simulate {name} of {value}. Minimum simulated {name} for technology '{self.channel_tech}' is {offset}"
            )

        return delay_samples
    
    # =========================[record audio function]=========================
    def play_record(self, audio, out_name):
        """
        Simulate playing and recording of audio through a communication channel.

        This function simulates a communication channel. The values in
        'self.playback_chans' are checked for valid values, but they don't really
        have any other effect. Only 'rech_chans' of type 'rx_voice' and
        'PTT_signal' can be used.

        Parameters
        ----------
        audio : array
            An array of audio data to pass through the communication channel.
        out_name : str
            The name of the output .wav file to write to.

        Returns
        -------
        list of strings
            A list of the recorded output channels in the order that they appear
            in the output file.

        See Also
        --------
        mcvqoe.hardware.AudioPlayer.play_record : Same function but for hardware.

        Examples
        --------
        Play 48 kHz audio stored in tx_voice and record in a file named 'test.wav'.
        note: "F1_harvard_phrases.wav" is found in the mouth2ear 'audio_clips' folder.

        >>> import mcvqoe.simulation.QoEsim
        >>> import mcvqoe.base.misc
        >>> rate, tx_voice = mcvqoe.base.audio_read("F1_harvard_phrases.wav")
        >>> sim_obj = mcvqoe.simulation.QoEsim(fs=int(48e3))
        >>> sim_obj.play_record(tx_voice, 'test.wav')

        Now do the same but also output the start signal on channel 1 and record
        the PTT signal on channel 1.

        >>> import mcvqoe.simulation.QoEsim
        >>> import mcvqoe.base.misc
        >>> rate, tx_voice = mcvqoe.base.audio_read("F1_harvard_phrases.wav")
        >>> sim_obj.playback_chans = {'tx_voice':0, 'start_signal':1}
        >>> sim_obj.rec_chans = {'rx_voice':0, 'PTT_signal':1}
        >>> sim_obj.play_record(tx_voice, 'test.wav')
        """
        
        # loop through playback_chans this is mostly just a format check to make
        # sure that all keys used are valid
        for (k, v) in self.playback_chans.items():
            if k == "start_signal":
                pass
            elif k == "tx_voice":
                pass
            else:
                raise ValueError(f"Unknown output channel : {k}")

        # list of outputs that we need to produce
        outputs = []
        # loop through rec_chans and detect keys that we can't produce
        for (k, v) in self.rec_chans.items():
            if k not in ("rx_voice", "PTT_signal"):
                if self.allow_all_rec:
                    warnings.warn(f"Got unexpected recording type : '{k}'")
                else:
                    raise RuntimeError(f"{__class__} can not generate recordings of type '{k}'")
            outputs.append(k)

        # get the module for the chosen channel tech
        chan_mod = self._get_chan_mod(self.channel_tech)

        # get delay offset for channel technology
        m2e_offset = chan_mod.standard_delay

        # calculate values in samples
        overplay_samples = int(self.overplay * self.sample_rate)

        # get value for device delay
        device_delay_samples = self._get_delay_samples(self.device_delay, 'device delay')

        # get value for M2E
        m2e_latency_samples = self._get_delay_samples(self.m2e_latency, 'M2E', offset=m2e_offset)

        # convert audio values to floats to work on them
        float_audio = mcvqoe.base.audio_float(audio)

        # append overplay to audio
        overplay_audio = np.zeros(int(overplay_samples), dtype=np.float32)
        tx_data_with_overplay = np.concatenate((float_audio, overplay_audio))


        # check if PTT was keyed during audio
        if self.ptt_wait_delay[self.default_radio] == -1:
            # PTT wait not set, don't simulate access time
            ptt_st_dly_samples = 0
            access_delay_samples = 0
        else:
            access_delay_samples = self._get_delay_samples(self.access_delay, 'Access Delay')
            ptt_st_dly_samples = int(self.ptt_wait_delay[self.default_radio] * self.sample_rate)

        # mute portion of tx_data that occurs prior to triggering of PTT
        muted_samples = int(access_delay_samples + ptt_st_dly_samples)
        muted_tx_data_with_overplay = tx_data_with_overplay[muted_samples:]

        # add pre channel impairments
        if self.pre_impairment:
            muted_tx_data_with_overplay = self.pre_impairment(
                muted_tx_data_with_overplay, self.sample_rate
            )

        if self.rec_snr is None:
            # don't add any noise
            muted_tx_data_with_overplay_and_noise = muted_tx_data_with_overplay
        else:
            # generate gaussian noise, of unit standard deviation
            noise = np.random.normal(0, 1, len(muted_tx_data_with_overplay)).astype(np.float32)

            # measure amplitude of signal and noise
            sig_level = active_speech_level(tx_data_with_overplay, self.sample_rate)
            noise_level = active_speech_level(noise, self.sample_rate)

            # calculate noise gain required to get desired SNR
            noise_gain = sig_level - (self.rec_snr + noise_level)

            # set noise to the correct level
            noise_scaled = noise * (10 ** (noise_gain / 20))

            # add noise to audio
            muted_tx_data_with_overplay_and_noise = muted_tx_data_with_overplay + noise_scaled

        # call audio channel function from module
        channel_voice = chan_mod.simulate_audio_channel(
            muted_tx_data_with_overplay_and_noise,
            self.sample_rate,
            self.channel_rate,
            self.print_args,
            self.channel_impairment,
        )

        # add post channel impairments
        if self.post_impairment:
            channel_voice = self.post_impairment(channel_voice, self.sample_rate)

        # generate silent noise section comprised of ptt_st_dly, access delay
        # and m2e latency audio snippets
        silence_length = int(ptt_st_dly_samples
                             + access_delay_samples
                             + m2e_latency_samples
                             + device_delay_samples)
        silent_section = np.zeros(silence_length)
        # prepend silent section to rx_data
        rx_voice = np.concatenate((silent_section, channel_voice))
        # Derive mean and standard deviation from real-world noise observed in
        # the audio recordings. This basically simulates the noise floor from
        # audio cables/audio interface that we always have when we record.
        mean = 0
        std = 1.81e-5
        rx_noise = np.random.normal(mean, std, len(rx_voice))
        # Add noise to rx voice
        rx_voice = rx_voice + rx_noise

        # force rx_data to be the same length as tx_data_with_overplay
        rx_voice = rx_voice[: tx_data_with_overplay.shape[0]]

        # output array is the length of rx_voice x number of outputs
        rx_data = np.empty((rx_voice.shape[0], len(outputs)))

        for n, o_type in enumerate(outputs):
            if o_type == "PTT_signal":
                # calculate PTT tone start time
                ptt_tone_st_samples = ptt_st_dly_samples + device_delay_samples
                # calculate length of sine signal in samples
                sin_len_samples = rx_data.shape[0] - ptt_tone_st_samples
                # construct sine signal
                rx_data[ptt_tone_st_samples:, n] = self.PTT_sig_amplitude * np.sin(
                    2
                    * np.pi
                    * self.PTT_sig_freq
                    * np.arange(sin_len_samples)
                    / float(self.sample_rate)
                )
                # zero out before PTT
                rx_data[:ptt_tone_st_samples, n] = 0
            elif o_type == "rx_voice":
                # add data to the array
                rx_data[:, n] = rx_voice
            # fallback if allow_all_rec is true
            elif self.allow_all_rec:
                # don't know how to generate this signal, fill with noise
                rx_data[:, n] = np.random.normal((rx_voice.shape[0],))
            else:
                raise RuntimeError("Internal error")

        # write out audio file
        mcvqoe.base.audio_write(out_name, int(self.sample_rate), rx_data)

        return outputs

    def record(self, filename):
        """
        Record audio based on rec_chans.

        There is no connection to the Tx side, so fixed length noise will be
        recorded.

        Parameters
        ----------
        filename : str
            The file name to write audio to.
        """

        if not self.allow_all_rec:
            raise RuntimeError("Data can not be generated for record.")

        samples = 10 * int(self.sample_rate)

        # generate data
        rx_data = np.random.normal((samples, len(self.rec_chans)))

        # write out audio file
        mcvqoe.base.audio_write(filename, int(self.sample_rate), rx_data)

        # return a tuple of channels
        return tuple(self.rec_chans.keys())

class ImpairmentParam:
    """Class for defining parameters to impairments."""
    
    def __init__(self, default, value_type, choice_type, **kwargs):
        self.default = default
        self.value_type = value_type
        self.choice_type = choice_type

        if self.choice_type == 'positive':
            self.max_val = np.inf
            self.min_val = 0.0 + kwargs['interval']

        # add kwargs
        for k, v in kwargs.items():
            # set attribute, don't care if it exists
            setattr(self, k, v)

class Impairment:
    """
    Class used to define impairments.

    This is a good base class to make impairments that will be logged correctly.
    """
    
    def __init__(self, **kwargs):
        self.arguments =  kwargs

    def __repr__(self):
        return f'{type(self).__name__}('+', '.join([f'{k}={repr(v)}' for k, v in self.arguments.items()])+')'

    def __call__(self, data, fs):
        return self.impairment(data, fs, **self.arguments)
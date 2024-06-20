import io
import math
import re

import serial
import serial.tools.list_ports

from warnings import warn


# Custom exception for commands
class CommandError(Exception):
    pass


class RadioInterface:
    """
    Class to talk to a radio interface board.
    
    Attributes
    ----------
    debug : bool, default=False
        If true, print extra info useful for debugging.
    default_radio : int, default=1

    See Also
    --------
    mcvqoe.simulation.QoEsim : Pretend to key fake radios.

    Examples
    --------
    Note that for these examples to work, you will need to have a radio interface
    plugged in.

    Create a radio interface object. This will search for a device on all serial
    ports on the machine.
    >>> ri = RadioInterface()

    Turn on an LED.
    >>> ri.led(1,'on')

    Key attached radio.
    >>> ri.ptt(True)

    Un-key attached radio.
    >>> ri.ptt(False)

    Turn off LED.
    >>> ri.led(1, 'off')

    If the serial port of the device is known it can be passed to the constructor.
    >>> ri = RadioInterface(port='COM12')
    
    """
    
    #USB PID/VID to use in search. Devices matching this PID/VID will be checked
    #This is a generic TI PID/VID that could get used by other things
    #TODO : do we want our own?
    _USB_VID = 0x2047 # RadioInterface Vendor ID (VID)
    _USB_PID = 0x0300 # RadioInterface Product ID (PID)

    def __init__(self, port=None, **kwargs):
        """
        Create a new RadioInterface object.

        to set class attributes, they can be specified with kwargs.

        Parameters
        ----------
        port : str, default=None
            Serial port to open to talk to radio interface hardware. If None is
            passed, all serial ports are searched for a device that seems to be
            connected to radio interface hardware. If a serial port string is
            given, it is used without sending any commands to it.
        """

        # set default values
        self.debug = False
        self.default_radio = 1

        # get properties from kwargs
        for k, v in kwargs.items():
            if hasattr(self, k):
                # None value means keep defaults
                if v is not None:
                    setattr(self, k, v)
            else:
                raise TypeError(f"{k} is not a valid keyword argument")

        if not port:
            ports = serial.tools.list_ports.comports()
            for p in ports:
                # check for matching PID/VID
                if(not (p.vid==self._USB_VID and p.pid==self._USB_PID)):
                    if self.debug:
                        print(f"Skipping {p.device}, PID/VID does not match")
                    # skip this device
                    continue
                try:
                    self._openPort(p.device)
                    # send device type command
                    dt = self.devtype()

                    if self.debug:
                        print(f"{p.device} Devtype : {dt}")

                    if dt.startswith("MCV radio interface"):
                        # port found, done
                        break
                    else:
                        # close serial port
                        self.sobj.close()
                except (CommandError, serial.SerialException, UnicodeDecodeError) as e:
                    if self.debug:
                        print(e)
            else:
                # port not found, give error
                raise RuntimeError("No radio interface found")
        else:
            # open port
            self._openPort(port)

    def __repr__(self):
        string_props=('default_radio',)

        if hasattr(self, "sobj"):
            # check if port is open
            if self.sobj:
                # get the currently open port
                props=[f'port = {repr(self.port_name)}']

                for prop in string_props:
                    props.append(f'{prop} = {repr(getattr(self, prop))}')

                return f'{type(self).__name__}({", ".join(props)})'

        # otherwise port is not open give some sort of an indication
        return f'<inactive {type(self).__name__}>'


    def __enter__(self):

        return self

    def ptt(self, state, num=None):
        """
        Change the push-to-talk status of the radio interface.

        This will send a command to the radio interface to immediately change the
        status of the chosen PTT output.

        Parameters
        ----------
        state : bool
            If state is true then the radio will be keyed (transmitting). If
            state is False then the radio will not be keyed (not transmitting).
        num : int, default=None
            PTT output number to use. If None, self.default_radio is used.

        See Also
        --------
        mcvqoe.hardware.RadioInterface.ptt_wait : Key radios after a delay.

        Examples
        --------

        Key the default radio.
        >>> ri.ptt(True)

        Un-key radio number 1.
        >>> ri.ptt(False, num=1)
        """

        if num is None:
            num = self.default_radio

        # check what the state is
        if state:
            # state is on
            state = "on"
        else:
            # state is off
            state = "off"

        # send command
        self._command(f"ptt {num} {state}")

    def led(self, num, state):
        """
        Turn on or off LED's on the radio interface board

        LED(num,state) changes the state of the LED given by num. If state is
        true turn the LED on if state is False turn the LED off
        """

        # determine LED state string
        if state:
            ststr = "on"
            if self.debug:
                print("state is on", flush=True)
        else:
            ststr = "off"
            if self.debug:
                print("state is off", flush=True)
        # send command
        self._command(f"LED {num} {ststr}")

    def devtype(self):
        """
        Get the devicetype string from the radio interface

        dt = DEVTYPE() where dt is the devicetype string
        """

        # flush input from buffer
        r = self.textin.readlines()
        if self.debug:
            print(f"flush: {r}")
        # send devtype command
        self._command("devtype")
        # get devtype line
        return self.textin.readline()

    def get_id(self):
        """Get the ID string from radio interface"""

        # Send ptt command with no arguments
        self._command("id")

        # Get response line
        ri_id = self.textin.readline()
        # Strip whitespace
        ri_id = ri_id.strip()

        return ri_id

    def get_version(self):
        """Get the version number from radio interface"""

        # Get devtype, this will have version
        devtype = self.devtype()
        parts = devtype.split(":")

        if len(parts) == 2:
            ver = parts[1]
            ver = ver.strip()
        else:
            ver = "old"
            warn("Unexpected devtype format, old RadioInterface firmware?")

        return ver

    def pttState(self):
        """
        Returns the pttState for a radioInterface object. This is called
        automatically when pttState is accessed.
        """

        # flush input from buffer

        # send ptt command with no arguments
        self._command("ptt")
        # get response line
        resp = self.textin.readline()
        # extract number of PTT outputs
        m = re.match("(?P<num>\d+) PTT outputs:", resp)
        # check for match
        if not m:
            raise RuntimeError(f"could not parse '{resp}'")
        # parse outputs
        num = int(m.group("num"))
        # preallocate value
        value = num * [None]
        # loop through all outputs
        for k in range(num):
            # get response line
            resp = self.textin.readline()
            # get state from response
            m = re.match("PTT(\d+) status : (?:(?P<on>on)|(?P<off>off))", resp)
            # check that state was parsed correctly
            if m:
                if m.group("on"):
                    value[k] = True
                elif m.group("off"):
                    value[k] = False
                else:
                    value[k] = None
            else:
                value[k] = None
            #if there was a problem, print response in debug mode
            if value[k] is None and self.debug:
                print(f'Could not parse line : \'{resp}\'')

        return value

    def waitState(self):
        """
        Returns the WaitState for a radioInterface object. This is called
        automatically when WaitState is accessed.
        """

        self._command("ptt state")
        # get response line
        resp = self.textin.readline()
        # parse PTT state
        m = re.match('PTT state : "(?P<state>.*?)"', resp)
        if m:
            return m.group("state")
        else:
            err_str = "Error : "
            if resp.startswith(err_str):
                raise RuntimeError(resp[len(err_str) :])
            else:
                raise RuntimeError(f"Unknown response '{resp}' received")

    def ptt_delay(self, delay, num=None, use_signal=False):
        """setup the radio interface to key the radio after a delay

        PTT_DELAY(dly) set the radio to be keyed in dly seconds.

        PTT_DELAY(dly, use_signal=True) set the radio to be keyed dly seconds
        after the start signal is detected.

        PTT_DELAY(dly, num=n, __) same as above but used key radio number n
        instead of the default radio

        delay = PTT_DELAY(dly, __) same as above but return the actual delay set on
        the microcontroller. This is different because of rounding and limits on
        the possible delay
        """

        if num is None:
            # No radio number given, use default
            num = self.default_radio

        # check which ptt command to use
        if use_signal:
            # delay is relative to signal
            delay_type = "Sdelay"
        else:
            # delay is relative to when command processed
            delay_type = "delay"

        # send ptt command with no arguments
        self._command(f"ptt {num} {delay_type} {delay}")
        # get response line
        resp = self.textin.readline()
        # get delay from string
        m = re.match(
            "(?:Error : (?P<err>.+)$)|(?:PTT in (?P<dly>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?) sec)",
            resp,
        )

        # check for match
        if not m:
            raise RuntimeError(f"Unable to parse esponse {resp}")

        # check PTT delay was found
        if m.group("dly"):
            return float(m.group("dly"))
        elif m.group("err"):
            raise RuntimeError(m.group("err"))
        else:
            # unable to parse error
            raise RuntimeError("Unknown Error")

    def temp(self):
        """
        Read value from temperature sensors

        [ext, int] = temp() - Returns the temperature measured by the thermistor
        external to the radiointerface or the temperature sensor built into the
        MSP430.
        """

        # send temp command
        self._command("temp")

        # get internal temp line
        intl = self.textin.readline()
        # get external temp line
        extl = self.textin.readline()

        # parse internal temperature
        m_int = re.match("int = (?P<temp>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?) C", intl)
        # check for match
        if m_int:
            # get temperature value
            t_int = float(m_int.group("temp"))
        else:
            raise RuntimeError(f"could not parse internal temperature from '{intl}'")
        # parse external temp value
        m_ext = re.match("ext = (?P<val>\d+)", extl)
        # check for match
        if m_ext:
            # get integer ADC value
            v_ext = int(m_ext.group("val"))
        else:
            raise RuntimeError(f"could not parse external temperature from '{extl}'")
        # B value of thermistor
        B = 3470
        # compute external temperature
        t_ext = (
            B / math.log(10e3 / ((2 ** 12 - 1) / v_ext - 1) / (10e3 * math.exp(-B / (273.15 + 25))))
            - 273.15
        )

        return (t_int, t_ext)

    # delete method
    def __del__(self):
        
        #check if we have a serial object
        if hasattr(self, "sobj"):
            # check if port is open
            if self.sobj:
                # closeout command, turn off LEDS and ptt
                self.sobj.write(b"closeout\n")

                # wait for all data to write out
                self.sobj.flush()

            # flush and close text wrapper
            self.textin.close()

    def __exit__(self, exc_type, exc_value, exc_traceback):

        # check if we have a serial object
        if hasattr(self, "sobj"):
            # check if we had a serial problem
            if (not exc_type) or "serial" not in exc_type.__name__.lower():
                self._command("closeout")
            else:
                print("Problem with serial port detected, no cleanup performed")

    def _openPort(self, port):

        self.sobj = serial.Serial(port, timeout=0.5)
        # buffer serial data
        self.textin = io.TextIOWrapper(io.BufferedReader(self.sobj))

        #save the name of the open port so it can be used later
        self.port_name = port

    def _command(self, cmd):
        """low level command function to send command to the MSP430"""

        # trim extraneous white space from command
        cmd = cmd.strip()

        if self.debug:
            print(f"sending '{cmd}'")

        # assemble string and encode to bytes
        cmd_b = (cmd + "\n").encode("utf-8")
        # send command
        self.sobj.write(cmd_b)

        # line buffer
        l = ""

        # maximum number of iterations
        mi = 3

        # check command responses for echo
        while cmd not in l:
            # get response
            l = self.textin.readline()

            # strip whitespace
            l = l.strip()

            if self.debug and l:
                print(f"received '{l}'")

            # subtract one from count
            mi -= 1
            # check if we should timeout
            if mi <= 0:
                # throw error
                raise CommandError("Command response timeout")
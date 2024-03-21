import warnings

#version info
from ..base.version import version

"""
Channel plugin for a clean channel with no impairments.

The clean channel plugin is the only one included with mcvqoe. It serves both as
a reference channel and as an example channel plugin for writing custom channel
plugins.

Attributes
----------
standard_delay: float
    The standard_delay attribute gives the delay that is added by the channel.
    This is used by QoEsim to compensate for the delay added by the channel and
    simulate the specified delay.
rates : list
    List of unique rates that can be used on the channel. This list should
    contain a list of possible rates. If there are multiple values that are
    accepted for a given rate, the one that is the most human readable should be
    chosen.
default_rate : str or number
    Default rate to use for channel. This should be one of the rates from
    `rates`.
"""

# plugin for clean channel

# No channel, no delay
standard_delay = 0

# no channel, no rate
default_rate = None
rates = []

channel_type = 'audio'

def simulate_audio_channel(
    tx_data, sample_rate, channel_rate=None, print_args=False, channel_impairment=None
):
    if channel_impairment:
        # apply impairment
        tx_data = channel_impairment(tx_data, sample_rate)
    if channel_rate:
        warnings.warn("For 'clean' there is no rate. 'channel_rate' option ignored")

    return tx_data
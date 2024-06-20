import scipy.signal
import sounddevice as sd
from fractions import Fraction
import mcvqoe.base
import tempfile
import pkgutil
import io
import os
import time


def single_play(ri, ap, audio_file=None, playback=False, ptt_wait=0.68, save_name=None):
    """
    Play an audio clip through a PTT system once.

    This function plays audio using the given RadioInterface and AudioPlayer
    objects. The output can, optionally, be played back to the user when
    complete

    Parameters
    ----------
    ri : RadioInterface
        Interface to talk to radio PTT.
    ap : AudioPlayer
        Audio player to play audio with.
    audio_file : str, default=None
        Audio file to use for test. if None, use default audio.
    playback : bool, default=False
        If true, play the audio after the trial is complete.
    ptt_wait : float, default=0.68
        Amount of time to wait, in seconds, between PTT and playback.
    """

    if audio_file is None:
        audio_file = io.BytesIO(pkgutil.get_data("mcvqoe.audio_clips", "test.wav"))

    # get fs from audio player
    fs = ap.sample_rate

    # Gather audio data in numpy array and audio sample rate
    fs_file, audio_dat = mcvqoe.base.audio_read(audio_file)
    # Calculate resample factors
    rs_factor = Fraction(fs / fs_file)
    # Resample audio
    audio = scipy.signal.resample_poly(
        audio_dat, rs_factor.numerator, rs_factor.denominator
    )

    with tempfile.TemporaryDirectory() as tmp_dir:

        if save_name:
            # save in user specified location
            rec_file = save_name
        else:
            # set filename of recording
            rec_file = os.path.join(tmp_dir, "test.wav")

        # request access to channel
        ri.ptt(True)
        # pause for access
        time.sleep(ptt_wait)
        # play audio
        ap.play_record(audio, rec_file)
        # release channel
        ri.ptt(False)

        if playback:
            # read in file
            fs_rec, rec_dat = mcvqoe.base.audio_read(rec_file)
            # check if we have multiple channels
            if len(rec_dat.shape) > 1:
                # drop all but the first channel
                # this will drop the PTT tone if used and not blow eardrums
                rec_dat = rec_dat[:, 0]
            # set sample rate
            sd.default.samplerate = fs_rec
            # play audio over the default device
            sd.play(rec_dat)


# main function
def main():
    # need a couple of extra things for this to work
    # import them here
    import argparse
    import mcvqoe.hardware

    # -----------------------[Setup ArgumentParser object]-----------------------

    parser = argparse.ArgumentParser(description="Simple program to key radios")
    parser.add_argument(
        "-t",
        "--time",
        type=float,
        default=10,
        metavar="T",
        help="Time to key radio for in seconds",
    )
    parser.add_argument(
        "-r",
        "--radioport",
        default="",
        metavar="PORT",
        help="Port to use for radio interface. Defaults to the "
        + "first port where a radio interface is detected",
    )
    parser.add_argument(
        "-a", "--audio-file", default="", metavar="F", help="audio file to play"
    )
    parser.add_argument(
        "-p",
        "--overPlay",
        type=float,
        default=1,
        metavar="DUR",
        help="The number of seconds to play silence after the "
        + "audio is complete. This allows for all of the audio "
        + "to be recorded when there is delay in the system",
    )
    parser.add_argument(
        "-w",
        "--PTT-wait",
        type=float,
        default=0.68,
        metavar="T",
        dest="ptt_wait",
        help="Time to wait between pushing PTT and playing audio",
    )
    parser.add_argument(
        "-P",
        "--playback",
        default=False,
        action="store_true",
        help="Playback audio after it is recorded",
    )
    parser.add_argument(
        "-o", "--output", default=None, type=str,
        help="If given, the recorded audio will be saved into the filename provided." +
        "This filename must have a .wav extension and must not point to an existing file."
    )

    # -----------------------------[Parse arguments]-----------------------------

    args = parser.parse_args()

    # -----------------------------[set audio file]-----------------------------

    if args.audio_file:
        # load the file that was given
        f = args.audio_file
    else:
        # no audio given, use default
        f = None

    # ---------------------------[Create AudioPlayer]---------------------------

    ap = mcvqoe.hardware.AudioPlayer()

    # ---------------------------[Open RadioInterface]---------------------------

    with mcvqoe.hardware.RadioInterface(args.radioport) as ri:

        print(f"RadioInterface opened successfully on {ri.port_name}!")

        # --------------------------------[Key radio]--------------------------------

        print(f"Playing audio")

        single_play(
            ri,
            ap,
            audio_file=f,
            ptt_wait=args.ptt_wait,
            playback=args.playback,
            save_name=args.output,
        )

    print("Complete")


if __name__ == "__main__":
    main()
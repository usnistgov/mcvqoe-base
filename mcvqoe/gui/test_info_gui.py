import datetime
import os
import sys
import tkinter as tk
from tkinter import scrolledtext

import pkg_resources


# This class and entire file was an early implementation of the GUI.
# Basically we just collect the pre/post notes and have the user input parameters.
# This code is no longer utilized.
class TestInfoGui(tk.Tk):
    """
    Class to show a gui to get information on a test.

    This class shows a GUI where the user can input parameters for a test. The
    test info defaults are logged to a file so that, when running multiple
    similar tests, some time can be saved.

    Attributes
    ----------
    defaults_file : str, default="test-type.txt"
        the file where defaults will be read/stored
    chk_audio_function : function, default=None
        The function to call when the check audio button is pressed. If this is
        None, no check audio button is used.
    outdir : str, default=''
        directory to write defaults_file in
    write_test_info : bool
        if true defaults will be written to the `defaults_file` after submit is
        pressed in the GUI. otherwise no notes will be written.
    info_in : dict
        Dictionary of info that will be used for GUI defaults
    test_info : dict
        Dictionary of info from the user, containing test info.

    See Also
    --------
    post_test : Connivance function for TestInfoGui.
    PostTestGui : GUI for post test notes.

    Examples
    --------
    get test notes from the user

    >>> gui = TestInfoGui()
    >>> test_info = gui.show()
    >>> print(test_info)
    """

    def __init__(
        self,
        defaults_file="test-type.txt",
        chk_audio_function=None,
        outdir="",
        write_test_info=True,
        *args,
        **kwargs,
    ):
        tk.Tk.__init__(self, *args, **kwargs)
        """
        Class to show a gui to get information on a test.

        Parameters
        ----------
        defaults_file : str, default="test-type.txt"
            the file where defaults will be read/stored
        chk_audio_function : function, default=None
            The function to call when the check audio button is pressed. If this is
            None, no check audio button is used.
        outdir : str, default=''
            directory to write defaults_file in
        write_test_info : bool, default=True
            if true defaults will be written to the `defaults_file` after submit is
            pressed in the GUI. otherwise no notes will be written.
        """

        self.defaults_name = os.path.join(outdir, defaults_file)
        self.load_settings(self.defaults_name)
        self.chk_audio_function = chk_audio_function
        self.write_test_info = write_test_info

        # Show MCV logo
        img_file = pkg_resources.resource_filename("mcvqoe.gui", "MCV-sm.png")
        self.tk.call("wm", "iconphoto", self._w, tk.PhotoImage(file=img_file))

    def load_settings(self, fname):
        """
        Load test info defaults from a file.

        Parameters
        ----------
        fname : str
            Full path of the file to read.
        """
        
        self.info_in = {}

        if fname:
            # --------------------[Obtain Previous Test info]--------------------
            try:
                with open(fname, "r") as prev_test:
                    self.info_in["test_type"] = prev_test.readline().split('"')[1]
                    self.info_in["tx_dev"] = prev_test.readline().split('"')[1]
                    self.info_in["rx_dev"] = prev_test.readline().split('"')[1]
                    self.info_in["system"] = prev_test.readline().split('"')[1]
                    self.info_in["test_loc"] = prev_test.readline().split('"')[1]
            except FileNotFoundError:
                self.info_in["test_type"] = ""
                self.info_in["tx_dev"] = ""
                self.info_in["rx_dev"] = ""
                self.info_in["system"] = ""
                self.info_in["test_loc"] = ""
            # dummy value for pre test notes, not saved in file
            self.info_in["Pre Test Notes"] = ""

    def show(self):
        """
        Populate window and wait for user input.

        Returns
        -------
        dict
            Dictionary with "Post Test Notes" or "Error Notes".
        """
        
        # Window creation
        self.title("Test Information")

        # End the program if the window is exited out
        self.protocol("WM_DELETE_WINDOW", self._cancel_action)

        # Test type prompt
        l1 = tk.Label(self, text="Test Type")
        l1.grid(row=0, column=0, padx=10, pady=5, sticky=tk.W)

        self.test_type_edit = tk.Entry(self, bd=2, width=50)
        self.test_type_edit.insert(tk.END, "")
        self.test_type_edit.insert(0, self.info_in["test_type"])
        self.test_type_edit.grid(row=1, column=0, padx=10, pady=5, sticky=tk.W)
        self.test_type_edit.focus()

        # Transmit device prompt
        l2 = tk.Label(self, text="Transmit Device")
        l2.grid(row=2, column=0, padx=10, pady=5, sticky=tk.W)
        self.tx_dev_edit = tk.Entry(self, bd=2)
        self.tx_dev_edit.insert(0, self.info_in["tx_dev"])
        self.tx_dev_edit.grid(row=3, column=0, padx=10, pady=5, sticky=tk.W)

        # Receive device prompt
        l3 = tk.Label(self, text="Receive Device")
        l3.grid(row=4, column=0, padx=10, pady=5, sticky=tk.W)
        self.rx_dev_edit = tk.Entry(self, bd=2)
        self.rx_dev_edit.insert(0, self.info_in["rx_dev"])
        self.rx_dev_edit.grid(row=5, column=0, padx=10, pady=5, sticky=tk.W)

        # System prompt
        l4 = tk.Label(self, text="System")
        l4.grid(row=6, column=0, padx=10, pady=5, sticky=tk.W)
        self.system_edit = tk.Entry(self, bd=2, width=60)
        self.system_edit.insert(0, self.info_in["system"])
        self.system_edit.grid(row=7, column=0, padx=10, pady=5, sticky=tk.W)

        # Test location prompt
        l5 = tk.Label(self, text="Test Location")
        l5.grid(row=8, column=0, padx=10, pady=5, sticky=tk.W)

        self.test_loc_edit = tk.Entry(self, bd=2, width=100)
        self.test_loc_edit.insert(0, self.info_in["test_loc"])
        self.test_loc_edit.grid(row=9, column=0, padx=10, pady=5, sticky=tk.W)

        # Pre-test notes prompt
        l6 = tk.Label(self, text="Please enter notes on pre-test conditions")
        l6.grid(row=10, column=0, padx=10, pady=5, sticky=tk.W)
        self.pre_notes_edit = scrolledtext.ScrolledText(self, bd=2, width=100, height=15)
        self.pre_notes_edit.insert(tk.INSERT, self.info_in["Pre Test Notes"])
        self.pre_notes_edit.grid(row=11, column=0, padx=10, pady=5, sticky=tk.W)

        # 'Submit', 'Test', and 'Cancel' buttons
        button_frame = tk.Frame(self)
        button_frame.grid(row=12, column=1, sticky=tk.E)

        exit_frame = tk.Frame(self)
        exit_frame.grid(row=12, column=0, sticky=tk.W)

        if self.chk_audio_function is not None:
            button = tk.Button(exit_frame, text="Check Audio", command=self.chk_audio_function)
            button.grid(row=0, column=0, padx=10, pady=10)

        button = tk.Button(button_frame, text="Submit", command=self._submit_action)
        button.grid(row=0, column=0, padx=10, pady=10)

        button = tk.Button(button_frame, text="Cancel", command=self._cancel_action)
        button.grid(row=0, column=1, padx=10, pady=10)

        # Run Tkinter window
        self.mainloop()

        if self.test_info is not None and self.defaults_name is not None and self.write_test_info:
            # --------------------[Print Test Type and Test Notes]----------------------

            # Print info to screen
            print("\nTest type: %s\n" % self.test_info["Test Type"], flush=True)
            print("Pre test notes:\n%s" % self.test_info["Pre Test Notes"], flush=True)

            # Write info to .txt file
            with open(self.defaults_name, "w") as file:
                file.write('Test Type : "%s"\n' % self.test_info["Test Type"])
                file.write('Tx Device : "%s"\n' % self.test_info["Tx Device"])
                file.write('Rx Device : "%s"\n' % self.test_info["Rx Device"])
                file.write('System    : "%s"\n' % self.test_info["System"])
                file.write('Test Loc  : "%s"\n' % self.test_info["Test Loc"])

        # can't seem to find documentation on this but, it fixes the following:
        # Tcl_AsyncDelete: async handler deleted by the wrong thread
        self.quit()

        return self.test_info

    def _submit_action(self):
        """Collect user input from Tkinter input window."""
        
        self.test_info = {
            "Test Type": self.test_type_edit.get(),
            "Tx Device": self.tx_dev_edit.get(),
            "Rx Device": self.rx_dev_edit.get(),
            "System": self.system_edit.get(),
            "Test Loc": self.test_loc_edit.get(),
            "Pre Test Notes": self.pre_notes_edit.get(1.0, tk.END),
        }
        # Delete window
        self.destroy()

    def _cancel_action(self):

        # signal cancel by setting test_info to None
        self.test_info = None

        self.destroy()


class PostTestGui(tk.Tk):
    """
    Class to show a gui to get notes after a test is complete.

    This class is used to show a GUI to the user on completion of a test to get
    any information about how the test went. If an error has been encountered
    during the test this is displayed in the gui and "Error Notes" are collected.
    Otherwise "Post Test Notes" are collected.

    Attributes
    ----------
    err : Exception
        If an exception is being handled, the exception, otherwise None.

    See Also
    --------
    post_test : Convenience function for PostTestGui.
    TestInfoGui : GUI to gather test info.

    Examples
    --------
    Get post test notes from user

    >>> gui = PostTestGui()
    >>> notes = gui.show()
    >>> print(notes)
    """

    def __init__(self, err, *args, **kwargs):
        """
        Class to show a gui to get notes after a test is complete

        Parameters
        ----------
        err :
            If an exception is being handled, the exception, otherwise None.
        """

        tk.Tk.__init__(self, *args, **kwargs)

        # error info, this will be used for the user prompt and to determine what
        # kind of notes we will create
        self.err = err

        # Show MCV logo
        img_file = pkg_resources.resource_filename("mcvqoe.gui", "MCV-sm.png")
        self.tk.call("wm", "iconphoto", self._w, tk.PhotoImage(file=img_file))

    def show(self):
        """
        Populate window and wait for user input.

        Returns
        -------
        dict
            Dictionary with "Post Test Notes" or "Error Notes".
        """

        # ------------------------------[Setup GUI]------------------------------

        self.title("Test Information")
        self.after(1, self.focus_force())

        # Prevent error if user exits
        self.protocol("WM_DELETE_WINDOW", self._collect_notes)

        # Pre-test notes prompt
        if self.err:
            label = tk.Label(
                self,
                text=f'An "{self.err.__name__}" was encountered. Please enter notes on test conditions',
            )
        else:
            label = tk.Label(self, text="Please enter post-test notes")
        label.grid(row=0, column=0, padx=10, pady=5, sticky=tk.W)

        self.notes_edit = scrolledtext.ScrolledText(self, bd=2, width=100, height=15)
        self.notes_edit.grid(row=1, column=0, padx=10, pady=5)
        self.notes_edit.focus()

        # 'Submit' and 'Cancel' buttons
        button_frame = tk.Frame(self)
        button_frame.grid(row=2, column=0, sticky=tk.E)

        button = tk.Button(button_frame, text="Submit", command=self._collect_notes)
        button.grid(row=0, column=0, padx=10, pady=10)

        button = tk.Button(button_frame, text="Cancel", command=self._cancel_action)
        button.grid(row=0, column=1, padx=10, pady=10)

        # Run Tkinter window
        self.mainloop()

        # can't seem to find documentation on this but, it fixes the following:
        # Tcl_AsyncDelete: async handler deleted by the wrong thread
        self.quit()

        if self.err:
            return {"Error Notes": self.notes}
        else:
            return {"Post Test Notes": self.notes}

    def _collect_notes(self):
        """Collect user's post-test notes."""

        self.notes = self.notes_edit.get(1.0, tk.END)

        # Delete window
        self.destroy()

    def _cancel_action(self):
        """
        Helper function for when cancel is pressed.
        """

        # set notes to empty
        self.notes = ""
        # destroy window
        self.destroy()


def post_test(error_only=False):
    """
    Convenience function for PostTestGui.

    This function creates a PostTestGui, calls the show method and returns the
    info dict.

    Parameters
    ----------
    error_only : bool, default=False
        If true will only show a dialog if an error occurred.

    Returns
    -------
    dict
        Dictionary with "Post Test Notes" or "Error Notes".
    """

    # get current error status, will be None if we are not handling an error
    error = sys.exc_info()[0]

    # check if there is no error and we should only show on error
    if (not error) and error_only:
        # nothing to do, bye!
        return {}

    # make a gui object
    gui = PostTestGui(error)

    # show things and return notes
    return gui.show()


def pretest(outdir="", check_function=None):
    """
    Convenience function for TestInfoGui.

    This function creates a TestInfoGui, calls the show method and returns test
    info. If no test info is given this function will call sys.exit.

    Parameters
    ----------
    outdir : str
        The directory to write test defaults to.
    check_function : function
        Function to call to check audio.

    Returns
    -------
    dict
        A dictionary of test info.
    """
    gui = TestInfoGui(chk_audio_function=check_function)

    test_info = gui.show()

    # check if the user canceled
    if test_info is None:
        print(f"\n\tExited by user")
        sys.exit(1)

    return test_info
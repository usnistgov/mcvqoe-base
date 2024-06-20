import glob
import os
import re
import shutil
import stat
import subprocess
import tempfile
import warnings

from datetime import datetime


# This hasn't been used in a long time, or updated since changes were made to
# our file structure, file logging, and file naming conventions. Most likely
# doesn't work and would need considerable tweaking to get running.
class log_search:
    """
    Class to parse and search MCV QoE log files

    The log_search class can read a single log file or a folder with multiple
    log files, addendum and group files.

    Attributes
    ----------
    fixedFields : list of strings
        The fixedFields static property is a list of fields that addendum files
        are not allowed to change
    found : set
        list of indicies matching the last search
    log : list of dicts
        the log attribute holds all of the parsed info from log files
    searchPath : string

    updateMode : {'Replace','AND','OR','XOR'}
        dictates how found is updated
    stringSearchMode : {'AND','OR','XOR'}
        dictates how string searches are performed
    foundCleared

    fieldNames : set
        a set of all the fieldnames that exist across all log entries
    """

    fixedFields = [
        "error",
        "complete",
        "operation",
        "GitHash",
        "logFile",
        "amendedBy",
        "date",
        "Arguments",
        "filename",
        "InputFile",
        "OutputFile",
    ]

    # Not hashable
    __hash__ = None

    def __init__(self, fname, addendumName=[], LogParseAction="Warn", groupName=[]):

        self.found = set()
        self.log = []
        self.searchPath = ""
        self.updateMode = "Replace"
        self.stringSearchMode = "OR"
        self.foundCleared = True
        self.fieldNames = set()
        self.groups = set()
        self.group_files = dict()

        if LogParseAction == "Warn":
            msgFcn = lambda m: warnings.warn(RuntimeWarning(m), stacklevel=3)
        elif LogParseAction == "Error":

            def errMsg(e):
                raise RuntimeError(e)

            msgFcn = errMsg
        elif LogParseAction == "Ignore":

            def noMsg(m):
                pass

            msgFcn = noMsg
        else:
            raise ValueError(f"invalid value '{LogParseAction}' for LogParseAction")

        if os.path.isdir(fname):
            # set searchpath to folder
            self.searchPath = fname

            # list log files in folder
            filenames = glob.glob(os.path.join(fname, "*.log"))

            # create full paths
            filenames = [os.path.join(fname, n) for n in filenames]

            # look for addendum files
            adnames = glob.glob(os.path.join(fname, "*.ad-log"))

            # check if we found any files
            if adnames:
                adnames[:] = [os.path.join(fname, n) for n in adnames]

            # look for group files
            groupnames = glob.glob(os.path.join(fname, "*.gr-log"))

            # check if we found any files
            if groupnames:
                groupnames[:] = [os.path.join(fname, n) for n in groupnames]

        else:

            (self.searchPath, _) = os.path.split(fname)

            # filenames is fname
            filenames = (fname,)

            if addendumName:
                adnames = (addendumName,)
            else:
                adnames = ()

            if groupName:
                groupnames = (groupName,)
            else:
                groupnames = ()

        # initialize idx
        idx = -1
        
        # -------------------------[Parse log files]----------------------------
        
        for fn in filenames:
            with open(fn, "r") as f:

                # create filename without path
                (_, short_name) = os.path.split(fn)

                # init status
                status = "searching"

                for lc, line in enumerate(f):

                    # strip newlines from line
                    line = line.strip("\r\n")

                    if line.startswith(">>"):
                        if not status == "searching":
                            msgFcn(
                                f"Start of packet found at line {lc} of {short_name} while in {status} mode"
                            )

                        # start of entry found, now we will parse the preamble
                        status = "preamble-st"

                    if status == "searching":
                        pass
                    elif status == "preamble-st":

                        # advance index
                        idx += 1

                        # add new dictionary to list
                        self.log.append({})

                        # split string into date and operation
                        parts = line.strip().split(" at ")

                        # set date
                        self.log[idx]["date"] = datetime.strptime(parts[1], "%d-%b-%Y %H:%M:%S")

                        # operation is the first bit
                        op = parts[0]

                        # remove >>'s from the beginning
                        op = op[2:]

                        # remove trailing ' started'
                        if op.endswith(" started"):
                            op = op[: -len(" started")]

                        # set operation
                        self.log[idx]["operation"] = op

                        # flag entry as incomplete
                        self.log[idx]["complete"] = False

                        # initialize error flag
                        self.log[idx]["error"] = False

                        # set source file
                        self.log[idx]["logFile"] = short_name

                        # dummy field for amendments
                        self.log[idx]["amendedBy"] = ""

                        # initialize groups
                        self.log[idx]["groups"] = set()

                        # set status to preamble
                        status = "preamble"
                    elif status == "preamble":

                        # check that the first character is not tab
                        if line and (not line[0] == "\t"):
                            # check for three equal signs
                            if not line.startswith("==="):
                                msgFcn(
                                    f"Unknown sequence found in preamble at line {lc} of file {short_name} : {repr(line)}"
                                )
                                # drop back to search mode
                                status = "searching"
                            elif line.startswith("===End"):
                                # end of entry, go into search mode
                                status = "searching"
                                # mark entry as complete
                                self.log[idx]["complete"] = True
                            elif line == "===Pre-Test Notes===":
                                status = "pre-notes"
                                # create empty pre test notes field
                                self.log[idx]["pre_notes"] = ""
                            elif line == "===Post-Test Notes===":
                                status = "post-notes"
                                # create empty post test notes field
                                self.log[idx]["post_notes"] = ""
                            else:
                                msgFcn(
                                    f"Unknown separator found in preamble at line {lc} of file {short_name} : {repr(line)}"
                                )
                                # drop back to search mode
                                status = "searching"
                        elif not line:
                            msgFcn(f"Empty line in preamble at line {lc} of file {short_name}")
                        else:
                            # split line on colon
                            lp = line.split(":")
                            # the MATLAB version uses genvarname but we just strip whitespace cause dict doesn't care
                            name = lp[0].strip()
                            # reconstruct the rest of line
                            arg = ":".join(lp[1:])

                            # check if key exists in dictionary
                            if name in self.log[idx].keys():
                                msgFcn(
                                    f"Duplicate field {name} found at line {lc} of file {short_name}"
                                )
                            else:
                                self.log[idx][name] = arg
                                # check for arguments
                                if name == "Arguments":
                                    self.log[idx]["_Arguments"] = self._argParse(arg)

                    elif status == "pre-notes":
                        # check that the first character is not tab
                        if line and line[0] == "\t":
                            # set sep based on if we have pre_notes
                            sep = "\n" if (self.log[idx]["pre_notes"]) else ""

                            # add in line, skip leading tab
                            self.log[idx]["pre_notes"] += sep + line.strip()
                        else:
                            # check for three equal signs
                            if not line.startswith("==="):
                                msgFcn(
                                    f"Unknown sequence found at line {lc} of file {short_name} : {repr(line)}"
                                )
                                # drop back to search mode
                                status = "searching"
                            elif line.startswith("===End"):
                                # end of entry, go into search mode
                                status = "searching"
                                # mark entry as complete
                                self.log[idx]["complete"] = True
                            else:
                                if line == "===Post-Test Notes===":
                                    status = "post-notes"
                                    # create empty post test notes field
                                    self.log[idx]["post_notes"] = ""
                                elif line == "===Test-Error Notes===":
                                    status = "post-notes"
                                    # create empty test error notes field
                                    self.log[idx]["error_notes"] = ""
                                    self.log[idx]["error"] = True
                                else:
                                    msgFcn(
                                        "Unknown separator found at line {lc} of file {short_name} : {repr(line)}"
                                    )
                                    # drop back to search mode
                                    status = "searching"

                    elif status == "post-notes":
                        # check that the first character is a tab
                        if line and line[0] == "\t":
                            field = "post_notes" if (not self.log[idx]["error"]) else "error_notes"

                            # set sep based on if we already have notes
                            sep = "" if (self.log[idx][field]) else "\n"

                            # add in line, skip leading tab
                            self.log[idx][field] += sep + line.strip()
                        else:
                            # check for three equal signs
                            if not line.startswith("==="):
                                msgFcn(
                                    f"Unknown sequence found at line {lc} of file {short_name} : {repr(line)}"
                                )
                                # drop back to search mode
                                status = "searching"
                            elif line.startswith("===End"):
                                # end of entry, go into search mode
                                status = "searching"
                                # mark entry as complete
                                self.log[idx]["complete"] = True
                            else:
                                msgFcn(
                                    f"Unknown separator found at line {lc} of file {short_name} : {repr(line)}"
                                )
                                # drop back to search mode
                                status = "searching"
                                
        # -------------------------[Parse addendum files]-----------------------
        
        for fn in adnames:
            with open(fn, "r") as f:

                # create filename without path
                (_, short_name) = os.path.split(fn)

                # init status
                status = "searching"

                for lc, line in enumerate(f):
                    # always check for start of entry
                    if line.startswith(">>"):
                        # check if we were in search mode
                        if not status == "searching":
                            # give error when start found out of sequence
                            raise ValueError(
                                f"Start of addendum found at line {lc} of file {short_name} while in {status} mode"
                            )

                        # start of entry found, now we will parse the preamble
                        status = "preamble-st"

                    if status == "searching":
                        pass
                    elif status == "preamble-st":

                        # split string into date and operation
                        parts = line.strip().split(" at ")

                        # set date
                        date = datetime.strptime(parts[1], "%d-%b-%Y %H:%M:%S")

                        # operation is the first bit
                        op = parts[0]

                        # remove >>'s from the beginning
                        op = op[2:]

                        # remove trailing ' started'
                        if op.endswith(" started"):
                            op = op[: -len(" started")]

                        # get index from _logMatch
                        idx = self._logMatch({"date": date, "operation": op})

                        if not idx:
                            raise ValueError(
                                f"no matching entry found for '{line.strip()}' from file {short_name}"
                            )
                        elif len(idx) > 1:
                            raise ValueError(
                                f"multiple matching entries found for '{line.strip()}' from file {short_name}"
                            )

                        # get index from set
                        idx = idx.pop()

                        # check if this log entry has been amended
                        if self.log[idx]["amendedBy"]:
                            # indicate which file amended this entry
                            self.log[idx]["amendedBy"] = short_name
                        else:
                            ValueError(f"log entry already amended at line {lc} of '{short_name}'")

                        # set status to preamble
                        status = "preamble"

                    elif status == "preamble":

                        # check that the first character is not tab
                        if line and not line[0] == "\t":
                            # check for end marker
                            if not line.startswith("<<"):
                                raise ValueError(
                                    f"Unknown sequence found in entry at line {lc} of file {short_name} : {line}"
                                )
                            else:
                                # end of entry, go into search mode
                                status = "searching"
                        else:
                            # split line on colon
                            lp = line.split(":")

                            # the MATLAB version uses genvarname but we just strip whitespace cause dict doesn't care
                            name = lp[0].strip()
                            # reconstruct the rest of line
                            arg = ":".join(lp[1:])

                            # check if field is amendable
                            if name in self.fixedFields:
                                raise ValueError(
                                    f"At line {lc} of file {short_name} : field '{name}' is not amendable"
                                )

                            # check if field exists in structure
                            if name in self.log[idx].keys():
                                self.log[idx][name] = arg
                            else:
                                raise ValueError(
                                    f"Invalid field {repr(name)} at line {lc} of {short_name}"
                                )
                                
        # -------------------------[Parse Group Files]-------------------------
        
        for fn in groupnames:
            with open(fn, "r") as f:

                # create filename without path
                (_, short_name) = os.path.split(fn)

                # Initialize dictionary for this file name
                self.group_files[short_name] = set()

                for lc, line in enumerate(f):
                    # remove whitespace
                    line = line.strip()

                    # check for blank lines
                    if not line:
                        continue

                    # check for comments
                    if line[0] == "#":
                        continue

                    parts = line.split(":")

                    groupNames = parts[0].strip().split(",")

                    members = ":".join(parts[1:]).split(",")

                    for ds in members:

                        # set date
                        date = datetime.strptime(ds.strip(), "%d-%b-%Y %H:%M:%S")

                        idx = self._logMatch({"date": date})

                        if not idx:
                            raise ValueError(
                                f"no matching entry found for '{line.strip()}' from file {short_name}"
                            )
                        elif len(idx) > 1:
                            raise ValueError(
                                f"multiple matching entries found for '{line.strip()}' from file {short_name}"
                            )

                        for groupName in groupNames:
                            # strip leading and trailing spaces
                            groupName = groupName.strip()
                            # concatenate filename and groupname
                            full_group_name = "{}:{}".format(short_name, groupName)
                            self.groups.add(full_group_name)
                            self.group_files[short_name].add(full_group_name)

                            self.log[list(idx)[0]]["groups"].add(full_group_name)

        for l in self.log:
            self.fieldNames.update(l.keys())

    def _logMatch(self, match):
        """Internal function to find matching log entries"""
        
        m = set()
        for n, x in enumerate(self.log):
            eq = [False] * len(match)
            for i, k in enumerate(match.keys()):
                if k == "date_before":
                    eq[i] = match[k] > x["date"]
                elif k == "date_after":
                    eq[i] = match[k] < x["date"]
                else:
                    try:
                        val = x[k]
                    except KeyError:
                        eq[i] = False
                        # done here, continue
                        continue
                    # check for strings and handle differently
                    if isinstance(val, str):
                        if isinstance(match[k], list):
                            str_eq = [(re.compile(s).search(val)) is not None for s in match[k]]
                            if self.stringSearchMode == "AND":
                                eq[i] = all(str_eq)
                            elif self.stringSearchMode == "OR":
                                eq[i] = any(str_eq)
                            elif self.stringSearchMode == "XOR":
                                # check if exactly one string matched
                                eq[i] = 1 == str_eq.count(True)
                        else:
                            eq[i] = re.compile(match[k]).search(val) is not None
                    elif isinstance(val, set):
                        if isinstance(match[k], set):
                            eq[i] = match[k].issubset(val)
                        else:
                            eq[i] = match[k] in val
                    else:
                        # fall back to equals comparison
                        eq[i] = val == match[k]
            if all(eq):
                m.add(n)
        return m

    def _foundUpdate(self, idx):
        """
        internal function to update the found attribute based on the update mode
        """
        
        # make idx a set
        idx = set(idx)
        
        if self.foundCleared:
            self.found = idx
        else:
            if self.updateMode == "Replace":
                self.found = idx
            elif self.updateMode == "AND":
                self.found &= idx
            elif self.updateMode == "OR":
                self.found |= idx
            elif self.updateMode == "XOR":
                self.found ^= idx
            else:
                raise ValueError(f"Unknown updateMode '{self.updateMode}'")
                
        # clear cleared
        self.foundCleared = False

    def Qsearch(self, search_field, search_term):
        """
        Quick search : search for a match in a single property

        Parameters
        ----------
        search_field : string
            The name of the field to search
        search_term
            the value that the search field values will be compared to

        Returns
        -------
        The set of matching indicies in self.log
        """

        # find matching entries
        idx = self._logMatch({search_field: search_term})

        # update found array
        self._foundUpdate(idx)

        return idx

    def MfSearch(self, search):
        """
        Multi field search : search for multiple matching fields

        Parameters
        ----------
        search : dict
            a dictionary where the keys are the fields to search and the values are
            the things to search for

        Returns
        -------
        The set of matching indicies in self.log
        """

        # search must be a dictionary
        if not isinstance(search, dict):
            raise ValueError("the search argument must be a dictionary")

        # search for matching log entries
        idx = self._logMatch(search)

        # update found array
        self._foundUpdate(idx)

        return idx

    def clear(self):
        """clear the found set"""
        
        # clear found
        self.found = set()
        self.foundCleared = True

    def datafilenames(self, ftype="csv", ignore_incomplete=False):
        """
        find data files matching a log entry

        Parameters
        ----------
        ftype : {'mat','csv','bad_csv','wav','sm_mat'}
            what type of files to look for
        """

        # name of test operations
        test_opps = ('Test', 'Intelligibility', 'PSuD', 'Access', 'M2E')

        types = re.compile(
            r"\.?(?P<csv>csv)|(?P<mat>mat)|(?P<wav>wav)|(?P<sm_mat>sm(?:all)?_mat)|(?P<bad_csv>bad_csv)",
            re.IGNORECASE,
        )

        m = types.match(ftype)

        if not m:
            raise ValueError(f"Unknown search type '{ftype}'")

        if m.group("mat"):
            # TODO: Should we delete this?
            tstFiles = {
                "ext": ".mat",
                "path": "data_matfiles",
                "singular": True,
                "exclude": "",
            }
        elif m.group("csv"):
            tstFiles = {
                "ext": ".csv",
                "path": os.path.join("data", "csv"),
                "singular": False,
                "exclude": "_BAD.csv",
            }
        elif m.group("bad_csv"):
            # TODO: where is this now?
            tstFiles = {
                "ext": "_BAD.csv",
                "path": os.path.join("post-processed data", "csv"),
                "singular": False,
                "exclude": None,
            }
        elif m.group("wav"):
            tstFiles = {
                "ext": "",
                "path": os.path.join("data", "wav"),
                "singular": True,
                "exclude": None,
            }
        elif m.group("sm_mat"):
            # TODO: Should we delete this?
            tstFiles = {
                "ext": ".mat",
                "path": os.path.join("post-processed data", "mat"),
                "singular": True,
                "exclude": None,
            }
        else:
            raise RuntimeError(f"'{ftype}' is an invalid file type")

        # filenames
        fn = []
        # file indexes
        fi = []
        for idx in self.found:
            if self.log[idx]["operation"] in test_opps:
                prefix = ["Rcapture_", "capture_"]
                folder = [tstFiles["path"]] * len(prefix)
                ext = tstFiles["ext"]
                singular = tstFiles["singular"]
                exclude = tstFiles["exclude"]
            elif self.log[idx]["operation"] == "Training":
                # TODO: Can we delete training? I think so...
                prefix = ["Training_"] * 2
                folder = ["training", "data"]
                ext = ".mat"
                singular = True
                exclude = None
            elif self.log[idx]["operation"] == "Tx Two Loc Test":
                # TODO: Does this need an update?
                prefix = ["Tx_capture", "capture"]
                folder = ["tx-data"] * len(prefix)
                ext = ".mat"
                singular = True
                exclude = None
            elif self.log[idx]["operation"] == "Rx Two Loc Test":
                # TODO: Does this need an update?
                prefix = ["Rx_capture", "capture"]
                folder = ["rx-data"] * len(prefix)
                ext = ".mat"
                singular = True
                exclude = None
            elif self.log[idx]["operation"].startswith("Copy"):
                fn.append(":None")
                fi.append(idx)
                continue
            else:
                raise ValueError(f"Unknown operation '{self.log[idx]['operation']}'")

            if (not ignore_incomplete) and (not self.log[idx]["complete"]):
                fn.append(":Incomplete")
                fi.append(idx)
                continue

            if self.log[idx]["error"]:
                fn.append(":Error")
                fi.append(idx)
                continue

            # get date string in file format
            date_str = self.log[idx]["date"].strftime("%d-%b-%Y_%H-%M-%S")

            for f, p in zip(folder, prefix):

                foldPath = os.path.join(self.searchPath, f)

                filenames = glob.glob(os.path.join(foldPath, p + "*" + ext))

                match = [
                    f for f in filenames if date_str in f and ((not exclude) or exclude not in f)
                ]

                if not singular and len(match) >= 1:
                    fn += match
                    fi.append([idx] * len(match))
                    break
                elif len(match) > 1:
                    print(f"More than one file found matching '{date_str}' in '{f}")
                    fn.append("Multiple")
                    fi.append(idx)
                elif len(match) == 1:
                    fn.append(match[0])
                    fi.append(idx)
                    break
            else:
                fn.append(None)
                fi.append(idx)
                warnings.warn(
                    RuntimeWarning(f"No matching files for '{date_str}' in '{foldPath}'"),
                    stacklevel=2,
                )

        return (fn, fi)

    def findFiles(self, locpath, ftype="csv"):
        """Get filenames from current log search object.

        Similar to datafilenames, but copies any found files that are in the
        network search path but missing from the local path into the local
        path.

        Parameters
        ----------
        locpath : string
            Local path for data storage. .
        ftype : string, optional
            File type for data to search for/copy. The default is 'csv'.

        Returns
        -------
        filenames : list
            List of filenames that match log search conditions.Filenames are
            guaranteed to exist locally.

        """

        network_path = self.searchPath

        #       self.searchPath = network_path
        net_names, net_ix = self.datafilenames(ftype)

        # Identify all sessions marked error on network
        net_errSessions = [name == ":Error" for name in net_names]

        # Identify all sessions marked Incomplete on network
        net_incSessions = [name == ":Incomplete" for name in net_names]

        # Identify all sessions that could not be identified on network
        net_notFound = [name == None for name in net_names]

        if any(net_notFound):
            warnings.warn(
                RuntimeWarning(f"'{sum(net_notFound)}' files not found on network"),
                stacklevel=2,
            )

        net_tossIx = [
            net_errSessions[i] or net_incSessions[i] or net_notFound[i]
            for i in range(0, len(net_names))
        ]
        # Toss unwanted sessions from net_names
        net_names_clean = [net_names[i] for i in range(0, len(net_names)) if (not (net_tossIx[i]))]

        if os.path.exists(os.path.join(locpath, "post-processed data", ftype)):
            # Check that path to data even exists

            # Switch to searching localpath
            self.searchPath = locpath
            loc_names, loc_ix = self.datafilenames(ftype)

            # Identify all sessions marked error/incomplete locally
            loc_errSessions = [name == ":Error" for name in loc_names]
            loc_incSessions = [name == ":Incomplete" for name in loc_names]
            loc_NoneSessions = [name == None for name in loc_names]
            loc_tossIx = [
                loc_NoneSessions[i] or loc_errSessions[i] or loc_incSessions[i]
                for i in range(0, len(loc_names))
            ]
            loc_names_clean = [
                loc_names[i] for i in range(0, len(loc_names)) if (not (loc_tossIx[i]))
            ]
        else:
            # Path to data does not exist at all locally
            # Set local names to be empty
            loc_names_clean = []

        #       # Grab just the basenames of each list
        loc_base = [os.path.basename(x) for x in loc_names_clean]
        net_base = [os.path.basename(x) for x in net_names_clean]

        # Transform into sets
        loc_set = set(loc_base)
        net_set = set(net_base)
        # Take set union of local and network names
        all_names = loc_set.union(net_set)
        # Identify names in network that are missing from local set
        non_localNames = all_names.difference(loc_set)

        for fname in non_localNames:
            _, fbase = os.path.split(fname)
            if ftype == "csv":
                subdir = os.path.join("post-processed data", "csv")
            elif ftype == "sm_mat":
                subdir = os.path.join("post-processed data", "mat")
            elif ftype == "wav":
                subdir = os.path.join("post-processed data", "wav")
            elif ftype == "mat":
                subdir = "data"
            else:
                raise RuntimeError(f"Unsupported ftype: '{ftype}' ")

            lpath = os.path.join(locpath, subdir)
            # Make directories if don't exist locally
            if not (os.path.exists(lpath)):
                os.makedirs(lpath)

            localpath = os.path.join(lpath, fname)
            netpath = os.path.join(network_path, subdir, fname)
            print(f"Copying from:\n -- {netpath}", flush=True)
            print(f"Copying to:\n -- {localpath}", flush=True)
            shutil.copy2(netpath, localpath)

        filenames, _ = self.datafilenames(ftype)

        f_errSessions = [name == ":Error" for name in filenames]
        f_incSessions = [name == ":Incomplete" for name in filenames]
        f_tossIx = [f_errSessions[i] or f_incSessions[i] for i in range(0, len(filenames))]
        filenames = [filenames[i] for i in range(0, len(filenames)) if (not (f_tossIx[i]))]

        if filenames == []:
            raise RuntimeError("Could not find any files meeting search criteria")
        self.searchPath = network_path
        return filenames

    def isAncestor(self, rev, repo_path, git_path=None):
        """
        Search for tests run with an ancestor of the given rev

        This searches the git hash field and can be used to find tests that have
        been run with code that is more recent than `rev`. This requires the
        repository that the tests were run using.

        Parameters
        ----------
        rev : string
            string that can be resolved, by git, to a commit. Possible values include
            branch names, tag names, and partial commit hashes
        repo_path : string
            this can either be a local path to the repository or a git URL. If
            it is a git URL the repository will be cloned and used for the search.
        git_path : string
            the path to the git executable

        Returns
        -------
        The set of matching indices in self.log
        """

        if git_path is None:
            git_path = "git"

        # dummy name in case it is not used
        tmpdir = None
        try:

            if isGitURL(repo_path):
                # save URL
                repo_url = repo_path
                # generate temp dir
                tmpdir = tempfile.TemporaryDirectory()
                # print message to inform the user
                print(f"Cloning : {repo_path}")
                # set repo path to temp dir
                repo_path = tmpdir.name
                # clone repo
                p = subprocess.run([git_path, "clone", repo_url, repo_path], capture_output=True)
                # check return code
                if p.returncode:
                    # TODO: error
                    raise RuntimeError(p.stderr)

            # get the full has of the commit described by rev
            p = subprocess.run(
                [git_path, "-C", repo_path, "rev-parse", "--verify", rev],
                capture_output=True,
            )
            # convert to string and trim whitespace
            rev_p = p.stdout.decode("utf-8").strip()
            # check for success
            if p.returncode:
                raise RuntimeError(f"Failed to parse rev : {rev_p}")

            match = set()

            hashCache = {}

            for k, l in enumerate(self.log):
                hash = l["Git Hash"].strip()

                if not hash:
                    # skip this one
                    continue

                # dump dty flag
                hash = hash.split()[0]

                if hash not in hashCache.keys():

                    # check that hash is valid
                    p = subprocess.run(
                        [git_path, "-C", repo_path, "cat-file", "-t", hash],
                        capture_output=True,
                    )

                    if p.returncode:
                        warnings.warn(
                            RuntimeWarning(
                                f"Could not get hash for {hash} {p.stderr.decode('utf-8').strip()}"
                            ),
                            stacklevel=2,
                        )
                        # store result in hash cache
                        hashCache[hash] = False
                        # skip this one
                        continue

                    p = subprocess.run(
                        [
                            git_path,
                            "-C",
                            repo_path,
                            "show-branch",
                            "--merge-base",
                            rev_p,
                            hash,
                        ],
                        capture_output=True,
                    )
                    # remove spaces from base
                    base = p.stdout.decode("utf-8").strip()
                    # check for errors
                    if p.returncode:
                        warnings.warn(
                            RuntimeWarning(
                                f"Could not get the status of log entry {k} git returned : {base}"
                            ),
                            stacklevel=2,
                        )

                    hashCache[hash] = base == rev_p

                if hashCache[hash]:
                    match.add(k)
        finally:
            if tmpdir:
                # must delete directory manually because of a bug in TemporaryDirectory
                # see https://bugs.python.org/issue26660
                # .git has read only files
                shutil.rmtree(os.path.join(tmpdir.name, ".git"), onerror=del_rw)
                # cleanup dir
                tmpdir.cleanup()

        self._foundUpdate(match)

        return match

    def argSearch(self, name, value):
        """
        search the arguments field of log entries

        Searches the arguments field for arguments that match the given name, value
        pair. Note : this has not been well tested with python, enjoy!

        Parameters
        ----------
        name : string
            the parameter name to search for
        value : string
            the parameter value to search for
        """

        def listCmp(l1, l2):

            m = [False] * len(l2)

            for a in l1:
                res = [valCmp(a, b) for b in l2]

                # make sure that there was a match
                if not any(res):
                    return False

                # OR lists together
                m = [a | b for a, b in zip(m, res)]

            return all(m)

        def valCmp(arg, val):
            if isinstance(arg, list) and isinstance(val, list):
                return listCmp(arg, val)
            elif isinstance(arg, list) and not isinstance(val, list):
                return listCmp(arg, [val])
            elif (not isinstance(arg, list)) and isinstance(val, list):
                return listCmp([arg], val)
            elif isinstance(arg, str):
                m = re.search(val, arg)
                return not not m
            else:
                return arg == val

        match = set()
        for i, l in enumerate(self.log):
            try:
                if valCmp(l["_Arguments"][name], value):
                    match.add(i)
            except KeyError:
                # argument not found, not a match
                pass

        self._foundUpdate(match)

        return match

    def _argParse(self, args):
        """
        internal function for parsing the arguments field

        This has not been well tested for python generated log files so, it may not
        work so well.
        """

        def str_or_float(val):
            if not val:
                return None
            m = re.match(r"(?P<str>'(?P<s>[^']*)')|(?P<true>true)|(?P<false>false)", val)
            if m:
                if m.group("str"):
                    return m.group("s")
                elif m.group("true"):
                    return True
                elif m.group("false"):
                    return False
                else:
                    raise RuntimeError("Internal Error")
            else:
                try:
                    return float(val)
                except ValueError:
                    warnings.warn(RuntimeWarning(f"Could not convert '{val}'"), stacklevel=2)
                    return val

        match_args = re.finditer(
            r"'(?P<name>[^']*)',(?P<value>(?P<cell_m>\{(?P<cell>[^}]*)\})|(?P<arr_m>\[(?P<arr>[^]]*)\])|(?:[^{[][^,]*))",
            args,
        )

        # dictionary for args
        arg_d = {}

        for m in match_args:
            # check for cell array
            if m.group("cell_m"):
                if m.group("cell"):
                    arg_d[m.group("name")] = [
                        str_or_float(v) for v in re.split(";|,", m.group("cell"))
                    ]
                else:
                    arg_d[m.group("name")] = []
            # check for a array
            elif m.group("arr_m"):
                if m.group("arr"):
                    arg_d[m.group("name")] = [
                        str_or_float(v) for v in re.split(";|,", m.group("arr"))
                    ]
                else:
                    arg_d[m.group("name")] = []
            else:
                arg_d[m.group("name")] = str_or_float(m.group("value"))

        return arg_d

    def argQuery(self, argName):
        """I really don't remember what this is for"""

        f_log = self.flog

        res = [None] * len(f_log)
        for i, entry in enumerate(f_log):
            res[i] = entry["_Arguments"][argName]

        return res

    def __len__(self):
        # return number of log entries
        return len(self.log)

    @property
    def flog(self):
        return [self.log[i] for i in self.found]


# workaround for deleting read only files
# code from : https://bugs.python.org/issue19643#msg208662
def del_rw(action, name, exc):
    """
    Workaround for deleting read only files with shutil.rmtree
    """
    os.chmod(name, stat.S_IWRITE)
    os.remove(name)

def isGitURL(str):
    """Detect if a url could be to a git repository"""
    
    if str.startswith("git@"):
        return True
    elif str.startswith("https://"):
        return True
    elif str.startswith("http://"):
        return True
    else:
        return False
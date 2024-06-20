import argparse
import json
import mcvqoe
import mcvqoe.base
import os
import pkg_resources
import pkgutil
import platform
import re
import shutil
import subprocess
import sys

from .sync import terminal_progress_update


# name for saved settings file
settings_name = "CopySettings.json"

if platform.system() == "Windows":

    def get_drive_serial(drive):
        # args for subprocess
        sp_args = {}
        # only for windows, prevent windows from appearing
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            sp_args['startupinfo'] = startupinfo
        # run vol command, seems that you need shell=True. Perhaps vol is not a real command?
        result = subprocess.run(
            f"vol {drive}", shell=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            **sp_args,
        )

        # check return code
        if result.returncode:
            info = result.stderr.decode("UTF-8")

            if "the device is not ready" in info.lower():
                raise RuntimeError("Device is not ready")
            else:
                raise RuntimeError(
                    f"Could not get volume info vol returned {result.returncode}"
                )

        # find drive serial number
        m = re.search(
            "^\W*Volume Serial Number is\W*(?P<ser>(?:\w+-?)+)",
            result.stdout.decode("UTF-8"),
            re.MULTILINE,
        )

        if m:
            return m.group("ser")
        else:
            raise RuntimeError("Serial number not found")

    def list_drives():
        # args for subprocess
        sp_args = {}
        # only for windows, prevent windows from appearing
        if os.name == 'nt':
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            sp_args['startupinfo'] = startupinfo

        result = subprocess.run(
            ["wmic", "logicaldisk", "get", "name"], stdout=subprocess.PIPE,
            **sp_args,
        )

        if result.returncode:
            raise RuntimeError("Unable to list drives")

        drive_table = []

        for line in result.stdout.decode("UTF-8").splitlines():
            # look for drive in line
            m = re.match("\A\s*(?P<drive>[A-Z]:)\s*$", line)
            # if there was a match
            if m:
                res = subprocess.run(
                    f'vol {m.group("drive")}',
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )

                if res.returncode:
                    info = res.stderr.decode("UTF-8")

                    if "the device is not ready" in info.lower():
                        # drive is not ready, skip
                        continue
                    elif "the network path was not found" in info.lower():
                        # network drive issue, skip
                        continue
                    else:
                        raise RuntimeError(
                            f'command returnd {res.returncode} for drive '
                            f'\'{m.group("drive")}\' \'{info}\''
                        )

                # find drive label
                m_label = re.search(
                    m.group("drive").rstrip(":")
                    + "\W*(?P<sep>\w+)\W*(?P<label>.*?)\W*$",
                    res.stdout.decode("UTF-8"),
                    re.MULTILINE,
                )

                if m_label:
                    # dictionary with serial and label
                    info = {"drive": line.strip()}
                    # check if we got a label
                    if m_label.groups("sep") == "is":
                        info["label"] = m_label.groups("label")
                    else:
                        info["label"] = ""

                    m_ser = re.search(
                        "^\W*Volume Serial Number is\W*(?P<ser>(?:\w+-?)+)",
                        res.stdout.decode("UTF-8"),
                        re.MULTILINE,
                    )

                    if m_ser:
                        info["serial"] = m_ser.group("ser")
                    else:
                        info["serial"] = ""

                    drive_table.append(info)

        return tuple(drive_table)


else:

    def list_drives():
        raise RuntimeError("Only Windows is supported at this time")

    def get_drive_serial(drive):
        raise RuntimeError("Only Windows is supported at this time")


def log_update(log_in_name, log_out_name, dryRun=False, progress_update=terminal_progress_update):
    with open(log_in_name, "rt") as fin:
        # will hold extra chars from input file
        # used to allow for partial line matches
        extra = ""
        if os.path.exists(log_out_name):
            with open(log_out_name, "rt") as fout:
                for line, (lin, lout) in enumerate(zip(fin, fout), start=1):
                    # check if the last match was not a full match
                    if extra:
                        raise RuntimeError(
                            f"At line {line}, last line was a partial match."
                        )
                    # check if lines are the same
                    if lin != lout:
                        # check if lout starts with lin
                        if lin.startswith(lout):
                            # get the chars in lout but not lin
                            extra = lin[len(lout) :]
                        else:
                            raise RuntimeError(
                                f"Files '{log_out_name}' and '{log_in_name}' differ at line {line}, can not copy"
                            )

                # get the remaining data in the file
                out_dat = fout.read()
        else:
            if not dryRun:
                # make sure that path to log file exists
                os.makedirs(os.path.dirname(log_out_name), exist_ok=True)
            # no in_dat
            in_dat = None

        # get remaining data in input file
        in_dat = fin.read()

        # strip trailing white space, add extra data
        in_dat = extra + in_dat.rstrip()

        # check if we have more data from the input file
        if in_dat:

            if not dryRun:
                # copy file to new location
                shutil.copy(log_in_name,log_out_name)

            progress_update('log-complete', 0, 0, lines=len(in_dat.splitlines()), file=log_out_name)
        else:
            if out_dat:
                raise RuntimeError("Input file is shorter than output")
            else:
                progress_update('log-complete', 0, 0, lines=0, file=log_out_name)

    # print success message
    #print(f"Log updated successfully to {log_out_name}\n")

def load_settings_file(file, match_drive=True):
    with open(file, "rt") as fp_set:
        set_dict = json.load(fp_set)

    if "Direct" not in set_dict:
        # default direct to False
        set_dict["Direct"] = False

    if set_dict["Direct"]:
        set_dict['prefix'] = ""
    else:

        # if we get a string for DriveSerial, make it a tuple
        if isinstance(set_dict["DriveSerial"], str):
            set_dict["DriveSerial"] = (set_dict["DriveSerial"], )
        else:
            # turn other things (ie. list) into a tuple
            set_dict["DriveSerial"] = tuple(set_dict["DriveSerial"])

        if match_drive:
            # get a list of connected storage devices
            drives = list_drives()

            matching_drives = [item for item in drives
                                    if item["serial"] in set_dict["DriveSerial"]]

            if not matching_drives:
                raise RuntimeError('Could not find drive with serial '
                                        f'in {set_dict["DriveSerial"]}')
            elif len(matching_drives) != 1:
                raise RuntimeError(f'Found {len(matching_drives)} '
                                    'matching drives. Please unplug all but one')

            # only one drive found, get info
            drive_info = matching_drives[0]

            # create drive prefix, add slash for path concatenation
            set_dict['prefix'] = drive_info["drive"] + os.sep

    return set_dict

def create_new_settings(direct, dest_dir, cname):
    if direct:
        prefix = ""
        rel_path = dest_dir
        drive_ser = None
    else:
        # split drive from path
        (prefix, rel_path) = os.path.splitdrive(dest_dir)

        # get serial number for drive
        drive_ser = get_drive_serial(prefix)

        # add slash for path concatenation
        prefix = prefix + os.sep

    # create dictionary of options, normalize paths
    set_dict = {
        "ComputerName": os.path.normpath(cname),
        "DriveSerial": (drive_ser, ),
        "Path": os.path.normpath(rel_path),
        "Direct": direct,
        "prefix": prefix,
    }

    return set_dict

def write_settings(set_dict, file):
    save_keys = ("ComputerName", "DriveSerial", "Path", "Direct")

    # filter dictionary to contain only the specified keys
    out_dict = {k : v for k, v in set_dict.items() if k in save_keys}

    # if we get a string for DriveSerial, make it a tuple
    if isinstance(out_dict["DriveSerial"], str):
        out_dict["DriveSerial"] = (out_dict["DriveSerial"], )

    # write out new dict
    json.dump(out_dict, file)

def add_drive(path, set_path):
    (prefix, rel_path) = os.path.splitdrive(path)

    if rel_path:
        # normalize rel_path to get rid of extra slashes
        rel_path = os.path.normpath(rel_path)

        if not rel_path and rel_path != os.path.sep:
            raise RuntimeError(f'Expected path to drive but got \'{path}\'')

    # load settings from file
    settings = load_settings_file(set_path, match_drive=False)

    if settings['Direct']:
        raise RuntimeError('Can not add a drive to a direct sync')

    # get serial number for the drive to add
    drive_ser = get_drive_serial(prefix)

    # get drives as a set
    drive_set = set(settings['DriveSerial'])

    # add drive serial
    drive_set.add(drive_ser)

    settings['DriveSerial'] = tuple(drive_set)

    # write new settings
    with open(set_path, 'w') as f:
        write_settings(settings, f)


def input_log_name(d):
    return os.path.join(d, "tests.log")

def output_log_name(set_dict):
    return os.path.join(
                        set_dict['prefix'],
                        set_dict["Path"],
                        set_dict["ComputerName"] + "-tests.log"
                    )

def update_sync(set_dict, sync_dir=None, dry_run=False, progress_update=terminal_progress_update):
    if sync_dir is None:
        sync_dir = os.path.join(set_dict['prefix'], "sync")

    SyncScript = os.path.join(sync_dir, "sync.py")
    sync_ver_path = os.path.join(sync_dir, "version.txt")

    sync_update = False

    if not os.path.exists(SyncScript):
        sync_update = True
        # print message
        progress_update('supdate-missing', 0, 2)

    if not sync_update:

        if os.path.exists(sync_ver_path):
            # read version from file
            with open(sync_ver_path, "r") as f:
                sync_ver = pkg_resources.parse_version(f.read())

            # get version from package
            qoe_ver = pkg_resources.parse_version(mcvqoe.base.version)

            # we need to update if sync version is older than mcvqoe version
            sync_update = qoe_ver > sync_ver

            if sync_update:
                progress_update('supdate-old', 0, 2)

        else:
            sync_update = True
            progress_update('supdate-vmissing', 0, 2)

    if sync_update and not dry_run:
        # there is no sync script
        # make sync dir
        os.makedirs(sync_dir, exist_ok=True)
        #update progress
        progress_update('supdate-write', 1, 2)
        # copy sync script
        with open(SyncScript, "wb") as f:
            f.write(pkgutil.get_data("mcvqoe.utilities", "sync.py"))

        with open(sync_ver_path, "w") as f:
            f.write(mcvqoe.base.version)
    else:
        progress_update('supdate-skip', 1, 2)

    return SyncScript

def run_drive_sync(script, out_dir, dest_dir, dry_run=False):
    # try to get path to python
    py_path = sys.executable

    if not py_path:
        # couldn't get path, try 'python' and hope for the best
        py_path = "python"

    syncCmd = [py_path, script, "--import", out_dir, dest_dir, "--cull"]

    if dry_run:
        print("Calling sync command:\n\t" + " ".join(syncCmd))
    else:
        stat = subprocess.run(syncCmd)

        if stat.returncode:
            raise RuntimeError(
                f"Failed to run sync script exit status {stat.returncode}"
            )

test_cpy_steps = {
                    'settings':'save settings',
                    'log':'copy log',
                    'supdate':'update sync',
                    'sync':'sync files',
                 }


def copy_test_files(out_dir, dest_dir=None, cname=None, sync_dir=None, dry_run=False,
                    force=False, direct=False, progress_update=None):

    if progress_update:
        force_lib_sync = True
    else:
        force_lib_sync = False
        progress_update=terminal_progress_update

    set_file = os.path.join(out_dir, settings_name)

    log_in_name = input_log_name(out_dir)

    num_steps = len(test_cpy_steps)

    for n, (step, name) in enumerate(test_cpy_steps.items()):

        progress_update('main-update', num_steps, n, step_name=name)

        if step == 'settings':
            if os.path.exists(set_file):

                set_dict = load_settings_file(set_file)

            else:
                if not cname:
                    raise RuntimeError(
                        f"--computer-name not given and '{set_file}' does not exist"
                    )

                if not dest_dir:
                    raise RuntimeError(f"--dest-dir not given and '{set_file}' does not exist")

                # TODO : check for questionable names in path?

                set_dict = create_new_settings(direct, dest_dir, cname)

            with (
                os.fdopen(os.dup(sys.stdout.fileno()), "w")
                if dry_run
                else open(set_file, "w")
            ) as sf:
                if dry_run:
                    print("Settings file:")
                write_settings(set_dict, sf)
        elif step == 'log':
            # file name for output log file
            log_out_name = output_log_name(set_dict)

            log_update(log_in_name, log_out_name, dry_run, progress_update=progress_update)

            # create destination path
            destDir = os.path.join(set_dict['prefix'], set_dict["Path"])

        elif step == 'supdate':
            if not set_dict["Direct"]:
                #update the sync script on the drive
                sync_script = update_sync(
                                            set_dict,
                                            sync_dir=sync_dir,
                                            dry_run=dry_run,
                                            progress_update=progress_update
                                          )
        elif step == 'sync':
            if not set_dict["Direct"] and not force_lib_sync:
                run_drive_sync(sync_script, out_dir, destDir, dry_run=dry_run)
            else:
                # direct sync, use library version
                from .sync import import_sync

                if dry_run:
                    print(
                        "Calling sync command:\n\t"
                        + f"sync.sync_files({repr(out_dir)}, {repr(destDir)}, bd=False, cull=True, sunset=30)"
                    )
                else:
                    import_sync(out_dir, destDir, bd=False, cull=True, sunset=30, progress_update=progress_update)

def recursive_sync(out_dir, dry_run=False, sync_dir=None, progress_update=None):
    # keep track of how many directories we found
    num_found = 0
    num_success = 0
    # check if progress update was given
    if progress_update is None:
        # use terminal function by default
        prog_fun = terminal_progress_update
    else:
        # use given function
        prog_fun = progress_update
    # get directory path
    out_dir = os.path.abspath(out_dir)
    for n, (root, dirs, files) in enumerate(os.walk(out_dir, topdown=True)):
        if dry_run:
            print(f'Checking "{root}" for "{settings_name}"')
        # check for copy settings
        if settings_name in files:
            num_found += 1
            prog_fun('recur-found', 0, n, dir=root)
            try:
                # settings found, copy files
                copy_test_files(root,dry_run=dry_run, sync_dir=sync_dir, progress_update=progress_update)
                # no error, this was a success
                num_success += 1
            except RuntimeError as e:
                # print error and continue
                prog_fun('recur-error', 0, n, err=str(e))
            # remove directories from dirs
            # this will skip all directories
            dirs.clear()
    # return stats
    return num_found, num_success

# main function
def main():
    parser = argparse.ArgumentParser(description=__doc__)
    
    parser.add_argument(
        "-d",
        "--dest-dir",
        default=None,
        type=str,
        metavar="DIR",
        dest="dest_dir",
        help="Path to store files on removable drive",
    )
    parser.add_argument(
        "-o",
        "--outdir",
        default="",
        metavar="DIR",
        help="Directory where test output data is stored",
    )
    parser.add_argument(
        "-c",
        "--computer-name",
        default=None,
        metavar="CNAME",
        dest="cname",
        help="computer name for log file renaming",
    )
    parser.add_argument(
        "-s",
        "--sync-directory",
        default=None,
        metavar="SZ",
        dest="sync_dir",
        help="Directory on drive where sync script is stored",
    )
    parser.add_argument(
        "-D",
        "--dry-run",
        action="store_true",
        default=False,
        dest="dry_run",
        help="Go through all the motions but, don't copy any files",
    )
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        default=False,
        help="overwrite config files with values from arguments",
    )
    parser.add_argument(
        "-i",
        "--direct",
        action="store_true",
        default=False,
        help="Copy directly to destination, not to a HD",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        default=False,
        help="Find copy settings recursively and sync where they are found",
    )

    # parse arguments
    args = parser.parse_args()

    if args.outdir:
        out_dir = os.getcwd()
    else:
        out_dir = args.outdir


    # convert to dict for use as kwargs
    args_dict = vars(args).copy()

    # remove some things
    args_dict.pop('outdir')
    args_dict.pop('recursive')

    if args.recursive:
        num_found, num_success = recursive_sync(out_dir, dry_run=args.dry_run, sync_dir=args.sync_dir)
        # check if we found any files
        if num_found:
            print(f'{num_found} test directories found, {num_success} successfully synced')
        else:
            print('No test directories found. Has sync been set up? are you in the correct directory?')
    else:
        copy_test_files(out_dir,**args_dict)


if __name__ == "__main__":
    main()
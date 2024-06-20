import argparse
import importlib.resources
import mcvqoe
import os.path
import sys
import tempfile

# Expected path components for csv files
# Not sure this is even needed with new file/folder structure implemented in 2023
csv_path_names = (("Access_Time", "Intelligibility", "Mouth_2_Ear", "PSuD",
                   "Transmit_Volume_Optimization"), ("MCV-QoE"))


def make_parser():

    #-----------------------[Setup ArgumentParser object]-----------------------

    parser = argparse.ArgumentParser(
        description="Reprocess audio files and write a new .csv with newly measured values")
    
    parser.add_argument('datafile', default=None, type=str,
                        help='CSV file from test to reprocess')
    parser.add_argument('outfile', default=None, type=str, nargs='?',
                        help="file to write reprocessed CSV data to. Can be the same name as datafile to overwrite results.\n" +
                        "if omitted output will be written to stdout")
    parser.add_argument('-m', '--measurement', type=str, default=None, metavar='M',
                        help='measurement to use to do reprocessing')
    parser.add_argument('--audio-path', type=str, default=None, metavar='P', dest='audio_path',
                        help='Path to audio files for test. Will be found automatically if not given')
    parser.add_argument('-s', '--split-audio-folder', default='', type=str, dest='split_audio_dest',
                        help='Folder to store single word clips to')

    return parser

def get_module(module_name=None, datafile=None):

    if not module_name:

        # Get module name
        module_name = mcvqoe.base.get_measurement_from_file(datafile)

        # Make sure a module was found
        if not module_name:
            raise RuntimeError(f"Unable to determine measurement for '{datafile}'")
    else:
        # Name given, clean up and use

        # Make lowercase
        module_name = module_name.lower()

        # Check if full import path was given
        if not module_name.startswith('mcvqoe.') :
            # Add mcvqoe to the module include
            module_name = 'mcvqoe.' + module_name

    # Load module and return
    return importlib.import_module(module_name).measure

def reprocess_file(test_obj, datafile, out_name, **kwargs):

    if not out_name:
        # Split data file path into parts
        d, n = os.path.split(datafile)
        # Construct new name for file
        out_name = os.path.join(d, 'R'+n)

    print(f'Loading test data from \'{datafile}\'', file=sys.stderr)
    # Read in test data
    test_dat = test_obj.load_test_data(datafile, **kwargs)

    print(f'Reprocessing test data to \'{out_name}\'', file=sys.stderr)

    test_obj.post_process(test_dat, out_name, test_obj.audio_path)

    return out_name

def main():

    #-----------------------------[Parse arguments]-----------------------------

    # Get parser
    parser = make_parser()

    args = parser.parse_args()

    #---------------------------[Load Measure Class]---------------------------

    measurement_class = get_module(module_name=args.measurement, datafile=args.datafile)

    #---------------------------[Create Test object]---------------------------

    # Create test obj to reprocess with
    test_obj = measurement_class()


    test_obj.split_audio_dest = args.split_audio_dest


    with tempfile.TemporaryDirectory() as tmp_dir:

        if(args.outfile == '--'):
            # Print results, don't save file
            out_name = os.path.join(tmp_dir, 'tmp.csv')
            print_outf = True
        else:
            out_name = args.outfile
            print_outf = False

        out_name = reprocess_file(test_obj, args.datafile, out_name, audio_path=args.audio_path)

        if(print_outf):
            with open(out_name, 'rt') as out_file:
                dat = out_file.read()
            print(dat)
            print('Reprocessing complete', file=sys.stderr)
        else:
            print(f'Reprocessing complete for \'{out_name}\'', file=sys.stderr)


# Main function
if __name__ == "__main__":
    main()
"""
Contains the prepare_molecules definition which reads, prepares, and writes
small molecules.
"""

import __future__

import sys
import json
import os
from datetime import datetime
from collections import OrderedDict

import gypsum.Utils as Utils
from gypsum.Parallelizer import Parallelizer

try:
    from rdkit.Chem import AllChem
    from rdkit import Chem
except:
    Utils.log("You need to install rdkit and its dependencies.")
    raise ImportError("You need to install rdkit and its dependencies.")

try:
    import numpy
except:
    Utils.log("You need to install numpy and its dependencies.")
    raise ImportError("You need to install numpy and its dependencies.")

try:
    from scipy.cluster.vq import kmeans2
except:
    Utils.log("You need to install scipy and its dependencies.")
    raise ImportError("You need to install scipy and its dependencies.")

from gypsum.MolContainer import MolContainer
from gypsum.Steps.SMILES.PrepareSmiles import prepare_smiles
from gypsum.Steps.ThreeD.PrepareThreeD import prepare_3d
from gypsum.Steps.IO.ProcessOutput import proccess_output
from gypsum.Steps.IO.LoadFiles import load_smiles_file
from gypsum.Steps.IO.LoadFiles import load_sdf_file

# see http://www.rdkit.org/docs/GettingStartedInPython.html#working-with-3d-molecules
def prepare_molecules(args):
    """A function for preparing small-molecule models for docking. To work, it
    requires that the python module rdkit be installed on the system.

    :param args: The arguments, from the commandline.
    :type args: dict
    :raises Exception: Is your input json file properly formed?
    :raises ImportError: mpi4py not installed, but --multithread_mode is set
       to mpi.
    :raises Exception: Output folder directory couldn't be found or created.
    :raises Exception: There is a corrupted container.
    """

    # Keep track of the tim the program starts.
    start_time = datetime.now()

    # A list of command-line parameters that will be ignored if using a json
    # file.
    json_warning_list = ['source', 'output_file', 'num_processors',
                         'min_ph', 'max_ph', 'delta_ph_increment',
                         'thoroughness', 'max_variants_per_compound',
                         'ph_std_dev']

    # Whether to warn the user that the above parameters, if specified, will
    # be ignored.
    need_to_print_override_warning = False

    if "json" in args:
        # "json" is one of the parameters, so we'll be ignoring the rest.
        try:
            params = json.load(open(args['json']))
        except:
            raise Exception("Is your input json file properly formed?")

        params = set_parameters(params)
        if [i for i in json_warning_list if i in list(args.keys())]:
            need_to_print_override_warning = True
    else:
        # We're actually going to use all the command-line parameters. No
        # warning necessary.
        params = set_parameters(args)

    # If running in serial mode, make sure only one processor is used.
    if params["multithread_mode"] == "serial":
        if params["num_processors"] != 1:
            print("Because --multithread_mode was set to serial, this will be run on a single processor.")
        params["num_processors"] = 1

    # Handle mpi errors if mpi4py isn't installed
    if params["multithread_mode"] == "mpi":
        try:
            import mpi4py
        except:
            printout = "mpi4py not installed but --multithread_mode is set to mpi. \n Either install mpi4py or switch multithread_mode to multithreading or serial"
            raise ImportError(printout)

    # Throw a message if running on windows. Windows doesn't deal with with
    # multiple processors, so use only 1.
    if sys.platform == "win32":
        print("Our Multiprocessing is not supportive of Windows. We will run tasks in Serial")
        params["num_processors"] = 1
        params["multithread_mode"] = "serial"

    # Launch mpi workers if that's what's specified.
    if params["multithread_mode"] == 'mpi':
        params["Parallelizer"] = Parallelizer(params["multithread_mode"], params["num_processors"])
    else:
        # Lower-level mpi (i.e. making a new Parallelizer within an mpi) has
        # problems with importing the MPI environment and mpi4py. So we will
        # flag it to skip the MPI mode and just go to multithread/serial. This
        # is a saftey precaution
        params["Parallelizer"] = Parallelizer(params["multithread_mode"], params["num_processors"], True)

    # Let the user know that their command-line parameters will be ignored, if
    # they have specified a json file.
    if need_to_print_override_warning == True:
        print("WARNING: Using the --json flag overrides all other flags.")

    # Load SMILES data
    if isinstance(params["source"], str):
        # Smiles must be array of strs.
        src = params["source"]
        if src.lower().endswith(".smi") or src.lower().endswith(".can"):
            # It's an smi file.
            smiles_data = load_smiles_file(src)
        elif params["source"].lower().endswith(".sdf"):
            # It's an sdf file. Convert it to a smiles.
            smiles_data = load_sdf_file(src)
        else:
            smiles_data = [params["source"]]
    else:
        pass  # It's already in the required format.

    # Make the output directory if necessary.
    if os.path.exists(params["output_folder"]) == False:
        os.mkdir(params["output_folder"])
        if os.path.exists(params["output_folder"]) == False:
            raise Exception("Output folder directory couldn't be found or created.")

    # For Debugging
    # print("")
    # print("###########################")
    # print("num_procs  :  ", params["num_processors"])
    # print("chosen mode  :  ", params["multithread_mode"])
    # print("Parallel style:  ", params["Parallelizer"].return_mode())
    # print("Number Nodes:  ", params["Parallelizer"].return_node())
    # print("###########################")
    # print("")

    # Make the molecule containers.
    contnrs = []
    idx_counter = 0
    for i in range(0,len(smiles_data)):
        smiles, name, props = smiles_data[i]
        if detect_unassigned_bonds(smiles) is None:
            print("Warning: Throwing out SMILES because of unassigned bonds: " + smiles)
            continue

        new_contnr = MolContainer(smiles, name, idx_counter, props)
        if new_contnr.orig_smi_canonical==None or type(new_contnr.orig_smi_canonical) !=str:
            print("Warning: Throwing out SMILES because of it couldn't convert to mol: " + smiles)
            continue

        contnrs.append(new_contnr)
        idx_counter += 1

    # Remove None types from failed conversion
    contnrs = [x for x in contnrs if x.orig_smi_canonical!=None]
    if len(contnrs)!= idx_counter:
        raise Exception("There is a corrupted container")

    # Start creating the models.

    # Prepare the smiles. Desalt, consider alternate ionization, tautometeric,
    # stereoisomeric forms, etc.
    prepare_smiles(contnrs, params)

    # Convert the processed SMILES strings to 3D.
    prepare_3d(contnrs, params)

    # Add in name and unique id to each molecule.
    add_mol_id_props(contnrs)

    # Output the current SMILES.
    Utils.print_current_smiles(contnrs)

    # Write any mols that fail entirely to a file.
    deal_with_failed_molecules(contnrs, params)

    # Calculate the total run time.
    end_time = datetime.now()
    run_time = end_time - start_time
    params["start_time"] = str(start_time)
    params["end_time"] = str(end_time)
    params["run_time"] = str(run_time)

    # Process the output.
    proccess_output(contnrs, params)

    # Kill mpi workers if necessary.
    params["Parallelizer"].end(params["multithread_mode"])

def detect_unassigned_bonds(smiles):
    """Detects whether a give smiles string has unassigned bonds.

    :param smiles: The smiles string.
    :type smiles: string
    :return: None if it has bad bonds, or the input smiles string otherwise.
    :rtype: None|string
    """

    mol = Chem.MolFromSmiles(smiles, sanitize=False)
    for bond in mol.GetBonds():
        if bond.GetBondTypeAsDouble() == 0:
            return None
    return smiles

def set_parameters(params_unicode):
    """Set the parameters that will control this ConfGenerator object.

    :param params_unicode: The parameters, with keys and values possibly in
       unicode.
    :type params_unicode: dict
    :return: The parameters, properly processed, with defaults used when no
       value specified.
    :rtype: dict
    """

    # Set the default values.
    default = OrderedDict({
        "source" : '',
        "output_folder": '',
        "output_file" : '',
        "separate_output_files" : False,
        "output_pdb": False,
        "num_processors" : -1,
        "start_time" : 0,
        "end_time" : 0,
        "run_time" : 0,
        "min_ph" : 6.4,
        "max_ph" : 8.4,
        "ph_std_dev" : 1.0,
        "thoroughness" : 3,
        "max_variants_per_compound" : 5,
        "second_embed" : False,
        "2d_output_only" : False,
        "skip_optimize_geometry" : False,
        "skip_alternate_ring_conformations" : False,
        "skip_adding_hydrogen" : False,
        "skip_making_tautomers" : False,
        "skip_ennumerate_chiral_mol" : False,
        "skip_ennumerate_double_bonds" : False,
        "multithread_mode" : "multithreading",
        "cache_prerun": False,
        "test": False
    })

    # Modify params so that they keys are always lower case.
    # Also, rdkit doesn't play nice with unicode, so convert to ascii

    # Because Python2 & Python3 use different string objects, we separate their
    # usecases here.
    params = {}
    if sys.version_info < (3,):
        # For Python3
        for param in params_unicode:
            val = params_unicode[param]
            if isinstance(val, unicode):
                val = str(val).encode("utf8")
            key = param.lower().encode("utf8")
            params[key] = val
    else:
        # For Python2
        for param in params_unicode:
            val = params_unicode[param]
            key = param.lower()
            params[key] = val

    # Overwrites values with the user parameters where they exit.
    merge_parameters(default, params)

    # Checks and prepares the final parameter list.
    final_params = finalize_params(default)

    return final_params

def merge_parameters(default, params):
    """Add default values if missing from parameters.

    :param default: The parameters.
    :type default: dict
    :param params: The default values
    :type params: dict
    :raises KeyError: Unrecognized parameter.
    :raises TypeError: Input parameter has a different type than the default.
    """

    # Generate a dictionary with the same keys, but the types for the values.
    type_dict = make_type_dict(default)

    # Move user-specified values into the parameter.
    for param in params:
        # Throw an error if there's an unrecognized parameter.
        if param not in default:
            Utils.log(
                "ERROR! Parameter \"" + str(param) + "\" not recognized!"
            )
            Utils.log("Here are the options:")
            Utils.log(str(list(default.keys())))
            raise KeyError("Unrecognized parameter: " + str(param))

        # Throw an error if the input parameter has a different type than
        # the default one.
        if not isinstance(params[param], type_dict[param]):
            # Cast int to float if necessary
            if type(params[param]) is int and type_dict[param] is float:
                params[param] = float(params[param])
            else:
                # Seems to be a type mismatch.

                Utils.log(
                    "ERROR! The parameter \"" + param + "\" must be of " +
                    "type" + str(type_dict[param]) + ", but it is of type " +
                    str(type(params[param])) + "."
                )
                raise TypeError("Input parameter (" + param + ") has a different type than the default.")

        # Update the parameter value with the user-defined one.
        default[param] = params[param]

def make_type_dict(dictionary):
    """Creates a types dictionary from an existant dictionary. Keys are
       preserved, but values are the types.

    :param dictionary: A dictionary, with keys are values.
    :type dictionary: dict
    :raises Exception: There appears to be an error in your parameters.
    :return: A dictionary with the same keys, but the values are the types.
    :rtype: dict
    """

    type_dict = {}
    allowed_types = [int, float, bool, str]
    # Go through the dictionary keys.
    for key in dictionary:
        # Get the the type of the value.
        val = dictionary[key]
        for allowed in allowed_types:
            if isinstance(val, allowed):
                # Add it to the type_dict.
                type_dict[key] = allowed

        # The value ha san unacceptable type. Throw an error.
        if key not in type_dict:
            Utils.log(
                "ERROR: There appears to be an error in your parameter " +
                "JSON file. No value can have type " + str(type(val)) +
                "."
            )
            raise Exception("ERROR: There appears to be an error in your parameters.")

    return type_dict

def finalize_params(params):
    """Checks and updates parameters to their final values.

    :param params: The parameters.
    :type params: dict
    :raises NotImplementedError: Missing parameter.
    :raises Exception: Source file doesn't exist.
    :raises Exception: To output files as .pdbs one needs to specify the
        output_folder.
    :raises Exception: For separate_output_files, one needs to specify the
       output_folder.
    :raises Exception: Missing parameter indicating where to write the
       output(s). Can be an HTML or .SDF file, or a directory.
    :return: The parameters, corrected/updated where needed.
    :rtype: dict
    """

    # Throw an error if there's a missing parameter.
    if params["source"] == "":
        Utils.log(
            "ERROR! Missing parameter \"source\". You need to specify " +
            "the source of the input molecules (probably a SMI or SDF " +
            "file)."
        )
        raise NotImplementedError("Missing parameter.")

    # Note on parameter "source", the data source. If it's a string that
    # ends in ".smi", it's treated as a smiles file. If it's a string that
    # ends in ".sdf", it's treated as an sdf file. If it's any other
    # string, it's assumed to be a smiles string itself and is assigned a
    # name of "". If it's a list, it's assumed to be a list of tuples,
    # [SMILES, Name].

    # Check some required variables.
    try:
        params["source"] = os.path.abspath(params["source"])
    except:
        raise Exception("Source file doesn't exist.")
    source_dir = params["source"].strip(os.path.basename(params["source"]))

    if params["output_folder"] == "" and params["source"] != "":
        params["output_folder"] = source_dir + "output" + str(os.sep)

    if params["output_pdb"] == True and params["output_folder"] == "":
        Utils.log(
            "ERROR! To output files as .pdbs one needs to specify the output_folder."
        )
        raise Exception("To output files as .pdbs one needs to specify the output_folder.")

    if params["separate_output_files"] == True and params["output_folder"] == "":
        Utils.log(
            "ERROR! For separate_output_files one needs to specify the output_folder."
        )
        raise Exception("For separate_output_files one needs to specify the output_folder.")

    if params["output_file"] == "" and params["output_folder"] != "":
        params["output_file"] = params["output_folder"] + "output.sdf"

    if params["output_file"] == "" and params["output_folder"] == "":
        Utils.log(
            "ERROR! Missing parameters \"output_folder\" and \"output_folder\". You need to " +
            "specify where to write the output file(s). Can be an HTML or " +
            "SDF file or a directory."
        )
        raise Exception("Missing parameter indicating where to write the" +
                        "output(s). Can be an HTML or .SDF file, or a " +
                        "directory.")

    # Make sure multithread_mode is always lower case.
    params["multithread_mode"] = params["multithread_mode"].lower()

    return params

def add_mol_id_props(contnrs):
    """Once all molecules have been generated, go through each and add the
       name and a unique id (for writing to the SDF file, for example).

    :param contnrs: A list of containers (MolContainer.MolContainer).
    :type contnrs: list
    """

    cont_id = 0
    for contnr in contnrs:
        for mol in contnr.mols:
            cont_id = cont_id + 1
            mol.set_rdkit_mol_prop("UniqueID", str(cont_id))
            mol.set_all_rdkit_mol_props()

def deal_with_failed_molecules(contnrs, params):
    """Removes and logs failed molecules.

    :param contnrs: A list of containers (MolContainer.MolContainer).
    :type contnrs: list
    :param params: The parameters, used to determine the filename that will
       contain the failed molecules.
    :type params: dict
    """

    failed_ones = []  # To keep track of failed molecules
    for contnr in contnrs:
        if len(contnr.mols) == 0:
            astr = contnr.orig_smi + "\t" + contnr.name
            failed_ones.append(astr)

    # Let the user know if there's more than one failed molecule.
    if len(failed_ones) > 0:
        Utils.log(
            "\n3D models could not be generated for the following entries:"
        )
        Utils.log("\n".join(failed_ones))
        Utils.log("\n")

        # Write the failures to an smi file.
        outfile = open(params["output_file"] + ".failed.smi", 'w')
        outfile.write("\n".join(failed_ones))
        outfile.close()

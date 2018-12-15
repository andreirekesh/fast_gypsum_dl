"""A module for loading in files."""

import __future__

try:
    from rdkit import Chem
except:
    Utils.log("You need to install rdkit and its dependencies.")
    raise ImportError("You need to install rdkit and its dependencies.")

def load_smiles_file(filename):
    """Loads a smiles file.

    :param filename: The filename.
    :type filename: str
    :return: A list of tuples, (SMILES, Name).
    :rtype: list
    """

    # A smiles file contains one molecule on each line. Each line is a string,
    # separated by white space, followed by the molecule name.
    data = []
    duplicate_names = {}
    missing_name_counter = 0
    line_counter = 0
    name_list = []
    for line in open(filename):
        # You've got the line.
        line = line.strip()
        if line != "":
            # From that line, get the smiles string and name.
            chunks = line.split()
            smiles = chunks[0]
            name = " ".join(chunks[1:])

            # Handle unnamed ligands.
            if name == "":
                print("\tUntitled ligand on line {}".format(line_counter))
                name = "untitled_lig_{}_line_{}".format(missing_name_counter,line_counter)
                print("\tNaming that ligand {}".format(name))
                print("\tAll associated files will be refered to with this name")
                missing_name_counter += 1

            # Handle duplicate ligands in same list.
            if name in name_list:
                # If multiple names...
                if name in duplicate_names.keys():
                    duplicate_names[name] = duplicate_names[name] + 1

                    new_name = "{}_copy_{}".format(name, duplicate_names[name])
                    print("\nMultiple entries with the ligand name: {}".format(name))
                    print("\tThe veresion of the ligand on line {} will be retitled {}".format(line_counter,new_name))
                    print("\tAll associated files will be refered to with this name")
                    name = new_name
                else:
                    duplicate_names[name] = 2
                    new_name = "{}_copy_{}".format(name, duplicate_names[name])
                    print("\nMultiple entries with the ligand name: {}".format(name))
                    print("\tThe veresion of the ligand on line {} will be retitled {}".format(line_counter,new_name))
                    print("\tAll associated files will be refered to with this name")
                    name = new_name

            # Save the data for this line and advance.
            name_list.append(name)
            line_counter +=1
            data.append((smiles, name, {}))

    # Return the data.
    return data

def load_sdf_file(filename):
    """Loads an sdf file.

    :param filename: The filename.
    :type filename: str
    :return: A list of tuples, (SMILES, Name).
    :rtype: list
    """

    suppl = Chem.SDMolSupplier(filename)
    data = []
    duplicate_names = {}
    missing_name_counter = 0
    mol_obj_counter = 0
    name_list = []
    for mol in suppl:
        # Convert mols to smiles. That's what the rest of the program is
        # designed to deal with.
        smiles = Chem.MolToSmiles(
            mol, isomericSmiles=True, canonical=True
        )

        try:
            name = mol.GetProp("_Name")
        except:
            name = ""

        # Handle unnamed ligands
        if name == "":
            print("\tUntitled ligand for the {} molecule in the input SDF".format(mol_obj_counter))
            name = "untitled_lig_{}_molnum_{}".format(missing_name_counter,mol_obj_counter)
            print("\tNaming that ligand {}".format(name))
            print("\tAll associated files will be refered to with this name")
            missing_name_counter += 1

            # Handle duplicate ligands in same list.
            if name in name_list:
                # If multiple names.
                if name in list(duplicate_names.keys()):
                    duplicate_names[name] = duplicate_names[name] + 1

                    new_name = "{}_copy_{}".format(name, duplicate_names[name])
                    print("\nMultiple entries with the ligand name: {}".format(name))
                    print("\tThe veresion of the ligand for the {} molecule in the SDF file will be retitled {}".format(mol_obj_counter,new_name))
                    print("\tAll associated files will be refered to with this name")
                    name = new_name
                else:
                    duplicate_names[name] = 2
                    new_name = "{}_copy_{}".format(name, duplicate_names[name])
                    print("\nMultiple entries with the ligand name: {}".format(name))
                    print("\tThe veresion of the ligand for the {} molecule in the SDF file will be retitled {}".format(mol_obj_counter,new_name))
                    print("\tAll associated files will be refered to with this name")
                    name = new_name

            mol_obj_counter += 1
            name_list.append(name)

        # SDF files may also contain properties. Get those as well.
        try:
            properties = mol.GetPropsAsDict()
        except:
            properties = {}

        if smiles != "":
            data.append((smiles, name, properties))

    return data

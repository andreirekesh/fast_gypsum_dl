"""
This module identifies and enumerates the possible protonation sites of
molecules.
"""

from rdkit import Chem

import gypsum.Parallelizer as Parallelizer
import gypsum.Utils as Utils
import gypsum.ChemUtils as ChemUtils
import gypsum.MyMol as MyMol
import gypsum.MolContainer as MolCont

from gypsum.Steps.SMILES.dimorphite.dimorphite_dl import protonate

def add_hydrogens(contnrs, min_pH, max_pH, st_dev, max_variants_per_compound,
                  thoroughness, num_procs, multithread_mode,
                  parallelizer_obj):
    """Adds hydrogen atoms to molecule containers, as appropriate for a given
       pH.

    :param contnrs: A list of containers (MolContainer.MolContainer).
    :type contnrs: A list.
    :param min_pH: The minimum pH to consider.
    :type min_pH: float
    :param max_pH: The maximum pH to consider.
    :type max_pH: float
    :param st_dev: The standard deviation. See Dimorphite-DL paper.
    :type st_dev: float
    :param max_variants_per_compound: To control the combinatorial explosion,
       only this number of variants (molecules) will be advanced to the next
       step.
    :type max_variants_per_compound: int
    :param thoroughness: How many molecules to generate per variant (molecule)
       retained, for evaluation. For example, perhaps you want to advance five
       molecules (max_variants_per_compound = 5). You could just generate five
       and advance them all. Or you could generate ten and advance the best
       five (so thoroughness = 2). Using thoroughness > 1 increases the
       computational expense, but it also increases the chances of finding good
       molecules.
    :type thoroughness: int
    :param num_procs: The number of processors to use.
    :type num_procs: int
    :param multithread_mode: The multithred mode to use.
    :type multithread_mode: string
    :param parallelizer_obj: The Parallelizer object.
    :type parallelizer_obj: Parallelizer.Parallelizer
    """

    """
    JDD: What is this? This is a stub that is used to keep track of what I need to still do.
    """

    # Make a simple directory with the ionization parameters.
    protonation_settings = {"min_ph": min_pH,
                            "max_ph": max_pH,
                            "st_dev": st_dev}

    # Format the inputs for use in the parallelizer.
    inputs = tuple([tuple([cont, protonation_settings]) for cont in contnrs if type(cont.orig_smi_canonical)==str])

    # Run the parallelizer and collect the results.
    results = parallelizer_obj.run(inputs, parallel_add_H, num_procs, multithread_mode)
    results = Parallelizer.flatten_list(results)

    # Dimorphite-DL might not have generated ionization states for some
    # molecules. Identify those that are missing.
    contnr_idxs_of_failed = Utils.fnd_contnrs_not_represntd(contnrs, results)

    # For those molecules, just use the original SMILES string, with hydrogen
    # atoms added using RDKit.
    for miss_indx in contnr_idxs_of_failed:
        Utils.log(
            "\tWARNING: Gypsum produced no valid protonation states for " +
            contnrs[miss_indx].orig_smi + " (" +
            contnrs[miss_indx].name + "), so using the original " +
            "smiles."
        )

        amol = contnrs[miss_indx].mol_orig_frm_inp_smi
        amol.contnr_idx = miss_indx

        # Save this failure to the genealogy record.
        amol.genealogy = [
            amol.orig_smi + " (source)",
            amol.orig_smi_deslt + " (desalted)",
            "(WARNING: Gypsum could not assign protonation states)"
        ]

        # Save this one to the results too, even though not processed
        # properly.
        results.append(amol)

    # Keep only the top few compound variants in each container, to prevent a
    # combinatorial explosion.
    ChemUtils.bst_for_each_contnr_no_opt(
        contnrs, results, max_variants_per_compound, thoroughness
    )

def parallel_add_H(contnr, protonation_settings):
    """Creates alternate ionization variants for a given molecule container.
       This is the function that gets fed into the parallelizer.

    :param contnr: The molecule container.
    :type contnr: MolContainer.MolContainer
    :param protonation_settings: Protonation settings to pass to Dimorphite-DL.
    :type protonation_settings: dict
    :raises Exception: container.orig_smi_canonical is not a string.
    :return: [description]
    :rtype: [type]
    """

    # Make sure the canonical SMILES is actually a string.
    if type(contnr.orig_smi_canonical) != str:
        print("container.orig_smi_canonical: ", contnr.orig_smi_canonical)
        print("type container.orig_smi_canonical: ", type(contnr.orig_smi_canonical))
        raise Exception("container.orig_smi_canonical: ", contnr.orig_smi_canonical)

    # Add the SMILES string to the protonation parameters.
    protonation_settings["smiles"] = contnr.orig_smi_canonical

    # Protonate the SMILESstring. This is Dimorphite-DL.
    smis = protonate(protonation_settings)

    # Convert the protonated SMILES strings into a list of rdkit molecule
    # objects. Add hydrogens to the smis, now that the Dimorphite-DL valences
    # are in place.
    rdkit_mols = [Chem.AddHs(Chem.MolFromSmiles(smi.strip())) for smi in smis]

    # Convert from rdkit mols to MyMol.MyMol.
    addH_mols = [MyMol.MyMol(mol) for mol in rdkit_mols if mol is not None]

    # Remove MyMols with odd substructures.
    addH_mols = [mol for mol in addH_mols if mol.remove_bizarre_substruc() is False]

    # I once saw it add a "C+"" here. So do a secondary check at this point to
    # make sure it's valid. Recreate the list, moving new MyMol.MyMol objects
    # into the return_values list.

    return_values = []

    orig_mol = contnr.mol_orig_frm_inp_smi
    for Hm in addH_mols:
        Hm.inherit_contnr_props(contnr)
        Hm.genealogy = orig_mol.genealogy[:]
        Hm.name = orig_mol.name

        if Hm.smiles() != orig_mol.smiles():
            Hm.genealogy.append(Hm.smiles(True) + " (protonated)")

        return_values.append(Hm)

    return return_values

######################################################.
#          This file stores functions used           #
#                in multiple modules                 #
######################################################.

import os
import subprocess
import sys
import time
import getopt
import numpy as np
import glob
import ast
import yaml
import pandas as pd
import json
import math
from pathlib import Path
from rdkit.Chem.rdMolAlign import GetBestRMS
from rdkit.Chem.rdmolops import RemoveHs
from rdkit import Geometry
from rdkit.Chem import Mol, rdmolfiles
from rdkit.Chem import AllChem as Chem
from aqme.argument_parser import set_options, var_dict
from rdkit import RDLogger
from aqme.xtb_to_json import read_json
import rdkit

GAS_CONSTANT = 8.3144621  # J / K / mol
J_TO_AU = 4.184 * 627.509541 * 1000.0  # UNIT CONVERSION
T = 298.15

aqme_version = "1.3.1"
time_run = time.strftime("%Y/%m/%d %H:%M:%S", time.localtime())
aqme_ref = f"AQME v {aqme_version}, Alegre-Requena, J. V.; Sowndarya, S.; Perez-Soto, R.; Alturaifi, T. M.; Paton, R. S., 2022. https://github.com/jvalegre/aqme"

RDLogger.DisableLog("rdApp.*")


def get_boltz(energy):
    """
    Gets the boltz weights for a list of energies
    """
    energ = [number - min(energy) for number in energy]

    boltz_sum = 0.0
    for e in energ:
        boltz_sum += math.exp(-e * J_TO_AU / GAS_CONSTANT / T)
    weights = []

    for e in energ:
        weight = math.exp(-e * J_TO_AU / GAS_CONSTANT / T) / boltz_sum
        weights.append(weight)

    return weights


def average_prop_mol(weights, prop):
    """
    Rtuerns the average properties for molecular properties
    """
    boltz_avg = 0.0
    for i, p in enumerate(prop):
        boltz_avg += p * weights[i]
    return boltz_avg


def average_prop_atom(weights, prop):
    """
    Rtuerns the average properties for molecular properties
    """
    boltz_avg = []
    for i, p in enumerate(prop):
        boltz_avg.append([number * weights[i] for number in p])
    boltz_res = np.sum(boltz_avg, 0)
    return boltz_res


def get_boltz_avg_properties_xtb(
    json_files,
    name,
    boltz_dir,
    type,
    nmr_atoms=None,
    nmr_slope=None,
    nmr_intercept=None,
    nmr_experim=None,
    mol=None,
):
    """
    Gets the properties from json files and gives boltz averaged boltz properties
    """
    if type == "xtb":
        mol_prop = [
            "total energy",
            "HOMO-LUMO gap/eV",
            "electronic energy",
            "Dipole module/D",
            "Total charge",
            "HOMO",
            "LUMO",
            "Fermi-level/eV",
            "Total dispersion C6",
            "Total dispersion C8",
            "Total polarizability alpha",
            "Total FOD",
        ]
        atom_prop = [
            "dipole",
            "partial charges",
            "mulliken charges",
            "cm5 charges",
            "FUKUI+",
            "FUKUI-",
            "FUKUIrad",
            "s proportion",
            "p proportion",
            "d proportion",
            "Coordination numbers",
            "Dispersion coefficient C6",
            "Polarizability alpha",
            "FOD",
            "FOD s proportion",
            "FOD p proportion",
            "FOD d proportion",
        ]
    elif type == "nmr":
        atom_prop = [
            "NMR Chemical Shifts",
        ]
        if nmr_experim is not None:
            exp_data = pd.read_csv(nmr_experim)

    energy = []

    for k, json_file in enumerate(json_files):
        json_data = read_json(json_file)
        if type == "xtb":
            energy.append(json_data["total energy"])
        elif type == "nmr":
            energy.append(json_data["optimization"]["scf"]["scf energies"][-1])

            json_data["properties"]["NMR"]["NMR Chemical Shifts"] = get_chemical_shifts(
                json_data, nmr_atoms, nmr_slope, nmr_intercept
            )
            if nmr_experim is not None:
                list_shift = json_data["properties"]["NMR"]["NMR Chemical Shifts"]
                df = pd.DataFrame(
                    list_shift.items(),
                    columns=["atom_idx", "conf_{}".format(k + 1)],
                )
                df["atom_idx"] = df["atom_idx"] + 1
                exp_data = exp_data.merge(df, on=["atom_idx"])
        with open(json_file, "w") as outfile:
            json.dump(json_data, outfile)

    boltz = get_boltz(energy)

    avg_json_data = {}
    for prop in atom_prop:
        prop_list = []
        for json_file in json_files:
            json_data = read_json(json_file)
            if type == "xtb":
                prop_list.append(json_data[prop])
            if type == "nmr":
                prop_list.append(json_data["properties"]["NMR"][prop].values())
        avg_prop = average_prop_atom(boltz, prop_list)

        if type == "nmr":
            dictavgprop = {}
            for i, key in enumerate(json_data["properties"]["NMR"][prop].keys()):
                dictavgprop[key] = avg_prop[i]
            avg_json_data[prop] = dictavgprop

            if nmr_experim is not None:
                list_shift = avg_json_data[prop]
                df = pd.DataFrame(
                    list_shift.items(),
                    columns=["atom_idx", "boltz_avg"],
                )
                df["atom_idx"] = df["atom_idx"].astype(int) + 1
                exp_data = exp_data.merge(df, on=["atom_idx"])
                exp_data["error_boltz"] = abs(
                    exp_data["experimental_ppm"] - exp_data["boltz_avg"]
                )
                exp_data.round(2).to_csv(
                    nmr_experim.split(".csv")[0] + "_predicted.csv", index=False
                )
        elif type == "xtb":
            avg_json_data[prop] = avg_prop.tolist()

    if type == "xtb":
        for prop in mol_prop:
            prop_list = []
            for json_file in json_files:
                json_data = read_json(json_file)
                prop_list.append(json_data[prop])
            avg_prop = average_prop_mol(boltz, prop_list)
            avg_json_data[prop] = avg_prop

    final_boltz_file = str(boltz_dir) + "/" + name + "_boltz.json"
    if mol is not None:
        avg_json_data = get_rdkit_properties(avg_json_data, mol)
    with open(final_boltz_file, "w") as outfile:
        json.dump(avg_json_data, outfile)


def get_rdkit_properties(avg_json_data, mol):
    avg_json_data["NHOHCount"] = rdkit.Chem.Lipinski.NHOHCount(mol)
    avg_json_data["FractionCSP3"] = rdkit.Chem.Lipinski.FractionCSP3(mol)
    avg_json_data["NOCount"] = rdkit.Chem.Lipinski.NOCount(mol)
    avg_json_data["NumAliphaticRings"] = rdkit.Chem.Lipinski.NumAliphaticRings(mol)
    avg_json_data["NumAromaticRings"] = rdkit.Chem.Lipinski.NumAromaticRings(mol)
    avg_json_data["NumHAcceptors"] = rdkit.Chem.Lipinski.NumHAcceptors(mol)
    avg_json_data["NumHDonors"] = rdkit.Chem.Lipinski.NumHDonors(mol)
    avg_json_data["NumHeteroatoms"] = rdkit.Chem.Lipinski.NumHeteroatoms(mol)
    avg_json_data["NumRotatableBonds"] = rdkit.Chem.Lipinski.NumRotatableBonds(mol)

    avg_json_data["TPSA"] = rdkit.Chem.Descriptors.TPSA(mol)
    avg_json_data["MolLogP"] = rdkit.Chem.Descriptors.MolLogP(mol)
    # avg_json_data["NumAmideBonds"] = rdkit.Chem.Descriptors.NumAmideBonds(mol)

    return avg_json_data


def get_chemical_shifts(json_data, nmr_atoms, nmr_slope, nmr_intercept):

    if not isinstance(nmr_atoms, list):
        nmr_atoms = ast.literal_eval(nmr_atoms)
    if not isinstance(nmr_slope, list):
        nmr_slope = ast.literal_eval(nmr_slope)
    if not isinstance(nmr_intercept, list):
        nmr_intercept = ast.literal_eval(nmr_intercept)

    atoms = json_data["atoms"]["elements"]["number"]
    tensor = json_data["properties"]["NMR"]["NMR isotopic tensors"]
    shifts = {}
    i = 0
    for atom, ten in zip(atoms, tensor):
        if atom in nmr_atoms:
            # assigning values from arrays
            index = nmr_atoms.index(atom)
            slope_nuc = nmr_slope[index]
            intercept_nuc = nmr_intercept[index]

            scaled_nmr = (intercept_nuc - ten) / (-slope_nuc)
            shifts[i] = scaled_nmr
        else:
            pass
        i += 1

    return shifts


def run_command(command, outfile):
    """
    Runs the subprocess command and outputs to the necessary output file
    """

    p2 = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    txt = [line.decode("utf-8") for line in p2.stdout]
    p2.stdout.close()

    with open(outfile, "w") as f:
        for line in txt:
            f.write(line)
    f.close()


def periodic_table():
    items = """X
			H                                                                                                  He
			Li Be  B                                                                             C   N   O   F  Ne
			Na Mg Al                                                                            Si   P   S  Cl  Ar
			K Ca Sc                                           Ti  V Cr Mn Fe Co Ni Cu  Zn  Ga  Ge  As  Se  Br  Kr
			Rb Sr  Y                                           Zr Nb Mo Tc Ru Rh Pd Ag  Cd  In  Sn  Sb  Te   I  Xe
			Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta  W Re Os Ir Pt Au  Hg  Tl  Pb  Bi  Po  At  Rn
			Fr Ra Ac Th Pa  U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Uub Uut Uuq Uup Uuh Uus Uuo
			"""
    periodic_table = items.replace("\n", " ").strip().split()
    periodic_table[0] = ""

    return periodic_table


# load paramters from yaml file
def load_from_yaml(self):
    """
    Loads the parameters for the calculation from a yaml if specified. Otherwise
    does nothing.
    """

    txt_yaml = f"\no  Importing AQME parameters from {self.varfile}"
    error_yaml = False
    # Variables will be updated from YAML file
    try:
        if os.path.exists(self.varfile):
            if os.path.splitext(self.varfile)[1] in [".yaml", ".yml", ".txt"]:
                with open(self.varfile, "r") as file:
                    try:
                        param_list = yaml.load(file, Loader=yaml.SafeLoader)
                    except yaml.scanner.ScannerError:
                        txt_yaml = f'\nx  Error while reading {self.varfile}. Edit the yaml file and try again (i.e. use ":" instead of "=" to specify variables)'
                        error_yaml = True
        if not error_yaml:
            for param in param_list:
                if hasattr(self, param):
                    if getattr(self, param) != param_list[param]:
                        setattr(self, param, param_list[param])

    except UnboundLocalError:
        txt_yaml = "\nx  The specified yaml file containing parameters was not found! Make sure that the valid params file is in the folder where you are running the code."

    return self, txt_yaml


# class for logging
class Logger:
    """
    Class that wraps a file object to abstract the logging.
    """

    # Class Logger to writargs.input.split('.')[0] output to a file
    def __init__(self, filein, append, suffix="dat"):
        self.log = open(f"{filein}_{append}.{suffix}", "w")

    def write(self, message):
        """
        Appends a newline character to the message and writes it into the file.

        Parameters
        ----------
        message : str
           Text to be written in the log file.
        """
        self.log.write(f"{message}\n")
        print(f"{message}\n")

    def fatal(self, message):
        """
        Writes the message to the file. Closes the file and raises an error exit

        Parameters
        ----------
        message : str
           text to be written in the log file.
        """
        self.write(message)
        self.finalize()
        raise SystemExit(1)

    def finalize(self):
        """
        Closes the file
        """
        self.log.close()


def creation_of_dup_csv_cmin(cmin):

    """
    Generates a pandas.DataFrame object with the appropiate columns for the
    conformational search and the minimization.

    Parameters
    ----------
    cmin : str
        Minimization method. Current valid methods are: ['xtb','ani']

    Returns
    -------
    pandas.DataFrame
    """

    # Boolean aliases from args
    is_xtb = cmin == "xtb"
    is_ani = cmin == "ani"

    # column blocks definitions

    xtb_columns = [
        "xTB-Initial-samples",
        "xTB-energy-window",
        "xTB-initial_energy_threshold",
        "xTB-RMSD-and-energy-duplicates",
        "xTB-Unique-conformers",
    ]
    ANI_columns = [
        "ANI-Initial-samples",
        "ANI-energy-window",
        "ANI-initial_energy_threshold",
        "ANI-RMSD-and-energy-duplicates",
        "ANI-Unique-conformers",
    ]
    end_columns = ["CMIN time (seconds)", "Overall charge"]

    # Check Minimization Method
    if is_ani:
        columns = ANI_columns
    if is_xtb:  # is_ani and is_xtb will not happen, but this is what was written
        columns = xtb_columns

    columns += end_columns
    return pd.DataFrame(columns=columns)


def move_file(destination, source, file):
    """
    Moves files from the source folder to the destination folder and creates
    the destination folders when needed.

    Parameters
    ----------
    destination : str
        Path to the destination folder
    src : str
        Path to the source folder
    file : str
        Full name of the file (file + extension)
    """

    destination.mkdir(exist_ok=True, parents=True)
    filepath = source / file
    try:
        filepath.rename(destination / file)
    except FileExistsError:
        filepath.replace(destination / file)


def get_info_input(file):
    """
    Takes an input file and retrieves the coordinates of the atoms and the
    total charge.

    Parameters
    ----------
    file : str or pathlib.Path
        A path pointing to a valid .com or .gjf file

    Returns
    -------
    coordinates : list
        A list of strings (without \\n) that contain the xyz coordinates of the .gjf or .com file
    charge : str
        A str with the number corresponding to the total charge of the .com or .gjf file
    """

    with open(file, "r") as input_file:
        input_lines = input_file.readlines()

    _iter = input_lines.__iter__()

    line = ""
    # input for Gaussian calculations
    if str(file).split(".")[1] in ["com", "gjf"]:

        # Find the command line
        while "#" not in line:
            line = next(_iter)

        # in case the keywords are distributed in multiple lines
        while len(line.split()) > 0:
            line = next(_iter)

        # pass the title lines
        _ = next(_iter)
        while line:
            line = next(_iter).strip()

        # Read charge and multiplicity
        charge, mult = next(_iter).strip().split()

        # Store the atom types and coordinates until next empty line.
        atoms_and_coords = []
        line = next(_iter).strip()
        while line:
            atoms_and_coords.append(line.strip())
            line = next(_iter).strip()

    # input for ORCA calculations
    if str(file).split(".")[1] == ".inp":

        # Find the line with charge and multiplicity
        while "* xyz" not in line or "* int" not in line:
            line = next(_iter)

        # Read charge and multiplicity
        charge = line.strip().split()[-2]

        # Store the coordinates until next *
        atoms_and_coords = []
        line = next(_iter).strip()
        while len(line.split()) > 1:
            atoms_and_coords.append(line.strip())
            line = next(_iter).strip()
    return atoms_and_coords, charge, mult


def smi_to_mol(
    smi,
    name,
    program,
    log,
    constraints_atoms,
    constraints_dist,
    constraints_angle,
    constraints_dihedral,
):
    smi = smi.split(".")
    if (
        len(smi) > 1
        or len(constraints_atoms) != 0
        or len(constraints_dist) != 0
        or len(constraints_angle) != 0
        or len(constraints_dihedral) != 0
    ):
        if program not in ["crest"]:
            log.write(
                "\nx  Program not supported for conformer generation of complexes! Specify: program='crest' for complexes"
            )
            sys.exit()

        (
            mol,
            constraints_atoms,
            constraints_dist,
            constraints_angle,
            constraints_dihedral,
        ) = nci_ts_mol(
            smi,
            name,
            constraints_atoms,
            constraints_dist,
            constraints_angle,
            constraints_dihedral,
        )

    else:
        params = Chem.SmilesParserParams()
        params.removeHs = False
        try:
            mol = Chem.MolFromSmiles(smi[0], params)
        except Chem.AtomValenceException:
            log.write(
                f"\nx  The SMILES string provided ( {smi[0]} ) contains errors. For example, N atoms from ligands of metal complexes should be N+ since they're drawn with four bonds in ChemDraw, same for O atoms in carbonyl ligands, etc.\n"
            )
            sys.exit()

    return (
        mol,
        constraints_atoms,
        constraints_dist,
        constraints_angle,
        constraints_dihedral,
    )


def rdkit_sdf_read(file, args):
    """
    Reads sdf files and stops the execution if the file was not accesible.                                                                                                                                                                                      rdkit.Chem.Mol objects
    """
    
    inmols = Chem.SDMolSupplier(file, removeHs=False)

    if inmols is None:
        args.log.write(f"Could not open {file}")
        args.log.finalize()
        sys.exit()
    return inmols


def nci_ts_mol(
    smi,
    name,
    constraints_atoms,
    constraints_dist,
    constraints_angle,
    constraints_dihedral,
):
    if constraints_atoms is not None:
        constraints_atoms = [[float(y) for y in x] for x in constraints_atoms]
    if constraints_dist is not None:
        constraints_dist = [[float(y) for y in x] for x in constraints_dist]
        constraints_dist = np.array(constraints_dist)
    if constraints_angle is not None:
        constraints_angle = [[float(y) for y in x] for x in constraints_angle]
        constraints_angle = np.array(constraints_angle)
    if constraints_dihedral is not None:
        constraints_dihedral = [[float(y) for y in x] for x in constraints_dihedral]
        constraints_dihedral = np.array(constraints_dihedral)

    molsH = []
    mols = []
    for m in smi:
        mols.append(Chem.MolFromSmiles(m))
        molsH.append(Chem.AddHs(Chem.MolFromSmiles(m)))

    for m in molsH:
        Chem.EmbedMultipleConfs(m, numConfs=1)
    for m in mols:
        Chem.EmbedMultipleConfs(m, numConfs=1)

    coord = [0.0, 0.0, 5.0]
    molH = molsH[0]
    for i, fragment in enumerate(molsH[1:]):
        offset_3d = Geometry.Point3D(coord[0], coord[1], coord[2])
        molH = Chem.CombineMols(molH, fragment, offset_3d)
        coord[1] += 5
        Chem.SanitizeMol(molH)

    coord = [0.0, 0.0, 5.0]
    mol = mols[0]
    for i, fragment in enumerate(mols[1:]):
        offset_3d = Geometry.Point3D(coord[0], coord[1], coord[2])
        mol = Chem.CombineMols(mol, fragment, offset_3d)
        coord[1] += 5
        Chem.SanitizeMol(mol)
    mol = Chem.AddHs(mol)

    mol = Chem.ConstrainedEmbed(mol, molH)
    rdmolfiles.MolToXYZFile(mol, name + "_crest.xyz")

    atom_map = []
    for atom in mol.GetAtoms():
        atom_map.append(atom.GetAtomMapNum())

    max_map = max(atom_map)
    for a in mol.GetAtoms():
        if a.GetSymbol() == "H":
            max_map += 1
            a.SetAtomMapNum(int(max_map))

    nconstraints_atoms = []
    if constraints_atoms is not None:
        for _, ele in enumerate(constraints_atoms):
            for atom in mol.GetAtoms():
                if ele == atom.GetAtomMapNum():
                    nconstraints_atoms.append(float(atom.GetIdx()) + 1)
        nconstraints_atoms = np.array(nconstraints_atoms)

    nconstraints_dist = []
    if constraints_dist is not None:
        for _, r in enumerate(constraints_dist):
            nr = []
            for _, ele in enumerate(r[:2]):
                for atom in mol.GetAtoms():
                    if ele == atom.GetAtomMapNum():
                        nr.append(float(atom.GetIdx()) + 1)
            nr.append(r[-1])
            nconstraints_dist.append(nr)
        nconstraints_dist = np.array(nconstraints_dist)

    nconstraints_angle = []
    if constraints_angle is not None:

        for _, r in enumerate(constraints_angle):
            nr = []
            for _, ele in enumerate(r[:3]):
                for atom in mol.GetAtoms():
                    if ele == atom.GetAtomMapNum():
                        nr.append(float(atom.GetIdx()) + 1)
            nr.append(r[-1])
            nconstraints_angle.append(nr)
        nconstraints_angle = np.array(nconstraints_angle)

    nconstraints_dihedral = []
    if constraints_dihedral is not None:
        for _, r in enumerate(constraints_dihedral):
            nr = []
            for _, ele in enumerate(r[:4]):
                for atom in mol.GetAtoms():
                    if ele == atom.GetAtomMapNum():
                        nr.append(float(atom.GetIdx()) + 1)
            nr.append(r[-1])
            nconstraints_dihedral.append(nr)
        nconstraints_dihedral = np.array(nconstraints_dihedral)

    return (
        mol,
        nconstraints_atoms,
        nconstraints_dist,
        nconstraints_angle,
        nconstraints_dihedral,
    )


def rules_get_charge(mol, args, type):
    """
    Automatically sets the charge for metal complexes
    """

    C_group = ["C", "Se", "Ge"]
    N_group = ["N", "P", "As"]
    O_group = ["O", "S", "Se"]
    F_group = ["F", "Cl", "Br", "I"]

    M_ligands, N_carbenes, bridge_atoms, neighbours = [], [], [], []
    charge_rules = np.zeros(len(mol.GetAtoms()), dtype=int)
    neighbours, metal_found = [], False
    for i, atom in enumerate(mol.GetAtoms()):
        # get the neighbours of metal atom and calculate the charge of metal center + ligands
        if atom.GetIdx() in args.metal_idx:
            metal_found = True
            charge_idx = args.metal_idx.index(atom.GetIdx())
            neighbours = atom.GetNeighbors()
            charge_rules[i] = args.metal_oxi[charge_idx]
            for neighbour in neighbours:
                M_ligands.append(neighbour.GetIdx())
                if neighbour.GetTotalValence() == 4:
                    if neighbour.GetSymbol() in C_group:
                        carbene_like = False
                        bridge_ligand = False
                        for inside_neighbour in neighbour.GetNeighbors():
                            if inside_neighbour.GetSymbol() in N_group:
                                if inside_neighbour.GetTotalValence() == 4:
                                    for N_neighbour in inside_neighbour.GetNeighbors():
                                        # this option detects bridge ligands that connect two metals such as M--CN--M
                                        # we use I since the M is still represented as I at this point
                                        if N_neighbour.GetSymbol() == "I":
                                            bridge_ligand = True
                                            bridge_atoms.append(
                                                inside_neighbour.GetIdx()
                                            )
                                    if not bridge_ligand:
                                        carbene_like = True
                                        N_carbenes.append(inside_neighbour.GetIdx())
                        if not carbene_like:
                            charge_rules[i] = charge_rules[i] - 1
                elif neighbour.GetTotalValence() == 3:
                    if neighbour.GetSymbol() in N_group:
                        charge_rules[i] = charge_rules[i] - 1
                elif neighbour.GetTotalValence() == 2:
                    if neighbour.GetSymbol() in O_group:
                        nitrone_like = False
                        for inside_neighbour in neighbour.GetNeighbors():
                            if inside_neighbour.GetSymbol() in N_group:
                                nitrone_like = True
                        if not nitrone_like:
                            charge_rules[i] = charge_rules[i] - 1

                elif neighbour.GetTotalValence() == 1:
                    if neighbour.GetSymbol() in F_group:
                        charge_rules[i] = charge_rules[i] - 1

    # for charges not in the metal or ligand
    for i, atom in enumerate(mol.GetAtoms()):
        if atom.GetIdx() not in M_ligands and atom.GetIdx() not in args.metal_idx:
            charge_rules[i] = atom.GetFormalCharge()

    # recognizes charged N and O atoms in metal ligands (added to the first metal of the list as default)
    # this group contains atoms that do not count as separate charge groups (i.e. N from Py ligands)
    if len(neighbours) > 0:
        invalid_charged_atoms = M_ligands + N_carbenes + bridge_atoms
        for atom in mol.GetAtoms():
            if atom.GetIdx() not in invalid_charged_atoms:
                if atom.GetSymbol() in N_group:
                    if atom.GetTotalValence() == 4:
                        charge_rules[0] = charge_rules[0] + 1
                if atom.GetSymbol() in O_group:
                    if atom.GetTotalValence() == 1:
                        charge_rules[0] = charge_rules[0] - 1

    if metal_found:
        if type == "csearch":
            return np.sum(charge_rules)
        if type == "cmin":
            return charge_rules

    # for organic molecules when using a list containing organic and organometallics molecules mixed
    else:
        charge = Chem.GetFormalCharge(mol)
        if type == "csearch":
            return charge, metal_found
        if type == "cmin":
            return charge_rules, metal_found


def substituted_mol(self, mol, checkI):
    """
    Returns a molecule object in which all metal atoms specified in args.metal_atoms
    are replaced by Iodine and the charge is set depending on the number of
    neighbors.

    """

    Neighbors2FormalCharge = dict()
    for i, j in zip(range(2, 9), range(-3, 4)):
        Neighbors2FormalCharge[i] = j

    for atom in mol.GetAtoms():
        symbol = atom.GetSymbol()
        if symbol in self.args.metal_atoms:
            self.args.metal_sym[self.args.metal_atoms.index(symbol)] = symbol
            self.args.metal_idx[self.args.metal_atoms.index(symbol)] = atom.GetIdx()
            self.args.complex_coord[self.args.metal_atoms.index(symbol)] = len(
                atom.GetNeighbors()
            )
            if checkI == "I":
                atom.SetAtomicNum(53)
                n_neighbors = len(atom.GetNeighbors())
                if n_neighbors > 1:
                    formal_charge = Neighbors2FormalCharge[n_neighbors]
                    atom.SetFormalCharge(formal_charge)

    return self.args.metal_idx, self.args.complex_coord, self.args.metal_sym


def getDihedralMatches(mol, heavy):
    # this is rdkit's "strict" pattern
    pattern = r"*~[!$(*#*)&!D1&!$(C(F)(F)F)&!$(C(Cl)(Cl)Cl)&!$(C(Br)(Br)Br)&!$(C([CH3])([CH3])[CH3])&!$([CD3](=[N,O,S])-!@[#7,O,S!D1])&!$([#7,O,S!D1]-!@[CD3]=[N,O,S])&!$([CD3](=[N+])-!@[#7!D1])&!$([#7!D1]-!@[CD3]=[N+])]-!@[!$(*#*)&!D1&!$(C(F)(F)F)&!$(C(Cl)(Cl)Cl)&!$(C(Br)(Br)Br)&!$(C([CH3])([CH3])[CH3])]~*"
    qmol = Chem.MolFromSmarts(pattern)
    matches = mol.GetSubstructMatches(qmol)

    # these are all sets of 4 atoms, uniquify by middle two
    uniqmatches = []
    seen = set()
    for (a, b, c, d) in matches:
        if (b, c) not in seen and (c, b) not in seen:
            if heavy:
                if (
                    mol.GetAtomWithIdx(a).GetSymbol() != "H"
                    and mol.GetAtomWithIdx(d).GetSymbol() != "H"
                ):
                    seen.add((b, c))
                    uniqmatches.append((a, b, c, d))
            if not heavy:
                if (
                    mol.GetAtomWithIdx(c).GetSymbol() == "C"
                    and mol.GetAtomWithIdx(d).GetSymbol() == "H"
                ):
                    pass
                else:
                    seen.add((b, c))
                    uniqmatches.append((a, b, c, d))
    return uniqmatches


def set_metal_atomic_number(mol, metal_idx, metal_sym):
    """
    Changes the atomic number of the metal atoms using their indices.

    Parameters
    ----------
    mol : rdkit.Chem.Mol
        RDKit molecule object
    metal_idx : list
        sorted list that contains the indices of the metal atoms in the molecule
    metal_sym : list
        sorted list (same order as metal_idx) that contains the symbols of the metals in the molecule
    """

    for atom in mol.GetAtoms():
        if atom.GetIdx() in metal_idx:
            re_symbol = metal_sym[metal_idx.index(atom.GetIdx())]
            atomic_number = periodic_table().index(re_symbol)
            atom.SetAtomicNum(atomic_number)


def get_conf_RMS(mol1, mol2, c1, c2, heavy, max_matches_rmsd):
    """
    Takes in two rdkit.Chem.Mol objects and calculates the RMSD between them.
    (As side efect mol1 is left in the aligned state, if heavy is specified
    the side efect will not happen)

    Parameters
    ----------
    mol1 : rdkit.Chem.Mol
        Probe molecule
    mol2 : rdkit.Chem.Mol
        Target molecule. The probe is aligned to the target to compute the RMSD
    c1 : int
        Conformation of mol1 to use for the RMSD
    c2 : int
        Conformation of mol2 to use for the RMSD
    heavy : bool
        If True it will ignore the H atoms when computing the RMSD
    max_matches_rmsd : int
        Max number of matches found in a SubstructMatch()

    Returns
    -------
    float
        Returns the best RMSD found
    """

    if heavy:
        mol1 = RemoveHs(mol1)
        mol2 = RemoveHs(mol2)
    return GetBestRMS(mol1, mol2, c1, c2, maxMatches=max_matches_rmsd)


def command_line_args():
    """
    Load default and user-defined arguments specified through command lines. Arrguments are loaded as a dictionary
    """

    # First, create dictionary with user-defined arguments
    kwargs = {}
    available_args = ["help"]
    bool_args = [
        "verbose",
        "csearch",
        "cmin",
        "qprep",
        "qcorr",
        "qdescp",
        "qpred",
        "metal_complex",
        "time",
        "heavyonly",
        "cregen",
        "lowest_only",
        "lowest_n",
        "chk",
        "dup",
        "fullcheck",
        "rot_dihedral",
        "nmr_online",
        "qsub",
        "qsub_ana",
        "boltz",
    ]

    for arg in var_dict:
        if arg in bool_args:
            available_args.append(f"{arg}")
        else:
            available_args.append(f"{arg} =")

    try:
        opts, _ = getopt.getopt(sys.argv[1:], "h", available_args)
    except getopt.GetoptError as err:
        print(err)
        sys.exit()

    for arg, value in opts:
        if arg.find("--") > -1:
            arg_name = arg.split("--")[1].strip()
        elif arg.find("-") > -1:
            arg_name = arg.split("-")[1].strip()
        if arg_name in bool_args:
            value = True
        if value == "None":
            value = None
        if arg_name in ("h", "help"):
            print(
                "o  AQME is installed correctly! For more information about the available options, see the documentation in https://github.com/jvalegre/aqme"
            )
            sys.exit()
        else:
            kwargs[arg_name] = value

    # Second, load all the default variables as an "add_option" object
    args = load_variables(kwargs, "command")

    return args


def load_variables(kwargs, aqme_module, create_dat=True):
    """
    Load default and user-defined variables
    """

    # first, load default values and options manually added to the function
    self = set_options(kwargs)

    # this part loads variables from yaml files (if varfile is used)
    txt_yaml = ""
    if self.varfile is not None:
        self, txt_yaml = load_from_yaml(self)
    if aqme_module != "command":

        self.initial_dir = Path(os.getcwd())

        if not isinstance(self.files, list):
            self.w_dir_main = os.path.dirname(self.files)
            check_files = os.path.basename(self.files)
        elif len(self.files) != 0:
            self.w_dir_main = os.path.dirname(self.files[0])
        else:
            self.w_dir_main = os.getcwd()

        if (
            Path(f"{self.w_dir_main}").exists()
            and os.getcwd() not in f"{self.w_dir_main}"
        ):
            self.w_dir_main = Path(f"{os.getcwd()}/{self.w_dir_main}")
        else:
            self.w_dir_main = Path(self.w_dir_main)

        if self.isom_type is not None:
            if (
                Path(f"{self.isom_inputs}").exists()
                and os.getcwd() not in f"{self.isom_inputs}"
            ):
                self.isom_inputs = Path(f"{os.getcwd()}/{self.isom_inputs}")
            else:
                self.isom_inputs = Path(self.isom_inputs)

        error_setup = False

        if not self.w_dir_main.exists():
            txt_yaml += "\nx  The PATH specified as input in the w_dir_main option might be invalid! Using current working directory"
            error_setup = True

        if error_setup:
            self.w_dir_main = Path(os.getcwd())

        if not isinstance(self.files, list):
            if not isinstance(self.files, Mol):
                self.files = glob.glob(f"{self.w_dir_main}/{check_files}")
            else:
                self.files = [self.files]

        # start a log file to track the QCORR module
        if create_dat:
            logger_1, logger_2 = "AQME", "data"
            if aqme_module == "qcorr":
                # detects cycle of analysis (0 represents the starting point)
                self.round_num, self.resume_qcorr = check_run(self.w_dir_main)
                logger_1 = "QCORR-run"
                logger_2 = f"{str(self.round_num)}"

            elif aqme_module == "csearch":
                logger_1 = "CSEARCH"

            elif aqme_module == "qprep":
                logger_1 = "QPREP"

            elif aqme_module == "qdescp":
                logger_1 = "QDESCP"
            elif aqme_module == "vismol":
                logger_1 == "VISMOL"

            if txt_yaml not in [
                "",
                f"\no  Importing AQME parameters from {self.varfile}",
                "\nx  The specified yaml file containing parameters was not found! Make sure that the valid params file is in the folder where you are running the code.\n",
            ]:
                self.log = Logger(self.initial_dir / logger_1, logger_2)
                self.log.write(txt_yaml)
                error_setup = True

            if not error_setup:
                if not self.command_line:
                    self.log = Logger(self.initial_dir / logger_1, logger_2)
                else:
                    # prevents errors when using command lines and running to remote directories
                    path_command = Path(f"{os.getcwd()}")
                    self.log = Logger(path_command / logger_1, logger_2)

                self.log.write(
                    f"AQME v {aqme_version} {time_run} \nCitation: {aqme_ref}\n"
                )

                if self.command_line:
                    self.log.write(
                        f"Command line used in AQME: aqme {' '.join([str(elem) for elem in sys.argv[1:]])}\n"
                    )

                if aqme_module in ["qcorr", "qprep", "qdescp", "vismol"]:
                    if len(self.files) == 0:
                        self.log.write(
                            f"x  There are no output files in {self.w_dir_main}\n"
                        )
                        error_setup = True

            if error_setup:
                # this is added to avoid path problems in jupyter notebooks
                self.log.finalize()
                os.chdir(self.initial_dir)
                sys.exit()

    return self


def read_file(initial_dir, w_dir, file):
    """
    Reads through a file and retrieves a list with all the lines.
    """

    os.chdir(w_dir)
    outfile = open(file, "r")
    outlines = outfile.readlines()
    outfile.close()
    os.chdir(initial_dir)

    return outlines


def QM_coords(outlines, min_RMS, n_atoms, program, keywords_line):
    """
    Retrieves atom types and coordinates from QM output files
    """

    atom_types, cartesians, range_lines = [], [], []
    per_tab = periodic_table()
    count_RMS = -1

    if program == "gaussian":
        if "nosymm" in keywords_line.lower():
            target_ori = "Input orientation:"
        else:
            target_ori = "Standard orientation:"

        if min_RMS > -1:
            for i, line in enumerate(outlines):
                if line.find(target_ori) > -1:
                    count_RMS += 1
                if count_RMS == min_RMS:
                    range_lines = [i + 5, i + 5 + n_atoms]
                    break
        else:
            for i in reversed(range(len(outlines))):
                if outlines[i].find(target_ori) > -1:
                    range_lines = [i + 5, i + 5 + n_atoms]
                    break
        if len(range_lines) != 0:
            for i in range(range_lines[0], range_lines[1]):
                massno = int(outlines[i].split()[1])
                if massno < len(per_tab):
                    atom_symbol = per_tab[massno]
                else:
                    atom_symbol = "XX"
                atom_types.append(atom_symbol)
                cartesians.append(
                    [
                        float(outlines[i].split()[3]),
                        float(outlines[i].split()[4]),
                        float(outlines[i].split()[5]),
                    ]
                )

    return atom_types, cartesians


def cclib_atoms_coords(cclib_data):
    """
    Function to convert atomic numbers and coordinate arrays from cclib into
    a format compatible with QPREP.
    """
    atom_numbers = cclib_data["atoms"]["elements"]["number"]
    atom_types = []
    per_tab = periodic_table()
    for atom_n in atom_numbers:
        if atom_n < len(per_tab):
            atom_symbol = per_tab[atom_n]
        else:
            atom_symbol = "XX"
        atom_types.append(atom_symbol)

    cartesians_array = cclib_data["atoms"]["coords"]["3d"]
    cartesians = [
        cartesians_array[i : i + 3] for i in range(0, len(cartesians_array), 3)
    ]

    return atom_types, cartesians


def check_run(w_dir):
    """
    Determines the folder where input files are gonna be generated in QCORR.
    """

    if "failed" in w_dir.as_posix():
        resume_qcorr = True
        for folder in w_dir.as_posix().replace("\\", "/").split("/"):
            if "run_" in folder:
                folder_count = int(folder.split("_")[1]) + 1
    else:
        input_folder = w_dir.joinpath("failed/")
        resume_qcorr = False
        folder_count = 1

        if os.path.exists(input_folder):
            dir_list = os.listdir(input_folder)
            for folder in dir_list:
                if folder.find("run_") > -1:
                    folder_count += 1

    return folder_count, resume_qcorr


def read_xyz_charge_mult(file):
    """
    Reads charge and multiplicity from XYZ files. These parameters should be defined
    in the title lines as charge=X and mult=Y (i.e. FILENAME charge=1 mult=1 Eopt -129384.564)
    """

    charge_xyz, mult_xyz = None, None
    # read charge and mult from xyz files
    with open(file, "r") as F:
        lines = F.readlines()
    for line in lines:
        for keyword in line.strip().split():
            if keyword.lower().find("charge") > -1:
                charge_xyz = int(keyword.split("=")[1])
            elif keyword.lower().find("mult") > -1:
                mult_xyz = int(keyword.split("=")[1])
            elif charge_xyz is not None and mult_xyz is not None:
                break

    if charge_xyz is None:
        charge_xyz = 0
    if mult_xyz is None:
        mult_xyz = 1

    return charge_xyz, mult_xyz


def mol_from_sdf_or_mol_or_mol2(input_file, module):
    """
    mol object from SDF, MOL or MOL2 files
    """

    if module == "qprep":
        # using sanitize=False to avoid reading problems
        mols = Chem.SDMolSupplier(input_file, removeHs=False, sanitize=False)
        return mols

    elif module == "csearch":

        # using sanitize=True in this case, which is recommended for RDKit calculations
        filename = os.path.splitext(input_file)[0]
        extension = os.path.splitext(input_file)[1]

        if extension.lower() == ".pdb":
            input_file = f'{input_file.split(".")[0]}.sdf'
            extension = ".sdf"

        if extension.lower() == ".sdf":
            mols = Chem.SDMolSupplier(input_file, removeHs=False)
        elif extension.lower() == ".mol":
            mols = [Chem.MolFromMolFile(input_file, removeHs=False)]
        elif extension.lower() == ".mol2":
            mols = [Chem.MolFromMol2File(input_file, removeHs=False)]

        IDs, charges, mults = [], [], []

        with open(input_file, "r") as F:
            lines = F.readlines()

        molecule_count = 0
        for i, line in enumerate(lines):
            if line.find(">  <ID>") > -1:
                ID = lines[i + 1].split()[0]
                IDs.append(ID)
            if line.find(">  <Real charge>") > -1:
                charge = lines[i + 1].split()[0]
                charges.append(charge)
            if line.find(">  <Mult>") > -1:
                mult = lines[i + 1].split()[0]
                mults.append(mult)
            if line.find("$$$$") > -1:
                molecule_count += 1
                if molecule_count != len(charges):
                    charges.append(0)
                if molecule_count != len(mults):
                    mults.append(1)

        suppl = []
        for i, mol in enumerate(mols):
            suppl.append(mol)

        if len(IDs) == 0:
            if len(suppl) > 1:
                for i in range(len(suppl)):
                    IDs.append(f"{filename}_{i+1}")
            else:
                IDs.append(filename)

        if len(charges) == 0:
            for i, mol in enumerate(mols):
                charges.append(Chem.GetFormalCharge(mol))
        if len(mults) == 0:
            for i, mol in enumerate(mols):
                NumRadicalElectrons = 0
                for Atom in mol.GetAtoms():
                    NumRadicalElectrons += Atom.GetNumRadicalElectrons()
                TotalElectronicSpin = NumRadicalElectrons / 2
                mult = int((2 * TotalElectronicSpin) + 1)
                mults.append(mult)

        return suppl, charges, mults, IDs

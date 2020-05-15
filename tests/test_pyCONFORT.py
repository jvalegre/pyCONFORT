#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import pytest
import pandas as pd
import subprocess

def read_energies(file): # parses the energies from sdf files - then used to filter conformers
	energies = []
	f = open(file,"r")
	readlines = f.readlines()
	for i in range(len(readlines)):
		if readlines[i].find('>  <Energy>') > -1:
			energies.append(float(readlines[i+1].split()[0]))
	f.close()
	return energies

# The target value is gonna be the number of conformers (n_conf). The other
# parameters are gonna be variables used by DBGEN
@pytest.mark.parametrize("smiles, params_file, n_confs, prefilter_confs_rdkit, filter_confs_rdkit, E_confs, n_confs_xtb, E_confs_xtb",
[
    # Pentane example
    ('pentane.smi', 'params_test1.yaml', 240, 236, 0, [1,2,3,5], 2, [1,2,3,5]),
    # ('pentane.smi', 'params_test2.yaml', 2, [1,2,3,5], 2, [1,2,3,5]),
    # ('pentane.smi', 'params_test3.yaml', 2, [1,2,3,5], 2, [1,2,3,5]),
    # ('pentane.smi', 'params_test4.yaml', 2, [1,2,3,5], 2, [1,2,3,5]),
    # ('pentane.smi', 'params_test5.yaml', 2, [1,2,3,5], 2, [1,2,3,5]),
    # ('pentane.smi', 'params_test6.yaml', 2, [1,2,3,5], 2, [1,2,3,5]),
    # ('pentane.smi', 'params_test7.yaml', 2, [1,2,3,5], 2, [1,2,3,5]),
    # ('pentane.smi', 'params_test8.yaml', 2, [1,2,3,5], 2, [1,2,3,5]),
    # ('pentane.smi', 'params_test9.yaml', 2, [1,2,3,5], 2, [1,2,3,5]),
])

# PARAMETERS TESTED FROM PARAMS_TEST*.YAML FILES:
# sample, rms_threshold, energy_threshold, initial_energy_threshold, auto_sample, ff, ewin, xtb, dihedralscan,

def test_confgen(smiles, params_file, n_conf, E_confs, n_confs_xtb, E_confs_xtb):
    # saves the working directory
    path = os.getcwd()

    # gets into the directory for testing SMILES
    os.chdir(path+'/'+smiles.split('.')[0])

    # Conformer generation using different parameters. It creates a CSV file
    subprocess.run(['python', '-m', 'DBGEN', '--varfile', params_file])

    # Retrieving the generated CSV file
    df_output = pd.read_csv(smiles.split('.')[0]+'-Duplicates Data.csv')

    file = params_file.split('.')[0]

    # tests for RDKit
    # get data of total and duplicated conformers
    test_init_rdkit_confs = df_output['RDKIT-Initial-samples']
    test_prefilter_rdkit_confs = df_output['RDKit-energy-duplicates']
    test_filter_rdkit_confs = df_output['RDKit-RMS-and-energy-duplicates']

    # read the energies of the conformers
    os.chdir(path+'/'+smiles.split('.')[0]+'/RDKit_generated_SDF_files')
    sdf_file_rdkit = Chem.SDMolSupplier(file+'_rdkit.sdf')
    test_rdkit_E_confs = read_energies(file+'_rdkit.sdf')

    assert n_confs == test_init_rdkit_confs
    assert prefilter_confs_rdkit == test_prefilter_rdkit_confs
    assert filter_confs_rdkit == test_filter_rdkit_confs
    # assert E_confs == test_E_confs

    # tests for xtb
    if xtb:
        sdf_file_xtb = smiles.split('.')[0]+'_xtb.sdf'
        sdf_file_xtb = Chem.SDMolSupplier(file_xtb)
        test_E_confs_xtb = read_energies(file_xtb)

        assert n_confs_xtb == test_n_confs_xtb
        assert E_confs_xtb == test_E_confs_xtb

# MISSING CHECKS:
# CHECK THAT THE AUTO FUNCTION IS WORKING
# CHECK THAT CSV GETS THE CORRECT INFO OF NUMBERS AND TIME!
# CHECK COM FILES generation
# CHECK THAT N OF DUPLICATES FOR THE DIFFERENT FILTERS IS ALWAYS THE samE
# CHECK THAT THE METAL PART IS WORKING
# CHECK THAT MULTIPLE METALS ARE COMPATIBLE
# CHECK THAT THE TEMPLATE PART IS WORKING
# CHECK THAT THE EXPEIRMENTAL RULES IS WORKING
# CHECK THAT ANALYSIS IS WORKING FROM ALL THE DIFFERENT FOLDERS (USE SMALL TEST LOG FILES WITH ALL THE TYPE OF ERRORS)
# CHECK THAT AUTOPREP IS WORKING
# CHECK THAT GENECP AND GEN IS WORKING

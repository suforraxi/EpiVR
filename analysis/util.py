#!/usr/bin/python
'''
Utility module run Echobase operations on any given
'''

import os
import json

import nibabel as nib
import numpy as np
from scipy.ndimage import morphology

from Echobase.Common import errors
from Echobase.Network.Metrics.globaltopo import synchronizability
from Echobase.Network.Transforms import lesion

with open('../data/DATA.json') as json_data_file:
    data = json.load(json_data_file)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def get_resected_electrodes(patient_id, dilate_radius=0):
    '''
    Utility function to compute and output labels of all resected electrodes.
    :param patient_id: Patient ID (str)
    :param dilate_radius: Amount of dilation/erosion to apply to resection image.
    :return: list of tuples: (electrode IDs, electrode label)
    '''

    # Initialize output
    resected_electrodes = []

    # Get resection image
    try:
        resection_nii = nib.load(os.path.expanduser(data['PATIENTS'][patient_id]['RESECTION_IMAGE']))
        resection_data = resection_nii.get_data()
        # Threshold and binarize the resection mask
        resection_data[resection_data >= 0.8] = 1
        resection_data[resection_data < 0.8] = 0
        resection_affine = resection_nii.get_affine()
    except KeyError:
        assert isinstance(patient_id, str)
        print 'The PATIENT ID %s is not configured in the DATA JSON config file. ' \
              'Please use a PATIENT ID that is included in the study.' % patient_id
        raise

    # Load electrode labels and generate electrode image
    electrodes = {}
    ele = np.zeros(resection_data.shape)
    radius = 2  # Radius of electrodes
    try:
        # Generate electrode image
        lines = open(os.path.expanduser(data['PATIENTS'][patient_id]['ELECTRODE_LABELS']), 'r').readlines()
        for line in lines:
            electrode_id = int(line.split(',')[0])
            X = int(float(line.split(',')[1]))
            Y = int(float(line.split(',')[2]))
            Z = int(float(line.split(',')[3]))
            electrode_label = line.split(',')[4]
            ele[max(X - radius, 0):min(X + radius, ele.shape[0]), max(Y - radius, 0):min(Y + radius, ele.shape[1]),
            max(Z - radius, 0):min(Z + radius, ele.shape[2])] = electrode_id

            # Keep filling in electrodes dictionary
            electrodes[electrode_id] = electrode_label
    except ValueError:
        print 'The electrode labels is incorrectly formatted. ' \
              'Make sure X, Y, Z are the second, third and forth columns ' \
              'and make sure all coordinates are floating point values.'
        raise
    except KeyError:
        print 'Make sure the data config file has the patient %s and their ELECTRODE_LABELS file path is set.' % patient_id
        raise

    # Erode/Dilate the resection image appropriately
    if dilate_radius > 0:
        resection_data = morphology.binary_dilation(resection_data, iterations=np.abs(dilate_radius))
    elif dilate_radius < 0:
        resection_data = morphology.binary_erosion(resection_data, iterations=np.abs(dilate_radius))

    # Apply the resection image mask and determine which electrodes are still present
    ele_masked = np.multiply(ele, resection_data)
    resected_electrode_ids = np.unique(ele_masked[ele_masked > 0])
    for resected_electrode_id in resected_electrode_ids:
        resected_electrodes.append((str(int(resected_electrode_id)), electrodes[resected_electrode_id]))

    return resected_electrodes

def write_resected_electrodes(patient_id, dilate_radius=0):
    '''

    Utility function to write resected electrode labels to CSV.
    :param patient_id: Patient ID (str)
    :param dilate_radius: Amount of dilation/erosion to apply to resection image.
    :return: None
    '''
    return 1
    # Create suffix for output filename
    if dilate_radius > 0:
        suffix = 'dilate_{}'.format(dilate_radius)
    elif dilate_radius < 0:
        suffix = 'erode_{}'.format(dilate_radius)
    else:
        suffix = '0'

    # Check if already created
    comp_dir = os.path.expanduser(data["COMP_DIR"])
    if os.path.isfile(os.path.join(comp_dir, patient_id, 'aim1/%s_resected_electrodes_%s.csv' % (patient_id, suffix))):
        return

    # Write to CSV file
    open(os.path.join(comp_dir, patient_id, 'aim1/%s_resected_electrodes_%s.csv' % (patient_id, suffix)), 'w').write(
        '\n'.join(map(lambda x: ','.join(x),
                      get_resected_electrodes(patient_id, dilate_radius))))

def region_control(adj, node_list):
    """
    Function for computing control centrality of a subregion, aka resection zone (change in synchronizability)
    Parameters
    ----------
        adj: ndarray, shape (N, N)
            Undirected, symmetric adjacency matrix with N nodes

        node_list: list
            List of node indices to simultaneously remove from the network
    Returns
    -------
        control_vec: ndarray, shape (N,)
            Control centrality based on delta_sync for each of N variates
    """

    # Standard param checks
    errors.check_type(adj, np.ndarray)
    errors.check_dims(adj, 2)
    if not (adj == adj.T).all():
        raise Exception('Adjacency matrix is not undirected and symmetric.')

    # Get data attributes
    n_node = adj.shape[0]

    # Get the original synchronizability
    base_sync = synchronizability(adj)

    for i in xrange(n_node):
        adj_lesion = lesion.node_lesion(adj, node_list)
        lesion_sync = synchronizability(adj_lesion)

    return (lesion_sync-base_sync) / base_sync
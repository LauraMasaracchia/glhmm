"""
Permutation testing from Gaussian Linear Hidden Markov Model
@author: Nick Y. Larsen 2023
"""

import numpy as np
import pandas as pd
import random
import math
import warnings
from tqdm import tqdm
from glhmm.palm_functions import *
from statsmodels.stats import multitest as smt
from sklearn.cross_decomposition import CCA
from collections import Counter
from skimage.measure import label, regionprops
from scipy.stats import ttest_ind, f_oneway, pearsonr, f, norm
from itertools import combinations
from sklearn.model_selection import train_test_split
import os
import re


def test_across_subjects(D_data, R_data, idx_data=None, method="multivariate", Nperm=0, confounds = None, 
                         dict_family = None,  within_group =False, between_groups=False, test_statistics_option=True, 
                         FWER_correction=False, identify_categories=False, category_lim=10, 
                         test_combination=False, predictor_names=[], outcome_names=[], verbose = True):
    """
    Perform permutation testing across subjects. Family structure can be taken into account by inputting "dict_family". To do this, an Exchangeable Block (EB) file must be created and loaded.
    Three options are available to customise the statistical analysis to particular research questions:
        - "multivariate": Perform permutation testing using regression analysis.
        - "univariate": Conduct permutation testing with correlation analysis.
        - "cca": Apply permutation testing using canonical correlation analysis.
        
    Parameters:
    --------------
    D_data (numpy.ndarray): 
        Input data array of shape that can be either a 2D array or a 3D array.
        For 2D, the data is represented as an (n, p) matrix, where n represents 
        the number of subjects, and p represents the number of predictors.
        For a 3D array, it has a shape (T, n, p), where the first dimension 
        represents timepoints, the second dimension represents the number of subjects, 
        and the third dimension represents features. 
        For 3D, permutation testing is performed per timepoint for each subject.              
    R_data (numpy.ndarray): 
        The dependent variable can be either a 2D array or a 3D array. 
        For a 2D array, it has a shape of (n, q), where n represents 
        the number of subjects, and q represents the outcome of the dependent variable.
        For a 3D array, it has a shape (T, n, q), where the first dimension 
        represents timepoints, the second dimension represents the number of subjects, 
        and the third dimension represents a dependent variable.   
        For 3D, permutation testing is performed per timepoint for each subject.     
    idx_data (numpy.ndarray), default=None: 
        An array containing the indices for each group. The array can be either 1D or 2D:
        For a 1D array, a sequence of integers where each integer labels the group number. For example, [1, 1, 1, 1, 2, 2, 2, ..., N, N, N, N, N, N, N, N].
        For a 2D array, each row represents the start and end indices for the trials in a given session, with the format [[start1, end1], [start2, end2], ..., [startN, endN]].              
    method (str, optional), default="multivariate": 
        The statistical method to be used for the permutation test. Valid options are
        "multivariate", "univariate", or "cca".       
        Note: "cca" stands for Canonical Correlation Analysis                                         
    Nperm (int), default=0: 
        Number of permutations to perform.                       
    confounds (numpy.ndarray or None, optional), default=None: 
        The confounding variables to be regressed out from the input data.
        The array should have a shape (n, c), where n is the number of subjects and c is the number of confounding variables. 
        Each column represents a different confound to be controlled for in the analysis.
    dict_family (dict): 
        Dictionary containing family structure information.                          
        - file_location (str): The file location of the family structure data in CSV format.
        - M (numpy.ndarray, optional): The matrix of attributes, which is not typically required.
                                    Defaults to None.
        - CMC (bool, optional), default=False: 
            A flag indicating whether to use the Conditional Monte Carlo method (CMC).
        - EE (bool, optional), default=True: A flag indicating whether to assume exchangeable errors, which allows permutation.  
    within_group (bool, optional), default=False: 
        If True, the function will perform within-group permutation.      
    between_groups (bool, optional), default=False: 
        If True, the function will perform between-group permutation.                                                    
    test_statistics_option (bool, optional), default=True: 
        If True, the function will return the test statistics for each permutation.
    FWER_correction (bool, optional), default=False: 
        Specify whether to perform family-wise error rate (FWER) correction using the MaxT method.
        Note: FWER_correction is not necessary if pval_correction is applied later for multiple comparison p-value correction.                  
    identify_categories: bool or list or numpy.ndarray, optional, default=False
        If True, automatically identify categorical columns. If a list or ndarray, use the provided list of column indices.    
    category_lim : int or None, optional, default=10
        Maximum allowed number of categories for the F-test. Acts as a safety measure for columns 
        with integer values, like age, which may be mistakenly identified as multiple categories.        
    test_combination (bool or str, optional), default=False:
        Apply Non-Parametric Combination (NPC) algorithm to combine multiple p-values into fewer p-values 
        (across rows, across columns or a single p-value)
        Valid options are False, True, "across_rows", or "across_columns".
        When method="multivariate":
            - True (bool): Returns a single p-value (1-by-1).
            - "across_rows" (str): Compute the geometric mean for each of the p rows along the q columns. The multivariate test returns (1-by-q) p-values, and applying "test combination" will give a single p-value (1-by-1).
        When method="univariate":
            - True (bool): Returns a single p-value (1-by-1).
            - "across_rows" (str): Compute the geometric means for each of the p rows along the q columns. Returns one value for each of the rows (1-by-p). 
            - "across_columns" (str): Compute the geometric means for each of the q columns along the p rows. Returns one value for each of the q columns (1-by-q).                       
    predictor_names (list of str, optional):
        Names of the predictor variables (features) used in the analysis. The order of predictor_names should match the order of columns in D_data.
    outcome_names (list of str, optional):
        Names of the outcome variables used in the analysis.
    verbose (bool, optional): 
        If True, display progress messages. If False, suppress progress messages.  
        
    Returns:
    ----------  
    result (dict): 
        A dictionary containing the following keys. Depending on the `test_statistics_option` and `method`, it can return the p-values, 
        correlation coefficients, and test statistics.
        'pval': P-values for the test with shapes based on the method:
            - method=="multivariate": (T, q)
            - method=="univariate": (T, p, q)
            - method=="cca": (T, 1)
        'test_statistics': Test statistics as the permutation distribution if `test_statistics_option` is True, else None.
            - method=="multivariate": (T, Nperm, q)
            - method=="univariate": (T, Nperm, p, q)
            - method=="cca": (T, Nperm, 1)
        'base_statistics': Values of the test statistics calculated on the original, unpermuted data.
        'statistical_measures': A dictionary that identifies each trait/column (q dimension) in the test statistics and specifies its unit.
        'test_type': The type of test, in this case "test_across_subjects",
        'method': The method used for analysis. Valid options are "multivariate", "univariate", or "cca".
        'max_correction': Specifies if FWER has been applied using MaxT, can either output True or False.  
        'Nperm': The number of permutations that has been performed.   
        'test_summary': A dictionary summarising the test results based on the applied method.
    """
    # Initialize variables
    test_type = 'test_across_subjects'
    method = method.lower()
    
    # Ensure Nperm is at least 1
    if Nperm <= 1:
        Nperm = 1
        # Set flag for identifying categories without permutation
        identify_categories = False if method=="univariate" and identify_categories==False else True
        if method == 'cca' and Nperm == 1:
            raise ValueError("CCA does not support parametric statistics. The number of permutations ('Nperm') cannot be set to 1. "
                            "Please increase the number of permutations to perform a valid analysis.")
    

    
    # Check validity of method and data_type
    valid_methods = ["multivariate", "univariate", "cca"]
    validate_condition(method.lower() in valid_methods, "Invalid option specified for 'method'. Must be one of: " + ', '.join(valid_methods))
    
    # Check validity of method
    valid_test_combination = [False, True, "across_columns", "across_rows"]
    validate_condition(test_combination in valid_test_combination, "Invalid option specified for 'test_combination'. Must be one of: " + ', '.join(map(str, valid_test_combination)))
    
    if method=="multivariate" and test_combination is valid_test_combination[2]:
            raise ValueError("method is set to 'multivariate' and 'test_combination' is set to 'across_rows.\n"
                            "The multivariate test will return (1-by-q) p-values, so the test combination can only be across_columns and return a single p-value.\n "
                         "If you want to perform 'test_combination' while doing 'multivariate' then please set 'test_combination' to 'True' or 'across_columns.")

    if FWER_correction and test_combination in [True, "across_columns", "across_rows"]:
       # Raise an exception and stop function execution
        raise ValueError("'FWER_correction' is set to True and 'test_combination' is either True, 'columns', or 'rows'. \n"
                         "Please set 'FWER_correction' to False if you want to apply 'test_combination' or set 'test_combination' to False if you want to run 'FWER_correction'.")
        
    if (within_group or between_groups) and idx_data is None:
        # Raise an exception and stop function execution
        raise ValueError("Cannot perform within-group or between-group permutation without 'idx_data'.\n"
                        "Please provide 'idx_data' to define group boundaries for the permutation.")
  
    if not within_group and not between_groups and idx_data is not None:
        # Raise an exception and stop function execution
        raise ValueError("When providing 'idx_data' to define group boundaries, either 'within_group' or 'between_groups' must be set to True.\n"
                        "If neither is set to True, do not provide 'idx_data' and perform permutation testing across subjects instead.")
    

    # Get indices for permutation
    idx_array = get_indices_array(idx_data) if idx_data is not None and idx_data.ndim == 2 else idx_data.copy() if idx_data is not None else None

    # Check if indices are unique
    _, idx_count =np.unique(idx_array, return_counts=True)  
    unique_diff =np.diff(idx_count)  
    if np.sum(unique_diff) !=0 and between_groups==True:
        # Raise an exception and stop function execution
        raise ValueError("The size of each group need to have a equal size to perform between group permutation\n"
                         "Please provide adjust your 'idx_data' or") 
    del unique_diff, idx_count    
    
    # Get the shapes of the data
    n_T, n_N, n_p, n_q, D_data, R_data = get_input_shape(D_data, R_data, verbose)
    # Note for convension we wrote (T, p, q) => (n_T, n_p, n_q)
    
    # Identify categorical columns in R_data
    category_columns = categorize_columns_by_statistical_method(R_data, method, Nperm, identify_categories, category_lim, test_combination=test_combination) 

    if category_columns["t_test_cols"]!=[] or category_columns["f_anova_cols"]!=[] or category_columns["f_reg_cols"]!=[]:
        if FWER_correction and (len(category_columns.get('t_test_cols')) != R_data.shape[-1] or len(category_columns.get('f_anova_cols')) != R_data.shape[-1] or len(category_columns.get('f_reg_cols')) != R_data.shape[-1]):
            print("Warning: Cannot perform FWER_correction with different test statisticss.\n"
                  "Consider to set identify_categories=False")
            raise ValueError("Cannot perform FWER_correction")  

    # Crate the family structure by looking at the dictionary 
    if dict_family is not None:
        # process dictionary of family structure
        dict_mfam=process_family_structure(dict_family, Nperm) 
        
    
    # Initialize arrays based on shape of data shape and defined options
    pval, base_statistics, test_statistics_list, F_stats_list, t_stats_list = initialize_arrays(n_p, n_q, n_T, method, Nperm, test_statistics_option, test_combination)

    # Custom variable names
    if test_combination is not False:
        n_p = pval.shape[-2]
        n_q = pval.shape[-1]
    predictor_names = [f"State {i+1}" for i in range(n_p)] if predictor_names==[] or len(predictor_names)!=n_p else predictor_names
    outcome_names = [f"Regressor {i+1}" for i in range(n_q)] if outcome_names==[] or len(outcome_names)!=n_q else outcome_names


    # Permutation matrix
    if dict_family is not None and idx_array is None:
        permutation_matrix = __palm_quickperms(dict_mfam["EB"], M=dict_mfam["M"], nP=dict_mfam["nP"], 
                                            CMC=dict_mfam["CMC"], EE=dict_mfam["EE"])
        # Convert the index so it starts from 0
        permutation_matrix -= 1
        
    elif idx_array is None:
        # Get indices for permutation across subjects
        permutation_matrix = permutation_matrix_across_subjects(Nperm, R_data)
        
    elif idx_array is not None:
        if within_group:
            if between_groups:
                # Permutation within and between groups
                permutation_matrix = permutation_matrix_within_and_between_groups(Nperm, Rin, idx_array)
            else:
                # Permutation within trials across sessions (within groups only)
                permutation_matrix = permutation_matrix_across_trials_within_session(Nperm, Rin, idx_array)
        elif between_groups:
            # Permutation across sessions (between groups only)
            permutation_matrix = permutation_matrix_within_subject_across_sessions(Nperm, Rin, idx_array)

    for t in tqdm(range(n_T)) if n_T > 1 & verbose ==True else range(n_T):
        # If confounds exist, perform confound regression on the dependent variables
        D_t, R_t = deconfound_values(D_data[t, :],R_data[t, :], confounds)
        
        # Handle NaN values and update permutation matrix if necessary
        if method in {"multivariate", "cca"}:
            D_t, R_t, nan_mask = remove_nan_values(D_t, R_t, method)
            permutation_matrix_update = (
                update_permutation_matrix(permutation_matrix, nan_mask)
                if np.any(nan_mask)
                else permutation_matrix.copy()
            )
        else:
            permutation_matrix_update = permutation_matrix.copy()
        
        # Create test_statistics based on method
        test_statistics, reg_pinv = initialize_permutation_matrices(method, Nperm, n_p, n_q, D_t, test_combination, category_columns=category_columns)

        for perm in tqdm(range(Nperm)) if n_T == 1 & verbose==True else range(Nperm):
            # Perform permutation on R_t
            Rin = R_t[permutation_matrix_update[:, perm]]
            # Calculate the permutation distribution
            stats_results = test_statistics_calculations(D_t, Rin, perm, test_statistics, reg_pinv, method, category_columns,test_combination)
            base_statistics[t, :] = stats_results["base_statistics"] if perm == 0 and stats_results["base_statistics"] is not None else base_statistics[t, :] 
            pval[t, :] = stats_results["pval_matrix"] if perm == 0 and stats_results["pval_matrix"] is not None else pval[t, :]
            F_stats_list[t, perm, :] = stats_results["F_stats"] if stats_results["F_stats"] is not None else F_stats_list[t, perm, :]
            t_stats_list[t, perm, :] = stats_results["t_stats"] if stats_results["t_stats"] is not None else t_stats_list[t, perm, :]

        if Nperm>1:
            # Calculate p-values
            pval = get_pval(test_statistics, Nperm, method, t, pval, FWER_correction)

        # Output test statistics if it is set to True can be hard for memory otherwise
        if test_statistics_option==True:
            test_statistics_list[t,:] = stats_results["test_statistics"]


    # Remove the first dimension if it is 1
    pval =np.squeeze(pval) 
    base_statistics =np.squeeze(base_statistics) if base_statistics is not None  else []
    test_statistics_list =np.squeeze(test_statistics_list) if test_statistics_list is not None  else []

    # Create report summary
    test_summary =create_test_summary(Rin, base_statistics,pval, predictor_names, outcome_names, method, F_stats_list, t_stats_list,n_T, n_N, n_p,n_q)
    # Change the output to say Nperm=0
    Nperm = 0 if Nperm==1 else Nperm
    # Check if "z_score" exists and keep only that key
    if 'z_score' in category_columns:
        category_columns = {'z_score': category_columns['z_score']}
    else:
        category_columns = {key: value for key, value in category_columns.items() if value}
        if len(category_columns)==1:
            category_columns[next(iter(category_columns))]='all_columns'

    if np.sum(np.isnan(pval)) > 0 and verbose:
        print("Warning: Permutation testing resulted in p-values that are NaN.")
        print("This could indicate an issue with the input data, such as:")
        print("  - More predictors than datapoints.")
        print("  - One or more features having identical values (no variability), making the F-statistic undefined.")
        print("Please review and clean your data before proceeding.")
    
    # Return results
    result = {
        'pval': pval,
        'base_statistics': base_statistics,
        'test_statistics': test_statistics_list,
        'statistical_measures': category_columns,
        'test_type': test_type,
        'method': method,
        'test_combination': test_combination,
        'max_correction':FWER_correction,
        'Nperm': Nperm,
        'test_summary':test_summary}
    return result


def test_across_trials(D_data, R_data, idx_data, method="multivariate", Nperm=0, confounds=None, 
                       test_statistics_option=True, FWER_correction=False, identify_categories=False, category_lim=10, 
                       test_combination=False, predictor_names=[], outcome_names=[], verbose=True):
    """
    Perform permutation testing across different trials within a session. 
    
    Three options are available to customize the statistical analysis to a particular research questions:
        - 'multivariate': Perform permutation testing using regression analysis.
        - 'correlation': Conduct permutation testing with correlation analysis.
        - 'cca': Apply permutation testing using canonical correlation analysis.
             
    Parameters:
    --------------
    D_data (numpy.ndarray): 
        Input data array of shape that can be either a 2D array or a 3D array.
        For 2D, the data is represented as an (n, p) matrix, where n represents 
        the number of trials, and p represents the number of predictors.
        For a 3D array, it has a shape (T, n, p), where the first dimension 
        represents timepoints, the second dimension represents the number of trials, 
        and the third dimension represents features. 
        For 3D, permutation testing is performed per timepoint            
    R_data (numpy.ndarray): 
        The dependent variable can be either a 2D array or a 3D array. 
        For a 2D array, it has a shape of (n, q), where n represents 
        the number of trials, and q represents the outcome of the dependent variable.
        For a 3D array, it has a shape (T, n, q), where the first dimension 
        represents timepoints, the second dimension represents the number of trials, 
        and the third dimension represents a dependent variable.   
        For 3D, permutation testing is performed per timepoint for each subject.                
    idx_data (numpy.ndarray), default=None: 
        An array containing the indices for each group. The array can be either 1D or 2D:
        For a 1D array, a sequence of integers where each integer labels the group number. For example, [1, 1, 1, 1, 2, 2, 2, ..., N, N, N, N, N, N, N, N].
        For a 2D array, each row represents the start and end indices for the trials in a given session, with the format [[start1, end1], [start2, end2], ..., [startN, endN]].              
    method (str, optional), default="multivariate": 
        The statistical method to be used for the permutation test. Valid options are
        "multivariate", "univariate", or "cca".       
        Note: "cca" stands for Canonical Correlation Analysis    
    Nperm (int), default=0: 
        Number of permutations to perform. 
    confounds (numpy.ndarray or None, optional), default=None: 
        The confounding variables to be regressed out from the input data (D_data).
        If provided, the regression analysis is performed to remove the confounding effects.    
    trial_timepoints (int), default=None: 
        Number of timepoints for each trial.                                                         
    test_statistics_option (bool, optional), default=True: 
        If True, the function will return the test statistics for each permutation.
    FWER_correction (bool, optional), default=False: 
        Specify whether to perform family-wise error rate (FWER) correction using the MaxT method.
        Note: FWER_correction is not necessary if pval_correction is applied later for multiple comparison p-value correction.                  
    identify_categories: bool or list or numpy.ndarray, optional, default=False
        If True, automatically identify categorical columns. If a list or ndarray, use the provided list of column indices.      
    category_lim : int or None, optional, default=10
        Maximum allowed number of categories for the F-test. Acts as a safety measure for columns 
        with integer values, like age, which may be mistakenly identified as multiple categories.     
    test_combination (bool or str, optional), default=False:
        Apply Non-Parametric Combination (NPC) algorithm to combine multiple p-values into fewer p-values 
        (across rows, across columns or a single p-value)
        Valid options are False, True, "across_rows", or "across_columns".
        When method="multivariate":
            - True (bool): Returns a single p-value (1-by-1).
            - "across_rows" (str): Compute the geometric mean for each of the p rows along the q columns. The multivariate test returns (1-by-q) p-values, and applying "test combination" will give a single p-value (1-by-1).
        When method="univariate":
            - True (bool): Returns a single p-value (1-by-1).
            - "across_rows" (str): Compute the geometric means for each of the p rows along the q columns. Returns one value for each of the rows (1-by-p). 
            - "across_columns" (str): Compute the geometric means for each of the q columns along the p rows. Returns one value for each of the q columns (1-by-q).                                        
    predictor_names (list of str, optional):
        Names of the predictor variables (features) used in the analysis. The order of predictor_names should match the order of columns in D_data.
    outcome_names (list of str, optional):
        Names of the outcome variables used in the analysis.
    verbose (bool, optional): 
        If True, display progress messages. If False, suppress progress messages. 

    Returns:
    ----------  
    result (dict): 
        A dictionary containing the following keys. Depending on the `test_statistics_option` and `method`, it can return the p-values, 
        correlation coefficients, and test statistics.
        'pval': P-values for the test with shapes based on the method:
            - method=="multivariate": (T, q)
            - method=="univariate": (T, p, q)
            - method=="cca": (T, 1)
        'test_statistics': test statistics is the permutation distribution if `test_statistics_option` is True, else None.
            - method=="multivariate": (T, Nperm, q)
            - method=="univariate": (T, Nperm, p, q)
            - method=="cca": (T, Nperm, 1)
        'base_statistics': Values of the test statistics calculated on the original, unpermuted data.
        'statistical_measures': A dictionary that identifies each trait/column (q dimension) in the test statistics and specifies its unit.
        'test_type': The type of test, in this case "test_across_trials",
        'method': The method used for analysis. Valid options are "multivariate", "univariate", or "cca".
        'max_correction': Specifies if FWER has been applied using MaxT, can either output True or False.  
        'Nperm': The number of permutations that has been performed.   
        'test_summary': A dictionary summarising the test results based on the applied method.
    """
    # Initialize variable
    category_columns = []   
    test_type =  'test_across_trials'
    method = method.lower()
    
    # Ensure Nperm is at least 1
    if Nperm <= 1:
        Nperm = 1
        # Set flag for identifying categories without permutation
        identify_categories = True
        if method == 'cca' and Nperm == 1:
            raise ValueError("CCA does not support parametric statistics. The number of permutations ('Nperm') cannot be set to 1.\n "
                            "Please increase the number of permutations to perform a valid analysis.")

    # Check validity of method and data_type
    valid_methods = ["multivariate", "univariate", "cca"]
    validate_condition(method.lower() in valid_methods, "Invalid option specified for 'method'. Must be one of: " + ', '.join(valid_methods))
    
    # Check validity of method
    valid_test_combination = [False, True, "across_columns", "across_rows"]
    validate_condition(test_combination in valid_test_combination, "Invalid option specified for 'test_combination'. Must be one of: " + ', '.join(map(str, valid_test_combination)))
    
    if method=="multivariate" and test_combination is valid_test_combination[2]:
            raise ValueError("method is set to 'multivariate' and 'test_combination' is set to 'across_rows.\n"
                            "The multivariate test will return (1-by-q) p-values, so the test combination can only be across_rows which is one in this case to single p-value.\n"
                         "If you want to perform 'test_combination' while doing 'multivariate' then please set 'test_combination' to 'True' or 'across_columns.")


    if FWER_correction and test_combination in [True, "across_columns", "across_rows"]:
       # Raise an exception and stop function execution
        raise ValueError("'FWER_correction' is set to True and 'test_combination' is either True, 'columns', or 'rows'.\n "
                         "Please set 'FWER_correction' to False if you want to apply 'test_combination' or set 'test_combination' to False if you want to run 'FWER_correction'.")

    # Get input shape information
    n_T, n_N, n_p, n_q, D_data, R_data = get_input_shape(D_data, R_data, verbose)
    time_FLAG = 0 if n_T ==1 else 1
    # Identify categorical columns in R_data
    category_columns = categorize_columns_by_statistical_method(R_data, method, Nperm, identify_categories, category_lim, test_combination=test_combination)

    if category_columns["t_test_cols"]!=[] or category_columns["f_anova_cols"]!=[] or category_columns["f_reg_cols"]!=[]:
        if FWER_correction and (len(category_columns.get('t_test_cols')) != R_data.shape[-1] or len(category_columns.get('f_anova_cols')) != R_data.shape[-1] or len(category_columns.get('f_reg_cols')) != R_data.shape[-1]):
            print("Warning: Cannot perform FWER_correction with different test statisticss.\n"
                  "Consider to set identify_categories=False")
            raise ValueError("Cannot perform FWER_correction")  
    
    # Get indices for permutation
    if len(idx_data.shape)==2:
        idx_array = get_indices_array(idx_data)
    else:
        idx_array =idx_data.copy()        

    # Initialize arrays based on shape of data shape and defined options
    pval, base_statistics, test_statistics_list, F_stats_list, t_stats_list = initialize_arrays(n_p, n_q, n_T, method, Nperm, test_statistics_option, test_combination)
    permutation_matrix = None

    # Custom variable names
    if test_combination is not False:
        n_p = pval.shape[-2]
        n_q = pval.shape[-1]

    # Define names for the summary statistics
    predictor_names = [f"State {i+1}" for i in range(n_p)] if predictor_names==[] or len(predictor_names)!=n_p else predictor_names
    outcome_names = [f"Regressor {i+1}" for i in range(n_q)] if outcome_names==[] or len(outcome_names)!=n_q else outcome_names

    permutation_matrix = permutation_matrix_across_trials_within_session(Nperm,R_data, idx_array, time_FLAG=time_FLAG) if permutation_matrix is None else permutation_matrix

    for t in tqdm(range(n_T)) if n_T > 1 & verbose ==True else range(n_T):
        # If confounds exist, perform confound regression on the dependent variables
        D_t, R_t = deconfound_values(D_data[t, :],R_data[t, :], confounds)
        
        # Handle NaN values and update permutation matrix if necessary
        if method in {"multivariate", "cca"}:
            D_t, R_t, nan_mask = remove_nan_values(D_t, R_t, method)
            permutation_matrix_update = (
                update_permutation_matrix(permutation_matrix, nan_mask)
                if np.any(nan_mask)
                else permutation_matrix.copy()
            )
        else:
            permutation_matrix_update = permutation_matrix.copy()
        
        # Create test_statistics and the regularized pseudo-inverse of D_data
        test_statistics, reg_pinv = initialize_permutation_matrices(method, Nperm, n_p, n_q, D_t, test_combination, category_columns=category_columns)
       
        for perm in range(Nperm):
            # Perform permutation on R_t
            Rin = R_t[permutation_matrix_update[:, perm]]
            # Calculate the permutation distribution
            stats_results = test_statistics_calculations(D_t, Rin, perm, test_statistics, reg_pinv, method, category_columns,test_combination)
            base_statistics[t, :] = stats_results["base_statistics"] if perm == 0 and stats_results["base_statistics"] is not None else base_statistics[t, :] 
            pval[t, :] = stats_results["pval_matrix"] if perm == 0 and stats_results["pval_matrix"] is not None else pval[t, :]
            F_stats_list[t, perm, :] = stats_results["F_stats"] if stats_results["F_stats"] is not None else F_stats_list[t, perm, :]
            t_stats_list[t, perm, :] = stats_results["t_stats"] if stats_results["t_stats"] is not None else t_stats_list[t, perm, :]

            if Nperm>1:
                # Calculate p-values
                pval = get_pval(test_statistics, Nperm, method, t, pval, FWER_correction)
            
            # Output test statistics if it is set to True can be hard for memory otherwise
            if test_statistics_option==True:
                test_statistics_list[t,:] = test_statistics
        if Nperm>1:
            # Calculate p-values
            pval = get_pval(test_statistics, Nperm, method, t, pval, FWER_correction)
    if Nperm >1 and test_combination is not False:
        category_columns['z_score'] = test_combination
        
    # Remove the first dimension if it is 1
    pval =np.squeeze(pval) 
    base_statistics =np.squeeze(base_statistics) if base_statistics is not None  else []
    test_statistics_list =np.squeeze(test_statistics_list) if test_statistics_list is not None  else []
    
    # Create report summary
    test_summary =create_test_summary(Rin, base_statistics,pval, predictor_names, outcome_names, method, F_stats_list, t_stats_list,n_T, n_N, n_p,n_q)
    
    Nperm = 0 if Nperm==1 else Nperm
    category_columns = {key: value for key, value in category_columns.items() if value}
    if len(category_columns)==1:
        category_columns[next(iter(category_columns))]='all_columns'

    if np.sum(np.isnan(pval))>0 & verbose:
        print("Warning: Permutation testing resulted in p-values equal to NaN.\n")
        print("This may indicate an issue with the input data. Please review your data.")
        
    # Return results
    result = {
        'pval': pval,
        'base_statistics': base_statistics,
        'test_statistics': test_statistics_list,
        'statistical_measures': category_columns,
        'test_type': test_type,
        'method': method,
        'test_combination': test_combination,
        'max_correction':FWER_correction,
        'Nperm': Nperm,
        'test_summary':test_summary}
    
    return result

def test_across_sessions_within_subject(D_data, R_data, idx_data, method="multivariate", Nperm=0, confounds=None, 
                                        test_statistics_option=True, FWER_correction=False, 
                                        test_combination=False, identify_categories=False, 
                                        category_lim=10, predictor_names=[], outcome_names=[], verbose = True):
    """
    Perform permutation testing across sessions, while keeping the trial order the same.

    Three options are available to customize the statistical analysis to a particular research questions:
        - 'multivariate': Perform permutation testing using regression analysis.
        - 'correlation': Conduct permutation testing with correlation analysis.
        - 'cca': Apply permutation testing using canonical correlation analysis.
           
    Parameters:
    --------------
    D_data (numpy.ndarray): 
        Input data array of shape that can be either a 2D array or a 3D array.
        For 2D, the data is represented as an (n, p) matrix, where n represents 
        the number of trials, and p represents the number of predictors.
        For a 3D array, it has a shape (T, n, p), where the first dimension 
        represents timepoints, the second dimension represents the number of trials, 
        and the third dimension represents features. 
        For 3D, permutation testing is performed per timepoint             
    R_data (numpy.ndarray): 
        The dependent variable can be either a 2D array or a 3D array. 
        For a 2D array, it has a shape of (n, q), where n represents 
        the number of trials, and q represents the outcome of the dependent variable.
        For a 3D array, it has a shape (T, n, q), where the first dimension 
        represents timepoints, the second dimension represents the number of trials, 
        and the third dimension represents a dependent variable.   
        For 3D, permutation testing is performed per timepoint for each subject.                
    idx_data (numpy.ndarray):           
        An array containing the indices for each group. The array can be either 1D or 2D:
        For a 1D array, a sequence of integers where each integer labels the group number. For example, [1, 1, 1, 1, 2, 2, 2, ..., N, N, N, N, N, N, N, N].
        For a 2D array, each row represents the start and end indices for the trials in a given session, with the format [[start1, end1], [start2, end2], ..., [startN, endN]].    
    method (str, optional), default="multivariate": 
        The statistical method to be used for the permutation test. Valid options are
        "multivariate", "univariate", or "cca".
        Note: "cca" stands for Canonical Correlation Analysis    
    Nperm (int), default=0: 
        Number of permutations to perform. 
    confounds (numpy.ndarray or None, optional), default=None: 
        The confounding variables to be regressed out from the input data (D_data).
        If provided, the regression analysis is performed to remove the confounding effects.                                                                                       
    test_statistics_option (bool, optional), default=True: 
        If True, the function will return the test statistics for each permutation.
    FWER_correction (bool, optional), default=False: 
        Specify whether to perform family-wise error rate (FWER) correction using the MaxT method.
        Note: FWER_correction is not necessary if pval_correction is applied later for multiple comparison p-value correction. 
    test_combination (bool or str, optional), default=False:
        Apply Non-Parametric Combination (NPC) algorithm to combine multiple p-values into fewer p-values 
        (across rows, across columns or a single p-value)
        Valid options are False, True, "across_rows", or "across_columns".
        When method="multivariate":
            - True (bool): Returns a single p-value (1-by-1).
            - "across_rows" (str): Compute the geometric mean for each of the p rows along the q columns. The multivariate test returns (1-by-q) p-values, and applying "test combination" will give a single p-value (1-by-1).
        When method="univariate":
            - True (bool): Returns a single p-value (1-by-1).
            - "across_rows" (str): Compute the geometric means for each of the p rows along the q columns. Returns one value for each of the rows (1-by-p). 
            - "across_columns" (str): Compute the geometric means for each of the q columns along the p rows. Returns one value for each of the q columns (1-by-q).                                        
    identify_categories: bool or list or numpy.ndarray, optional, default=False
        If True, automatically identify categorical columns. If a list or ndarray, use the provided list of column indices.      
    category_lim : int or None, optional, default=10
        Maximum allowed number of categories for the F-test. Acts as a safety measure for columns 
        with integer values, like age, which may be mistakenly identified as multiple categories.
    predictor_names (list of str, optional):
        Names of the predictor variables (features) used in the analysis. The order of predictor_names should match the order of columns in D_data.
    outcome_names (list of str, optional):
        Names of the outcome variables used in the analysis.   
    verbose (bool, optional), default=False: 
        If True, display progress messages and prints. If False, suppress messages.                            
    
    Returns:
    ----------  
    result (dict): 
        A dictionary containing the following keys. Depending on the `test_statistics_option` and `method`, it can return the p-values, 
        correlation coefficients, test statistics.
        'pval': P-values for the test with shapes based on the method:
            - method=="multivariate": (T, q)
            - method=="univariate": (T, p, q)
            - method=="cca": (T, 1)
        'test_statistics': test statistics is the permutation distribution if `test_statistics_option` is True, else None.
            - method=="multivariate": (T, Nperm, q)
            - method=="univariate": (T, Nperm, p, q)
            - method=="cca": (T, Nperm, 1)
        'base_statistics': Values of the test statistics calculated on the original, unpermuted data.
        'statistical_measures': A dictionary that identifies each trait/column (q dimension) in the test statistics and specifies its unit.
        'test_type': The type of test, in this case "test_across_sessions",
        'method': The method used for analysis. Valid options are "multivariate", "univariate", or "cca".
        'max_correction': Specifies if FWER has been applied using MaxT, can either output True or False.  
        'Nperm': The number of permutations that has been performed.   
        'test_summary': A dictionary summarising the test results based on the applied method.
                  
    """ 
    # Initialize variable
    category_columns = []  
    test_type = 'test_across_sessions'  
    method = method.lower()
    permute_beta = True # For across session test we are permuting the beta coefficients for each session
     
    # Ensure Nperm is at least 1
    if Nperm <= 1:
        Nperm = 1
        # Set flag for identifying categories without permutation
        identify_categories = True
        if method == 'cca' and Nperm == 1:
            raise ValueError("CCA does not support parametric statistics. The number of permutations ('Nperm') cannot be set to 1. "
                            "Please increase the number of permutations to perform a valid analysis.")

     
    # Check validity of method and data_type
    valid_methods = ["multivariate", "univariate", "cca"]
    validate_condition(method.lower() in valid_methods, "Invalid option specified for 'method'. Must be one of: " + ', '.join(valid_methods))
    
    # Check validity of method
    valid_test_combination = [False, True, "across_columns", "across_rows"]
    validate_condition(test_combination in valid_test_combination, "Invalid option specified for 'test_combination'. Must be one of: " + ', '.join(map(str, valid_test_combination)))
    
    if method=="multivariate" and test_combination is valid_test_combination[2]:
            raise ValueError("method is set to 'multivariate' and 'test_combination' is set to 'across_rows.\n"
                            "The multivariate test will return (1-by-q) p-values, so the test combination can only be across_columns and return a single p-value.\n "
                         "If you want to perform 'test_combination' while doing 'multivariate' then please set 'test_combination' to 'True' or 'across_columns.")

    if FWER_correction and test_combination in [True, "across_columns", "across_rows"]:
       # Raise an exception and stop function execution
        raise ValueError("'FWER_correction' is set to True and 'test_combination' is either True, 'columns', or 'rows'.\n "
                         "Please set 'FWER_correction' to False if you want to apply 'test_combination' or set 'test_combination' to False if you want to run 'FWER_correction'.")
        
    # Get indices of the sessions
    idx_array = get_indices_array(idx_data)

    # Calculate the maximum number of permutations
    max_permutations = math.factorial(len(np.unique(idx_array)))
    # Using scientific notation format with string formatting
    exp_notation = "{:.2e}".format(max_permutations)
    if Nperm > max_permutations:
        warnings.warn(f"Maximum number of permutations with {len(np.unique(idx_array))} sessions is: {exp_notation}. \n"
                    "Reduce the number of permutations to the maximum number of permutations to run the test properly.")
    if verbose:
        print(f"Maximum number of permutations with {len(np.unique(idx_array))} sessions is: {exp_notation}")
    
    # Get input shape information
    n_T, n_N, n_p, n_q, D_data, R_data = get_input_shape(D_data, R_data, verbose)

    # Identify categorical columns in R_data
    category_columns = categorize_columns_by_statistical_method(R_data, method, Nperm, identify_categories, category_lim, permute_beta, test_combination)

    # Initialize arrays based on shape of data shape and defined options
    pval, base_statistics, test_statistics_list, F_stats_list, t_stats_list = initialize_arrays(n_p, n_q, n_T, method, Nperm, test_statistics_option, test_combination)

    # Custom variable names
    if test_combination is not False:
        n_p = pval.shape[-2]
        n_q = pval.shape[-1]
    predictor_names = [f"State {i+1}" for i in range(n_p)] if predictor_names==[] or len(predictor_names)!=n_p else predictor_names
    outcome_names = [f"Regressor {i+1}" for i in range(n_q)] if outcome_names==[] or len(outcome_names)!=n_q else outcome_names
    # Divide the sessions into two dataset to avoid overfit
    train_indices_list, test_indices_list, nan_R =train_test_indices(R_data, idx_data,  category_lim) 

    for t in tqdm(range(n_T)) if n_T > 1 & verbose==True else range(n_T):
        # If confounds exist, perform confound regression on the dependent variables
        D_t, R_t = deconfound_values(D_data[t, :],R_data[t, :], confounds)
        # Removing rows that contain nan-values
        D_t, R_t, nan_mask = remove_nan_values(D_t, R_t, method, test_type)
        idx_data_update =update_indices(nan_mask, idx_data) if np.any(nan_mask) else idx_data.copy()

        # Update test and train indices
        if np.any(nan_mask) and np.array_equal(nan_R, nan_mask)==False:
            # Keep elements only that are True (i.e., remove False)
            nan_mask =(nan_R | nan_mask)
            # Get the indices corresponding to NaN values
            indices = np.arange(len(nan_mask))
            nan_indices = indices[nan_mask]
            # Update indices due to NaN values in D_matrix
            train_indices_list_update, test_indices_list_update= train_test_update_indices(train_indices_list, test_indices_list, nan_indices)

        else:
            # Just use the original test and train indices
            test_indices_list_update = test_indices_list.copy()
            train_indices_list_update = train_indices_list.copy()
            
        # Create test_statistics and pval_perms based on method
        test_statistics, reg_pinv = initialize_permutation_matrices(method, Nperm, n_p, n_q, D_t, test_combination, permute_beta, category_columns)
        
        # Calculate the beta coefficient of each session
        beta, _, _ = calculate_beta_session(reg_pinv, R_t, idx_data_update, permute_beta, category_lim, test_indices_list_update, train_indices_list_update)

        for perm in range(Nperm):
            # Calculate the permutation distribution
            idx_data_in_test =get_indices_from_list(test_indices_list_update)
            stats_results = test_statistics_calculations(D_t, R_t, perm, test_statistics, reg_pinv, method, category_columns, test_combination, idx_data_in_test, permute_beta, beta, test_indices_list_update)
            base_statistics[t, :] = stats_results["base_statistics"] if perm == 0 and stats_results["base_statistics"] is not None else base_statistics[t, :] 
            pval[t, :] = stats_results["pval_matrix"] if perm == 0 and stats_results["pval_matrix"] is not None else pval[t, :]
            F_stats_list[t, perm, :] = stats_results["F_stats"] if stats_results["F_stats"] is not None else F_stats_list[t, perm, :]
            t_stats_list[t, perm, :] = stats_results["t_stats"] if stats_results["t_stats"] is not None else t_stats_list[t, perm, :]
        if Nperm>1:
            # Calculate p-values
            pval = get_pval(test_statistics, Nperm, method, t, pval, FWER_correction)
            
            # Output test statistics if it is set to True can be hard for memory otherwise
            if test_statistics_option==True:
                test_statistics_list[t,:] = test_statistics
  
    # Remove the first dimension if it is 1
    pval =np.squeeze(pval) 
    base_statistics =np.squeeze(base_statistics) if base_statistics is not None  else []
    test_statistics_list =np.squeeze(test_statistics_list) if test_statistics_list is not None  else []

    # Create report summary
    test_summary =create_test_summary(R_data, base_statistics,pval, predictor_names, outcome_names, method, F_stats_list, t_stats_list,n_T, n_N, n_p,n_q, test_indices_list)

    Nperm = 0 if Nperm==1 else Nperm    
    category_columns = {key: value for key, value in category_columns.items() if value}
    if len(category_columns)==1:
        category_columns[next(iter(category_columns))]='all_columns'

    if np.isscalar(pval) is True:
        print("Exporting the base statistics only")
    elif np.sum(np.isnan(pval))>0 & verbose:
        print("Warning: Permutation testing resulted in p-values equal to NaN.\n")
        print("This may indicate an issue with the input data. Please review your data.")
              
    # Return results
    result = {
        'pval': pval,
        'base_statistics': base_statistics,
        'test_statistics': test_statistics_list,
        'test_type': test_type,
        'method': method,
        'test_combination': test_combination,
        'max_correction':FWER_correction,
        'statistical_measures': category_columns,
        'Nperm': Nperm,
        'test_summary':test_summary}
    
    return result

def test_across_state_visits(D_data, R_data , method="multivariate", Nperm=0, confounds=None, 
                             test_statistics_option=True, pairwise_statistic ="mean",
                             FWER_correction=False, category_lim=10, identify_categories = False, 
                             vpath_surrogates=None, state_com="larger", predictor_names=[], outcome_names=[], verbose = True):
    """
    Perform permutation testing across Viterbi path for continuous data.
    
    Parameters:
    --------------    
    D_data (numpy.ndarray): 
        The Viterbi path can be either a 2D or 1D array:
        - For 2D, it is one-hot encoded for each state at every timepoint, with shape (n, p), where n is the number of samples (n_timepoints x n_sessions), 
        and p represents the number of states.
        - For 1D, it is a discrete state value array with shape (n,), where n is the number of samples (n_timepoints x n_sessions), and each value represents a given state.        
    R_data (numpy.ndarray): 
        Physiological signal measurements with shape (n, q), where n is the number of samples (n_timepoints x n_sessions), 
        and q represents dependent/target variables.
        For multivariate methods, this represents multiple dependent variables recorded simultaneously.                               
    method (str, optional), default="multivariate":     
        Statistical method for the permutation test. Valid options are 
        "multivariate", "univariate", "cca", "osr" or "osa". 
        Note: "cca" stands for Canonical Correlation Analysis.   
    Nperm (int), default=0:                
        Number of permutations to perform
    test_statistics_option (bool, optional), default=True: 
        If True, the function will return the test statistics for each permutation.
    pairwise_statistic (str, optional), default="mean":  
        The chosen statistic when applying methods one-state-vs-the-rest (osr) or one-state-vs-another-state (osa). 
        Valid options are "mean" or "median".
    FWER_correction (bool, optional), default=False: 
        Specify whether to perform family-wise error rate (FWER) correction for multiple comparisons using the MaxT method.
        Note: FWER_correction is not necessary if pval_correction is applied later for multiple comparison p-value correction.
    category_lim : int or None, optional, default=None
        Maximum allowed number of categories for F-test. Acts as a safety measure for columns 
        with integer values, like age, which may be mistakenly identified as multiple categories.                   
    state_com (str, optional), default="larger":  
        Only affects the osr test. Choose whether the signal of a state is either larger or smaller than the mean/median signal size of the remaining states. 
        Valid options are "larger" or "smaller".
    verbose (bool, optional): 
        If True, display progress messages. If False, suppress progress messages.

    Returns:
    ----------  
    result (dict):  A dictionary containing the following keys. Depending on the `test_statistics_option` and `method`, it can return the p-values and test statistics.
        'pval': P-values for the test with shapes based on the method:
            - method=="multivariate": (T, q)
            - method=="univariate": (T, p, q)
            - method=="cca": (T, 1)
            - method=="osr": (T, p, 1)
            - method=="osa": (T, p, p)
        'base_statistics': Values of the test statistics calculated on the original, unpermuted data and got the same shape as 'pval'.
        'test_statistics': test statistics is the permutation distribution if `test_statistics_option` is True, else None.
            - method=="multivariate": (T, Nperm, q)
            - method=="univariate": (T, Nperm, p, q)
            - method=="cca": (T, Nperm, 1)
            - method=="osr": (T, Nperm, p)
            - method=="osa": (T, Nperm, p, p)
        'statistical_measures': A dictionary that identifies each trait/column (q dimension) in the test statistics and specifies its unit.
        'test_type': The type of test, in this case "test_across_viterbi_path".
        'method': The method used for analysis. Valid options are "multivariate", "univariate", "cca", "osr", or "osa".
        'max_correction': Specifies if FWER has been applied using MaxT, can either output True or False.
        'Nperm': The number of permutations that has been performed.
        'test_summary': A dictionary summarising the test results based on the applied method.
    """
    # Initialize variables
    test_type = 'test_across_state_visits'
    method = method.lower()
    if vpath_surrogates is not None:
        # Define Nperm if vpath_surrogates is provided
        Nperm = vpath_surrogates.shape[-1]

    # Ensure Nperm is at least 1
    if Nperm <= 1:
        Nperm = 1
        # Set flag for identifying categories without permutation
        identify_categories = True
        if method == 'cca' or method =='osr' or method =='osa' and Nperm == 1:
            raise ValueError("'cca', 'osr' and 'osa' does not support parametric statistics. The number of permutations ('Nperm') cannot be set to 1. "
                            "Please increase the number of permutations to perform a valid analysis.")
             
    # Check if the Viterbi path is correctly constructed
    if vpath_check_2D(D_data) == False:
        raise ValueError(
            "'D_data' is not correctly formatted. Ensure that the Viterbi path is correctly positioned within the target matrix (R). "
            "The data should be one-hot encoded if it's 2D, or an array of integers if it's 1D. "
            "Please verify your input to the 'test_across_state_visits' function."
        )
    # Check validity of method
    valid_state_com = ["larger", "smaller"]
    validate_condition(state_com.lower() in valid_state_com, "Invalid option specified for 'state_com'. Must be one of: " + ', '.join(valid_state_com))
    
    # Check validity of method
    valid_methods = ["multivariate", "univariate", "cca", "osr", "osa"]
    validate_condition(method.lower() in valid_methods, "Invalid option specified for 'method'. Must be one of: " + ', '.join(valid_methods))
    
    valid_statistic = ["mean", "median"]
    validate_condition(pairwise_statistic.lower() in valid_statistic, "Invalid option specified for 'statistic'. Must be one of: " + ', '.join(valid_statistic))
    
    # Convert vpath from matrix to vector
    vpath_array=generate_vpath_1D(D_data)
    if D_data.ndim == 1:
        vpath_bin = np.zeros((len(D_data), len(np.unique(D_data))))
        vpath_bin[np.arange(len(D_data)), D_data - 1] = 1
        D_data = vpath_bin.copy()
    
    # Number of states
    n_states = len(np.unique(vpath_array))
    
    # Get input shape information
    n_T, n_N, n_p, n_q, vpath_data, R_data= get_input_shape(D_data, R_data , verbose)  

    # Identify categorical columns in R_data
    category_columns = categorize_columns_by_statistical_method(R_data, method, Nperm, identify_categories, category_lim,pairwise_statistic=pairwise_statistic)
    
    # Identify categorical columns
    if category_columns["t_test_cols"]!=[] or category_columns["f_anova_cols"]!=[]:
        if FWER_correction and (len(category_columns.get('t_test_cols')) != vpath_data.shape[-1] or len(category_columns.get('f_anova_cols')) != vpath_data.shape[-1]):
            print("Warning: Cannot perform FWER_correction with different test statisticss.\nConsider to set identify_categories=False")
            raise ValueError("Cannot perform FWER_correction")    
   
    # Initialize arrays based on shape of data shape and defined options
    pval, base_statistics, test_statistics_list, F_stats_list, t_stats_list = initialize_arrays(n_p, n_q,n_T, method, Nperm, test_statistics_option)

    # Custom variable names
    predictor_names = [f"State {i+1}" for i in range(n_states)] if predictor_names==[] or len(predictor_names)!=n_states else predictor_names
    outcome_names = [f"Regressor {i+1}" for i in range(pval.shape[-1])] if outcome_names==[] or len(outcome_names)!=pval.shape[-1] else outcome_names

    # Print tqdm over n_T if there are more than one timepoint
    for t in tqdm(range(n_T)) if n_T > 1 & verbose==True else range(n_T):
        # Correct for confounds and center data_t
        data_t, _ = deconfound_values(R_data[t, :],None, confounds)

        # Removing rows that contain nan-values
        if method == "multivariate" or method == "cca":
            if vpath_surrogates is None:
                vpath_array, data_t, _ = remove_nan_values(vpath_array, data_t, method)
            else:
                vpath_surrogates, data_t, _ = remove_nan_values(vpath_surrogates, data_t, method)
        
        if method != "osa":
            ###################### Permutation testing for other tests beside state pairs #################################
            # Create test_statistics and pval_perms based on method
            test_statistics, reg_pinv = initialize_permutation_matrices(method, Nperm, n_p, n_q, vpath_data[0,:,:], category_columns=category_columns)
            # Perform permutation testing
            for perm in tqdm(range(Nperm)) if n_T == 1 & verbose==True else range(n_T):
                # Redo vpath_surrogate calculation if the number of states are not the same (out of 1000 permutations it happens maybe 1-2 times with this demo dataset)
                
                if vpath_surrogates is None:
                    while True:
                        # Create vpath_surrogate
                        vpath_surrogate = surrogate_state_time(perm, vpath_array, n_states)
                        if len(np.unique(vpath_surrogate)) == n_states:
                            break  # Exit the loop if the condition is satisfied
                else:
                    vpath_surrogate = vpath_surrogates[:,perm].astype(int)
                        
                if method =="osr":
                    for state in range(1, n_states+1):
                        test_statistics[perm,state -1] =calculate_baseline_difference(vpath_surrogate, data_t, state, pairwise_statistic.lower(), state_com)

                elif method =="multivariate":
                    # Make vpath to a binary matrix
                    vpath_surrogate_binary = np.zeros((len(vpath_surrogate), len(np.unique(vpath_surrogate))))
                    # Set the appropriate positions to 1
                    vpath_surrogate_binary[np.arange(len(vpath_surrogate)), vpath_surrogate - 1] = 1
                    stats_results = test_statistics_calculations(vpath_surrogate_binary,data_t, perm,test_statistics, reg_pinv, method, category_columns)
                    base_statistics[t, :] = stats_results["base_statistics"] if perm == 0 and stats_results["base_statistics"] is not None else base_statistics[t, :] 
                    pval[t, :] = stats_results["pval_matrix"] if perm == 0 and stats_results["pval_matrix"] is not None else pval[t, :]
                    if stats_results["t_stats"] is not None:
                        t_stats_list[t,perm,:] = stats_results["t_stats"]
                else:
                    # Univariate test
                    # Apply 1 hot encoding
                    vpath_surrogate_onehot = viterbi_path_to_stc(vpath_surrogate,n_states)
                    # Apply t-statistic on the vpath_surrogate
                    stats_results = test_statistics_calculations(vpath_surrogate_onehot, data_t , perm, test_statistics, reg_pinv, method, category_columns)
                    base_statistics[t, :] = stats_results["base_statistics"] if perm == 0 and stats_results["base_statistics"] is not None else base_statistics[t, :] 
                    pval[t, :] = stats_results["pval_matrix"] if perm == 0 and stats_results["pval_matrix"] is not None else pval[t, :]
            if Nperm>1:
                # Calculate p-values
                pval = get_pval(test_statistics, Nperm, method, t, pval, FWER_correction)
        ###################### Permutation testing for state pairs #################################
        elif method =="osa":
            # Run this code if it is "osa"
            # Generates all unique combinations of length 2 
            pairwise_comparisons = list(combinations(range(1, n_states + 1), 2))
            test_statistics = np.zeros((Nperm, len(pairwise_comparisons)))
            pval = np.zeros((n_states, n_states))
            # Iterate over pairwise state comparisons
            
            for idx, (state_1, state_2) in tqdm(enumerate(pairwise_comparisons), total=len(pairwise_comparisons), desc="Pairwise comparisons") if verbose ==True else enumerate(pairwise_comparisons):    
                # Generate surrogate state-time data and calculate differences for each permutation
                for perm in range(Nperm):
                    
                    if vpath_surrogates is None:
                        while True:
                            # Create vpath_surrogate
                            vpath_surrogate = surrogate_state_time(perm, vpath_array, n_states)
                            if len(np.unique(vpath_surrogate)) == n_states:
                                break  # Exit the loop if the condition is satisfied
                    else:
                        vpath_surrogate = vpath_surrogates[:,perm].astype(int)
                        
                    test_statistics[perm,idx] = calculate_statepair_difference(vpath_surrogate, data_t, state_1, 
                                                                               state_2, pairwise_statistic)
                
                if Nperm>1:
                    p_val= np.sum(test_statistics[:,idx] >= test_statistics[0,idx], axis=0) / (Nperm + 1)
                    pval[state_1-1, state_2-1] = p_val
                    pval[state_2-1, state_1-1] = 1 - p_val
            # Fill numbers in base statistics
            if  np.sum(base_statistics[t, :])==0:
                base_statistics[t, :] =test_statistics[0,:]
                
        if test_statistics_option:
            test_statistics_list[t, :] = test_statistics

    # Remove the first dimension if it is 1
    pval =np.squeeze(pval) 
    base_statistics =np.squeeze(base_statistics) if base_statistics is not None  else []
    test_statistics_list =np.squeeze(test_statistics_list) if test_statistics_list is not None  else []

    # Create report summary
    test_summary =create_test_summary(R_data, base_statistics,pval, predictor_names, outcome_names, method, F_stats_list, t_stats_list,n_T, n_N, n_p,n_q)
    if method =="osr":
        test_summary["state_com"] = state_com 
    if method =="osa":
        test_summary["pairwise_comparisons"] =pairwise_comparisons
        
    Nperm = 0 if Nperm==1 else Nperm
    
    category_columns = {key: value for key, value in category_columns.items() if value}
    if len(category_columns)==1:
        category_columns[next(iter(category_columns))]='all_columns'

    if np.sum(np.isnan(pval))>0 & verbose:
        print("Warning: Permutation testing resulted in p-values equal to NaN.")
        print("This may indicate an issue with the input data. Please review your data.")
        
    # Return results
    result = {
        'pval': pval,
        'base_statistics': base_statistics,
        'test_statistics': test_statistics_list,
        'statistical_measures': category_columns,
        'test_type': test_type,
        'method': method,
        'max_correction':FWER_correction,
        'Nperm': Nperm,
        'test_summary':test_summary}
    return result

def remove_nan_values(D_data, R_data, method, test_type=None):
    """
    Remove rows with NaN values from input data arrays.

    Parameters:
    -----------
    D_data (numpy.ndarray)
        Input data array containing features.
    R_data (numpy.ndarray): 
        Input data array containing response values.
    method (str, optional), default="multivariate":     
        Statistical method for the permutation test. Valid options are 
        "multivariate", "univariate", "cca", "osr" or "osa". 
        Note: "cca" stands for Canonical Correlation Analysis.   
    
    Returns:
    ---------
    D_data (numpy.ndarray): 
        Cleaned feature data (D_data) with NaN values removed.  
    R_data (numpy.ndarray): 
        Cleaned response data (R_data) with NaN values removed.
    nan_mask(bool)
        Array that mask the position of the NaN values with True and False for non-nan values
    """
    FLAG = 0
    # removed_indices = None
    
    if R_data.ndim == 1:
        FLAG = 1
        R_data = R_data.reshape(-1,1) 
    if method == "multivariate" and test_type!="test_across_sessions":
        # When applying "multivariate" we need to remove rows for our D_data, as we cannot use it as a predictor for
        # Check for NaN values and remove corresponding rows
        nan_mask = np.isnan(np.expand_dims(D_data,axis=1)).any(axis=1) if D_data.ndim==1 else np.isnan(D_data).any(axis=1)
        # nan_mask = np.isnan(D_data).any(axis=1)
        # Get indices or rows that have been removed
        # removed_indices = np.where(nan_mask)[0]
        D_data = D_data[~nan_mask]
        R_data = R_data[~nan_mask]
    elif method== "cca" or test_type=="test_across_sessions":
        # When applying cca we need to remove rows at both D_data and R_data
        # Check for NaN values and remove corresponding rows
        nan_mask = np.isnan(D_data).any(axis=1) | np.isnan(R_data).any(axis=1)
        # Remove nan indices
        D_data = D_data[~nan_mask]
        R_data = R_data[~nan_mask]
    if FLAG ==1:
        # Flatten R_data
        R_data =R_data.flatten()
    return D_data, R_data, nan_mask

def validate_condition(condition, error_message):
    """
    Validates a given condition and raises a ValueError with the specified error message if the condition is not met.

    Parameters:
    --------------
    condition (bool): 
        The condition to check.
    error_message (str): 
        The error message to raise if the condition is not met.
    """
    # Check if a condition is False and raise a ValueError with the given error message
    if not condition:
        raise ValueError(error_message)


def get_input_shape(D_data, R_data, verbose):
    """
    Computes the input shape parameters for permutation testing.

    Parameters:
    --------------
    D_data (numpy.ndarray): 
        The input data array.
    R_data (numpy.ndarray): 
        The dependent variable.
    verbose (bool): 
        If True, display progress messages. If False, suppress progress messages.

    Returns:
    ----------  
    n_T (int): 
        The number of timepoints.
    n_ST (int): 
        The number of subjects or trials.
    n_p (int): 
        The number of features.
    D_data (numpy.ndarray): 
        The updated input data array.
    R_data (numpy.ndarray): 
        The updated dependent variable.
    """
    # Get the input shape of the data and perform necessary expansions if needed
    if R_data.ndim == 1:
        R_data = np.expand_dims(R_data, axis=1)
    
    if len(D_data.shape) == 1:
        D_data = np.expand_dims(D_data, axis=1)
        D_data = np.expand_dims(D_data, axis=0)
        R_data = np.expand_dims(R_data, axis=0)
        n_T, n_ST, n_p = D_data.shape
        n_q = R_data.shape[-1]
    elif len(D_data.shape) == 2:
        # Performing permutation testing for the whole data
        D_data = np.expand_dims(D_data, axis=0)
        if D_data.ndim !=R_data.ndim:
            R_data = np.expand_dims(R_data, axis=0)
        n_T, n_ST, n_p = D_data.shape
        n_q = R_data.shape[-1]

    else:
        # Performing permutation testing per timepoint
        if verbose:
            print("performing permutation testing per timepoint")
        n_T, n_ST, n_p = D_data.shape

        # Tile the R_data if it doesn't match the number of timepoints in D_data
        if R_data.shape[0] != D_data.shape[0]:
            R_data = np.tile(R_data, (D_data.shape[0],1,1)) 
        n_q = R_data.shape[-1]
    
    
    return n_T, n_ST, n_p, n_q, D_data, R_data

def process_family_structure(dict_family, Nperm):
    """
    Process a dictionary containing family structure information.

    Parameters:
    --------------
    dict_family (dict): Dictionary containing family structure information.
        file_location (str): The file location of the family structure data in CSV format.
        M (numpy.ndarray, optional): The matrix of attributes, which is not typically required.
                                Defaults to None.
        nP (int): The number of permutations to generate.
        CMC (bool, optional): A flag indicating whether to use the Conditional Monte Carlo method (CMC).
                        Defaults to False.
        EE (bool, optional): A flag indicating whether to assume exchangeable errors, which allows permutation.
                        Defaults to True.             
    Nperm (int): Number of permutations.

    Returns:
    ----------  
    dict_mfam (dict): Modified dictionary with processed values.
        EB (numpy.ndarray): 
            Block structure representing relationships between subjects.
        M (numpy.ndarray, optional), default=None: 
            The matrix of attributes, which is not typically required.
        nP (int): 
            The number of permutations to generate.
        CMC (bool, optional), default=False: 
            A flag indicating whether to use the Conditional Monte Carlo method (CMC).
        EE (bool, optional), default=True: 
            A flag indicating whether to assume exchangeable errors, which allows permutation.
    """
    
    # dict_family: dictionary of family structure
    # Nperm: number of permutations

    default_values = {
        'file_location' : 'None',
        'M': 'None',
        'CMC': 'False',
        'EE': 'False',
        'nP': Nperm
    }
    dict_mfam =dict_family.copy()

    # Validate and load family structure data
    if 'file_location' not in dict_mfam:
        raise ValueError("The 'file_location' variable must be defined in dict_family.")
    
    # Convert the DataFrame to a matrix
    EB = pd.read_csv(dict_mfam['file_location'], header=None).to_numpy()
    
    # Check for invalid keys in dict_family
    invalid_keys = set(dict_mfam.keys()) - set(default_values.keys())
    if not invalid_keys== set():
        valid_keys = ['M', 'CMC', 'EE']
        validate_condition(
            invalid_keys in valid_keys, "Invalid keys in dict_family: Must be one of: " + ', '.join(valid_keys)
        )
    
    # Set default values for M, CMC, and EE
    del dict_mfam['file_location']
    dict_mfam['EB'] = EB
    dict_mfam['nP'] = Nperm
    dict_mfam.setdefault('M', default_values['M'])
    dict_mfam.setdefault('CMC', default_values['CMC'])
    dict_mfam.setdefault('EE', default_values['EE'])
    
    return dict_mfam

def initialize_arrays(n_p, n_q, n_T, method, Nperm, test_statistics_option, test_combination=False):
    """
    Initializes arrays for permutation testing.

    Parameters:
    --------------
    n_p (int): 
        The number of features.
    n_q (int): 
        The number of predictions.
    n_T (int): 
        The number of timepoints.
    method (str): 
        The method to use for permutation testing.
    Nperm (int): 
        Number of permutations.
    test_statistics_option (bool): 
        If True, return the test statistics values.
    test_combination (str), default=False:       
        Specifies the combination method.
        Valid options: "True", "across_columns", "across_rows".

    Returns:
    ----------  
    pval (numpy array): 
        p-values for the test (n_T, n_p) if test_statistics_option is False, else None.
    base_statistics (numpy array): 
        base statistics of a given test
    test_statistics_list (numpy array): 
        test statistics values (n_T, Nperm, n_p) or (n_T, Nperm, n_p, n_q) if method="univariate" , else None.
    """
    
    # Initialize the arrays based on the selected method and data dimensions
    if  method == "multivariate":
        if test_combination in [True, "across_columns", "across_rows"]: 
            pval = np.zeros((n_T, 1))
            if test_statistics_option==True:
                test_statistics_list = np.zeros((n_T, Nperm, 1))
            else:
                test_statistics_list= None
            base_statistics= np.zeros((n_T, 1, 1))
        else:
            pval = np.zeros((n_T, n_q))
        
            if test_statistics_option==True:
                test_statistics_list = np.zeros((n_T, Nperm, n_q))
            else:
                test_statistics_list= None
            base_statistics= np.zeros((n_T, 1, n_q))
        
    elif  method == "cca":
        pval = np.zeros((n_T, 1))
        if test_statistics_option==True:
            test_statistics_list = np.zeros((n_T, Nperm, 1))
        else:
            test_statistics_list= None
        base_statistics= np.zeros((n_T, 1, 1))        
    elif method == "univariate" :  
        if test_combination in [True, "across_columns", "across_rows"]: 
            pval_shape = (n_T, 1) if test_combination == True else (n_T, n_q) if test_combination == "across_columns" else (n_T, n_p)
            pval = np.zeros(pval_shape)
            base_statistics = pval.copy()
            if test_statistics_option:
                test_statistics_list_shape = (n_T, Nperm, 1) if test_combination == True else (n_T, Nperm, n_q) if test_combination == "across_columns" else (n_T, Nperm, n_p)
                test_statistics_list = np.zeros(test_statistics_list_shape)
            else:
                test_statistics_list = None
        else:    
            pval = np.zeros((n_T, n_p, n_q))
            base_statistics = pval.copy()
            if test_statistics_option==True:    
                test_statistics_list = np.zeros((n_T, Nperm, n_p, n_q))
            else:
                test_statistics_list= None
    elif method == "osa":
        pval = np.zeros((n_T, n_p, n_p))
        pairwise_comparisons = list(combinations(range(1, n_p + 1), 2))
        if test_statistics_option==True:    
            test_statistics_list = np.zeros((n_T, Nperm, len(pairwise_comparisons)))
        else:
            test_statistics_list= None
        base_statistics= np.zeros((n_T, 1, len(pairwise_comparisons)))
    elif method == "osr":
        pval = np.zeros((n_T, 1, n_p))
        if test_statistics_option==True:
            test_statistics_list = np.zeros((n_T, Nperm, n_p))
        else:
            test_statistics_list= None
        base_statistics= np.zeros((n_T, 1, n_p))

    # Create the data to store the t-stats
    t_stats_list = np.zeros((n_T, Nperm, n_p, n_q))

    # Create the data to store the t-stats
    F_stats_list = np.zeros((n_T, Nperm, n_q))

    return pval, base_statistics, test_statistics_list, F_stats_list, t_stats_list

def expand_variable_permute_beta(base_statistics,test_statistics_list,idx_array, method):
    """
    Expand the base statistics and test statistics for permutation testing.

    Parameters:
    -----------
    base_statistics (numpy.ndarray): 
        The base statistics array.
    test_statistics_list (numpy.ndarray): 
        The list of test statistics arrays.
    idx_array (numpy.ndarray):
        The array containing indices.

    method (str):
        The method used for expansion. Options: "multivariate", other.

    Returns:
    --------
    base_statistics (numpy.ndarray): 
        The expanded base statistics array.

    test_statistics_list (numpy.ndarray):
        The expanded list of test statistics arrays.
    """
    num_sessions =len(np.unique(idx_array))
    if method == "multivariate":
        # Add a new axis with at the second position
        base_statistics = np.tile(base_statistics, (1, num_sessions, 1))  # Expand the second dimension 
        # Add a new axis with size 5 at the second position
        test_statistics_list = np.expand_dims(test_statistics_list, axis=1)  
        test_statistics_list = np.tile(test_statistics_list, (1, num_sessions, 1, 1))  
    else:
        # Add a new axis with size 5 at the second position
        base_statistics = np.expand_dims(base_statistics, axis=1)  
        base_statistics = np.tile(base_statistics, (1, num_sessions, 1, 1))  
        # Add a new axis with size 5 at the second position
        test_statistics_list = np.expand_dims(test_statistics_list, axis=1)  
        test_statistics_list = np.tile(test_statistics_list, (1, num_sessions, 1, 1)) 
    return base_statistics,test_statistics_list

def deconfound_values(D_data, R_data, confounds=None):
    """
    Regress out confounds from the input data array D_data, and optionally from R_data if provided.
    This function deconfounds D_data by regressing out the effect of confounds. If R_data is provided, 
    it also deconfounds R_data. If confounds are not provided, it returns the centered versions of D_data 
    and R_data (if R_data is not None).

    Parameters:
    --------------
    D_data (numpy.ndarray): 
        The independent variable matrix. Shape: (n, p), where n is the number of observations and 
        p is the number of predictors.  
    R_data (numpy.ndarray or None): 
        The dependent variable matrix. Shape: (n, q), where q is the number of dependent variables.
        If None, only D_data will be deconfounded and returned.  
    confounds (numpy.ndarray or None, optional): 
        The confounds matrix. Shape: (n, k), where k is the number of confounding variables. Default is None.

    Returns:
    ----------
    D_t (numpy.ndarray): 
        The deconfounded D_data with confounds regressed out. Shape: (n, p).
        
    R_t (numpy.ndarray or None): 
        The deconfounded R_data with confounds regressed out, if R_data is provided. Shape: (n, q) or None 
        if R_data was not provided.
    """
    # Center D_data
    D_data_centered = D_data - np.nanmean(D_data, axis=0)

    if R_data is not None:
        # Center R_data
        R_data_centered = R_data - np.nanmean(R_data, axis=0)
    else:
        R_data_centered = None

    if confounds is not None:
        # Center confounds
        confounds_centered = confounds - np.nanmean(confounds, axis=0)

        # Check for NaNs in D_data and confounds
        nan_in_D = np.isnan(D_data).any()
        nan_in_confounds = np.isnan(confounds).any()

        # Fast path if no NaNs are present
        if not nan_in_D and not nan_in_confounds:
            D_t = D_data_centered - confounds_centered @ np.linalg.pinv(confounds_centered) @ D_data_centered
            if R_data_centered is not None:
                R_t = R_data_centered - confounds_centered @ np.linalg.pinv(confounds_centered) @ R_data_centered
            else:
                R_t = None
        else:
            # Initialize outputs with NaNs
            D_t = np.full_like(D_data, np.nan)
            R_t = np.full_like(R_data, np.nan) if R_data is not None else None

            # Column-wise regression for D_data
            for i in range(D_data.shape[1]):
                valid_indices = ~np.isnan(D_data[:, i]) & ~np.isnan(confounds).any(axis=1)
                if np.any(valid_indices):
                    confounds_valid = confounds_centered[valid_indices]
                    D_t[valid_indices, i] = (
                        D_data_centered[valid_indices, i]
                        - confounds_valid @ np.linalg.pinv(confounds_valid) @ D_data_centered[valid_indices, i]
                    )

            # Column-wise regression for R_data (if provided)
            if R_data_centered is not None:
                for i in range(R_data.shape[1]):
                    valid_indices = ~np.isnan(R_data[:, i]) & ~np.isnan(confounds).any(axis=1)
                    if np.any(valid_indices):
                        confounds_valid = confounds_centered[valid_indices]
                        R_t[valid_indices, i] = (
                            R_data_centered[valid_indices, i]
                            - confounds_valid @ np.linalg.pinv(confounds_valid) @ R_data_centered[valid_indices, i]
                        )
    else:
        # If confounds are not provided, return centered data
        D_t = D_data_centered
        R_t = R_data_centered

    return D_t, R_t

def deconfound_values(D_data, R_data, confounds=None):
    """
    Deconfound the variables R_data and D_data for permutation testing.

    Parameters:
    --------------
    D_data  (numpy.ndarray): 
        The input data array.
    R_data (numpy.ndarray or None): 
        The second input data array, default= None.
        If None, assumes we are working across visits, and R_data represents the Viterbi path of a sequence.
    confounds (numpy.ndarray or None): 
        The confounds array, default= None.

    Returns:
    ----------  
    D_t (numpy.ndarray): 
        D_data with confounds regressed out.
    R_t (numpy.ndarray): 
        R_data with confounds regressed out.
    """
    # Center D_data and R_data
    D_data_centered = D_data - np.nanmean(D_data, axis=0)

    if R_data is not None:
        # Center R_data
        R_data_centered = R_data - np.nanmean(R_data, axis=0)
    

    if confounds is not None:
        # Center confounds
        confounds_centered = confounds - np.nanmean(confounds, axis=0)

        # Check for NaNs in D_data, R_data, or confounds
        nan_in_D = np.isnan(D_data).any()
        nan_in_confounds = np.isnan(confounds).any()
        nan_in_R = np.isnan(R_data).any() if R_data is not None else False

        if not nan_in_D and not nan_in_R and not nan_in_confounds:
            # Fast matrix operation when no NaNs are present
            D_t = D_data_centered - confounds_centered @ np.linalg.pinv(confounds_centered) @ D_data_centered
            # Center R_data
            if R_data is not None: 
                R_t = R_data_centered - confounds_centered @ np.linalg.pinv(confounds_centered) @ R_data_centered
            
        else:
            # Initialize outputs with NaNs
            D_t = np.full_like(D_data, np.nan)

            # Column-wise regression for D_data
            for i in range(D_data.shape[1]):
                valid_indices = ~np.isnan(D_data[:, i]) & ~np.isnan(confounds).any(axis=1)
                if np.any(valid_indices):  # Ensure valid indices exist
                    confounds_valid = confounds_centered[valid_indices]
                    D_t[valid_indices, i] = (
                        D_data_centered[valid_indices, i]
                        - confounds_valid @ np.linalg.pinv(confounds_valid) @ D_data_centered[valid_indices, i]
                    )
                    
                    
            if R_data is not None:
                # Initialize outputs with NaNs
                R_t = np.full_like(R_data, np.nan)

                # Column-wise regression for R_data
                for i in range(R_data.shape[1]):
                    valid_indices = ~np.isnan(R_data[:, i]) & ~np.isnan(confounds).any(axis=1)
                    if np.any(valid_indices):  # Ensure valid indices exist
                        confounds_valid = confounds_centered[valid_indices]
                        R_t[valid_indices, i] = (
                            R_data_centered[valid_indices, i]
                            - confounds_valid @ np.linalg.pinv(confounds_valid) @ R_data_centered[valid_indices, i]
                        )
            else:
                R_t = None
    else:
        # If confounds are not provided, return centered data
        D_t = D_data_centered
        R_t = R_data_centered if R_data is not None else R_data
    return D_t, R_t

def initialize_permutation_matrices(method, Nperm, n_p, n_q, D_data, test_combination=False, permute_beta=False, category_columns=None):
    """
    Initializes the permutation matrices and prepare the regularized pseudo-inverse of D_data.

    Parameters:
    --------------
    method (str): 
        The method to use for permutation testing.
    Nperm (int): 
        The number of permutations.
    n_p (int): 
        The number of features.
    n_q (int): 
        The number of predictions.
    D_data (numpy.ndarray): 
        The independent variable.
    test_combination (str), default=False:       
        Specifies the combination method.
        Valid options: "True", "across_columns", "across_rows".
    permute_beta (bool, optional), default=False: 
        A flag indicating whether to permute beta coefficients.


    Returns:
    ----------  
    test_statistics (numpy.ndarray): 
        The permutation array.
    pval_perms (numpy.ndarray): 
        The p-value permutation array.
    reg_pinv (numpy.ndarray or None): 
        The regularized pseudo-inverse of D_data.
    """
    # Define regularized pseudo-inverse
    reg_pinv = None
    # Initialize the permutation matrices based on the selected method
    if method in {"univariate"}:
        if test_combination in [True, "across_columns", "across_rows"]: 
            test_statistics_shape = (Nperm, 1) if test_combination == True else (Nperm, n_q) if test_combination == "across_columns" else (Nperm, n_p)
            test_statistics = np.zeros(test_statistics_shape)
        else:
            # Initialize test statistics output matrix based on the selected method
            test_statistics = np.zeros((Nperm, n_p, n_q))
        if permute_beta or category_columns['f_reg_cols']!=[]:
            # Set the regularization parameter
            regularization = 0.001
            # Create a regularization matrix (identity matrix scaled by the regularization parameter)
            regularization_matrix = regularization * np.eye(D_data.shape[1])  # Regularization term for Ridge regression
            # Compute the regularized pseudo-inverse of D_data
            reg_pinv = np.linalg.inv(D_data.T @ D_data + regularization_matrix) @ D_data.T 
    elif method =="cca":
        # Initialize test statistics output matrix based on the selected method
        test_statistics = np.zeros((Nperm, 1))
    elif method =="osr":
        # Initialize test statistics output matrix based on the selected method
        test_statistics = np.zeros((Nperm, n_p))
    else:
        # multivariate
        if test_combination in [True, "across_columns", "across_rows"]:
            test_statistics = np.zeros((Nperm, 1))
        else:
            # Regression got a N by q matrix 
            test_statistics = np.zeros((Nperm, n_q))

        # Define regularization parameter
        regularization_parameter = 0.001
        # Create a regularization matrix (identity matrix scaled by the regularization parameter)
        regularization_matrix = regularization_parameter * np.eye(D_data.shape[1]) 
        # Compute the regularized pseudo-inverse
        reg_pinv = np.linalg.inv(D_data.T @ D_data + regularization_matrix) @ D_data.T  
        

    return test_statistics, np.array(reg_pinv)

def permutation_matrix_across_subjects(Nperm, R_data):
    """
    Generates a normal permutation matrix with the assumption that each index is independent across subjects. 

    Parameters:
    --------------
    Nperm (int): 
        The number of permutations.
    R_data (numpy.ndarray): 
        R-matrix at timepoint 't'
        
    Returns:
    ----------  
    permutation_matrix (numpy.ndarray): 
        Permutation matrix of subjects it got a shape (n_ST, Nperm)
    """

    R_len = []

    # Loop through each timepoint and count non-NaN values
    for t in range(R_data.shape[0]):
        non_nan_count = np.sum(~np.isnan(R_data[t, :]), axis=0)
        R_len.append(non_nan_count)

    # Find the timepoint with the longest length
    max_length = np.argmax(R_len) 
    #Rin = R_data[max_length,~np.isnan(R_data[max_length, :])] # Now only look at values that are not NaN for the longest list of values
    R_t = R_data[max_length,:]

    permutation_matrix = np.zeros((R_t.shape[0],Nperm), dtype=int)
    for perm in range(Nperm):
        if perm == 0:
            permutation_matrix[:,perm] = np.arange(R_t.shape[0])
        else:
            permutation_matrix[:,perm] = np.random.permutation(R_t.shape[0])
    return permutation_matrix

def get_pval(test_statistics, Nperm, method, t, pval, FWER_correction=False):
    """
    Computes p-values from the test statistics.
    # Ref: https://github.com/OHBA-analysis/HMM-MAR/blob/master/utils/testing/permtest_aux.m

    Parameters:
    --------------
    test_statistics (numpy.ndarray): 
        The permutation array.
    pval_perms (numpy.ndarray): 
        The p-value permutation array.
    Nperm (int): 
        The number of permutations.
    method (str): 
        The method used for permutation testing.
    t (int): 
        The timepoint index.
    pval (numpy.ndarray): 
        The p-value array.

    Returns:
    ----------  
    pval (numpy.ndarray): 
        Updated updated p-value .
    """
    if method == "multivariate" or method == "osr":
        if FWER_correction:
            # Perform family-wise permutation correction
            # Compute the maximum statistic for each permutation (excluding the first row)
            max_test_statistics = np.max(test_statistics[1:], axis=1)  # Shape: (Nperm,)

            # Count how many times MaxT statistics exceed or equal each observed statistic
            # Adding 1 to numerator and denominator for bias correction
            pval[t, :] = (np.sum(max_test_statistics[:, np.newaxis] >= test_statistics[0, :], axis=0) + 1) / (Nperm + 1)
            
        else:
            # Count how many times test_statistics exceed or equal each observed statistic
            # Adding 1 for bias correction
            pval[t, :] = (np.sum(test_statistics[:] >= test_statistics[0,:], axis=0)) / (Nperm+ 1)
        
    elif method == "univariate" or method =="cca":
        if FWER_correction:
            # Perform family-wise permutation correction
            # Calculate the MaxT statistics for each permutation (excluding the observed)
            # The empirical distribution of the maximum test statistics does not include the observed statistics
            maxT_statistics = np.max(np.abs(test_statistics[1:, :, :]), axis=(1, 2))  # Shape: (Nperm - 1,)

            # Extract the observed test statistics (first row)
            observed_test_stats = np.abs(test_statistics[0, :, :])  # Shape: (p_dim, q_dim)

            # Use broadcasting to compare observed statistics against MaxT statistics
            # Expand dimensions for broadcasting
            observed_expanded = observed_test_stats[np.newaxis, :, :]  # Shape: (1, p_dim, q_dim)
            maxT_expanded = maxT_statistics[:, np.newaxis, np.newaxis]  # Shape: (Nperm - 1, 1, 1)

            # Count how many times MaxT statistics exceed or equal each observed statistic
            # Adding 1 to numerator and denominator for bias correction
            pval[t, :, :] = (np.sum(maxT_expanded >= observed_expanded, axis=0) + 1) / (Nperm + 1)  # Shape: (p_dim, q_dim)
            
        else:    
            # Count how many times test_statistics exceed or equal each observed statistic
            # Adding 1 for bias correction
            pval[t, :] = (np.sum(test_statistics[:] >= test_statistics[0,:], axis=0)) / (Nperm+ 1)
    
    return pval


def permutation_matrix_across_trials_within_session(Nperm, R_data, idx_array, trial_timepoints=None, time_FLAG=0):
    """
    Generates permutation matrix of within-session across-trial data based on given indices.

    Parameters:
    --------------
    Nperm (int): 
        The number of permutations.
    R_data (numpy.ndarray): 
        The preprocessed data array.
    idx_array (numpy.ndarray): 
        The indices array.
    trial_timepoints (int): 
        Number of timepoints for each trial, default = None

    Returns:
    ----------  
    permutation_matrix (numpy.ndarray): 
        Permutation matrix of subjects it got a shape (n_ST, Nperm)
    """
    # Perform within-session between-trial permutation based on the given indices
    if time_FLAG:

        # Createing the permutation matrix
        R_len = []

        # Loop through each timepoint and count non-NaN values
        for t in range(R_data.shape[0]):
            non_nan_count = np.sum(~np.isnan(R_data[t, :]), axis=0)
            R_len.append(non_nan_count)

        # Find the timepoint with the longest length
        max_length = np.argmax(R_len) 
        #Rin = R_data[max_length,~np.isnan(R_data[max_length, :])] # Now only look at values that are not NaN for the longest list of values
        R_t = R_data[max_length,:]

    else:
        R_t = R_data.copy()
    
    permutation_matrix = np.zeros((R_t.shape[0], Nperm), dtype=int)
    for perm in range(Nperm):
        if perm == 0:
            permutation_matrix[:,perm] = np.arange(R_t.shape[0])
        else:
            unique_indices = np.unique(idx_array)
            if trial_timepoints is None:
                count = 0
                for i in unique_indices:
                    if i ==0:
                        count =count+R_t[idx_array == unique_indices[i], :].shape[0]
                        permutation_matrix[0:count,perm]=np.random.permutation(np.arange(0,count))
                    else:
                        idx_count=R_t[idx_array == unique_indices[i], :].shape[0]
                        count =count+idx_count
                        permutation_matrix[count-idx_count:count,perm]=np.random.permutation(np.arange(count-idx_count,count))
    
            else:
                # Initialize the array to store permutation indices
                permutation_array = []

                # Iterate over unique session indices
                for count, session_idx in enumerate(unique_indices):
                    # Extract data for the current session
                    session_data = R_t[idx_array == session_idx, :]
                    # Get number of data points for each session
                    num_datapoints = session_data.shape[0]

                    # Calculate the number of trials based on trial_timepoints
                    # This step is required because each session can have a different number of trials
                    num_trials = num_datapoints // trial_timepoints

                    # Generate indices for each trial and repeat them based on trial_timepoints
                    idx_trials = np.repeat(np.arange(num_trials), trial_timepoints)

                    # Count unique indices and their occurrences
                    unique_values, value_counts = np.unique(idx_trials, return_counts=True)

                    # Randomly permute the unique indices
                    unique_values_perm = np.random.permutation(unique_values)

                    # Repeat each unique value according to its count in value_counts
                    permuted_array = np.concatenate([np.repeat(value, count) for value, count in zip(unique_values_perm, value_counts)])

                    # Get positions for each unique trial
                    positions_permute = [np.where(permuted_array == i)[0] for i in unique_values]

                    # Extend the permutation_array with adjusted positions
                    permutation_array.extend(np.concatenate(positions_permute) + num_datapoints * count)
                permutation_matrix[:,perm] =np.array(permutation_array)

    return permutation_matrix

def permute_subject_trial_idx(idx_array):
    """
    Permutes an array based on unique values while maintaining the structure.
    
    Parameters:
    --------------
    idx_array (numpy.ndarray): 
        Input array to be permuted.
    
    Returns:
    ----------  
    permuted_array (numpy.ndarray):
        Permuted matrix based on unique values.
    """
    # Get unique values and their counts
    unique_values, value_counts = np.unique(idx_array, return_counts=True)

    # Permute the unique values
    permuted_unique_values = np.random.permutation(unique_values)

    # Repeat each unique value according to its original count
    permuted_array = np.repeat(permuted_unique_values, value_counts)

    return permuted_array


def permutation_matrix_within_subject_across_sessions(Nperm, R_data, idx_array):
    """
    Generates permutation matrix of within-session across-session data based on given indices.

    Parameters:
    --------------
    Nperm (int): 
        The number of permutations.
    R_data (numpy.ndarray): 
        The preprocessed data array.
    idx_array (numpy.ndarray): 
        The indices array.


    Returns:
    ----------  
    permutation_matrix (numpy.ndarray): 
        The within-session continuos indices array.
    """
    R_len = []

    # Loop through each timepoint and count non-NaN values
    for t in range(R_data.shape[0]):
        non_nan_count = np.sum(~np.isnan(R_data[t, :]), axis=0)
        R_len.append(non_nan_count)

    # Find the timepoint with the longest length
    max_length = np.argmax(R_len) 
    #Rin = R_data[max_length,~np.isnan(R_data[max_length, :])] # Now only look at values that are not NaN for the longest list of values
    R_t = R_data[max_length,:]

    permutation_matrix = np.zeros((R_t.shape[0],Nperm), dtype=int)
    for perm in range(Nperm):
        if perm == 0:
            permutation_matrix[:,perm] = np.arange(R_t.shape[0])
        else:
            idx_array_perm = permute_subject_trial_idx(idx_array)
            unique_indices = np.unique(idx_array_perm)
            positions_permute = [np.where(np.array(idx_array_perm) == i)[0] for i in unique_indices]
            permutation_matrix[:,perm] = np.concatenate(positions_permute,axis=0)
    return permutation_matrix

def permutation_matrix_within_and_between_groups(Nperm, R_data, idx_array):
    """
    Generates a permutation matrix with permutations within and between groups.
    
    Parameters:
    --------------
    Nperm (int): 
        The number of permutations.
    R_data (numpy.ndarray): 
        The R_data array used for generating the within-group permutation matrix.
    idx_array (numpy.ndarray): 
        The indices array that groups the R_data (e.g., session or subject identifiers).
    
    Returns:
    ----------
    permutation_matrix (numpy.ndarray): 
        The matrix with both within- and between-group permutations.
    """
    R_len = []

    # Loop through each timepoint and count non-NaN values
    for t in range(R_data.shape[0]):
        non_nan_count = np.sum(~np.isnan(R_data[t, :]), axis=0)
        R_len.append(non_nan_count)

    # Find the timepoint with the longest length
    max_length = np.argmax(R_len) 
    #Rin = R_data[max_length,~np.isnan(R_data[max_length, :])] # Now only look at values that are not NaN for the longest list of values
    R_t = R_data[max_length,:]

    # Generate the within-group permutation matrix
    permutation_matrix_within_group = permutation_matrix_across_trials_within_session(
        Nperm, R_t, idx_array)
    
    # Initialize the permutation matrix for within and between groups
    permutation_within_and_between_group = np.zeros_like(permutation_matrix_within_group)
    
    for perm in range(Nperm):
        if perm == 0:
            # The first column is just the identity permutation (no change)
            permutation_within_and_between_group[:, perm] = np.arange(R_t.shape[0])
        else:
            # Permute the idx_array to shuffle the groupings
            idx_array_perm = permute_subject_trial_idx(idx_array)
            unique_indices = np.unique(idx_array_perm)
            
            # Find the positions of each unique group after permutation
            positions_permute = [np.where(np.array(idx_array_perm) == i)[0] for i in unique_indices]
            perm_array = np.concatenate(positions_permute, axis=0)
            
            # Apply the within-group permutation to the newly permuted positions
            permutation_within_and_between_group[:, perm] = permutation_matrix_within_group[:, perm][perm_array]
    
    return permutation_within_and_between_group

def generate_vpath_1D(vpath):
    """
    Convert a 2D array representing a matrix with one non-zero element in each row
    into a 1D array where each element is the column index of the non-zero element.

    Parameters:
    ------------
    vpath(numpy.ndarray):       
        A 2D array where each row has only one non-zero element. 
        Or a 1D array where each row represents a sate number

    Returns:
    ------------
    vpath_array(numpy.ndarray): 
        A 1D array containing the column indices of the non-zero elements.
        If the input array is already 1D, it returns a copy of the input array.

    """
    if np.ndim(vpath) == 2:
        vpath_array = np.nonzero(vpath)[1] + 1
    else:
        if np.min(vpath)==0:
            # Then it is already a vector
            vpath_array = vpath.copy()+1
        else:
            # Then it is already a vector
            vpath_array = vpath.copy()

    return vpath_array.astype(np.int8)



def surrogate_state_time(perm, viterbi_path,n_states):
    """
    Generates surrogate state-time matrix based on a given Viterbi path.

    Parameters:
    --------------
    perm (int): 
        The permutation number.
    viterbi_path (numpy.ndarray): 
        1D array or 2D matrix containing the Viterbi path.
    n_states (int): 
        The number of states

    Returns:
    ----------  
    viterbi_path_surrogate (numpy.ndarray): 
        A 1D array representing the surrogate Viterbi path
    """
       
    if perm == 0:
        if np.ndim(viterbi_path) == 2 and viterbi_path.shape[1] !=1:
            viterbi_path_surrogate = viterbi_path_to_stc(viterbi_path, n_states)
        elif np.ndim(viterbi_path) == 2 and viterbi_path.shape[1] ==1:
            viterbi_path_surrogate = np.squeeze(viterbi_path.copy().astype(np.int8))
        else:
            viterbi_path_surrogate = viterbi_path.copy().astype(np.int8)
            
    else:
        viterbi_path_surrogate = surrogate_viterbi_path(viterbi_path, n_states)
    return viterbi_path_surrogate


def surrogate_state_time_matrix(Nperm, vpath_data, n_states):
    vpath_array=generate_vpath_1D(vpath_data)
    vpath_surrogates = np.zeros((len(vpath_array),Nperm), dtype=np.int8)
    for perm in tqdm(range(Nperm)):
        while True:
            vpath_surrogates[:,perm] = surrogate_state_time(perm, vpath_array, n_states)
            if len(np.unique(vpath_surrogates[:,perm])) == n_states:
                break  # Exit the loop if the condition is satisfied
    return vpath_surrogates


def viterbi_path_to_stc(viterbi_path, n_states):
    """
    Convert Viterbi path to state-time matrix.

    Parameters:
    --------------
    viterbi_path (numpy.ndarray): 
        1D array or 2D matrix containing the Viterbi path.
    n_states (int): 
        Number of states in the hidden Markov model.

    Returns:
    ----------  
    stc (numpy.ndarray): 
        State-time matrix where each row represents a time point and each column represents a state.
    """
    stc = np.zeros((len(viterbi_path), n_states), dtype=np.int8)
    if np.min(viterbi_path)==0:
        stc[np.arange(len(viterbi_path)), viterbi_path] = 1
    else:
        stc[np.arange(len(viterbi_path)), viterbi_path-1] = 1
    return stc

def surrogate_viterbi_path(viterbi_path, n_states):
    """
    Generate a surrogate Viterbi path that preserves segment structure but 
    reassigns each segment to a different state without repetition.

    Parameters:
    --------------
    viterbi_path (numpy.ndarray):   
        1D array containing the original Viterbi path with unique state segments.
    n_states (int):                
        Total number of states.

    Returns:
    ----------  
    viterbi_path_surrogate (numpy.ndarray): 
        A 1D array with the same segmentation structure but reassigned unique states.
    """
    # Identify unique states and their segment indices
    unique_states, segment_start_indices = np.unique(viterbi_path, return_index=True)
    
    # Ensure the number of unique states matches the expected count
    if len(unique_states) != n_states:
        raise ValueError("Mismatch: Unique states in viterbi_path does not match n_states")

    # Generate a shuffled mapping ensuring no state is mapped to itself
    shuffled_states = unique_states.copy()
    np.random.shuffle(shuffled_states)
    
    while np.any(shuffled_states == unique_states):
        np.random.shuffle(shuffled_states)

    # Create a state mapping
    state_mapping = dict(zip(unique_states, shuffled_states))

    # Apply the mapping to generate the surrogate path
    viterbi_path_surrogate = np.vectorize(state_mapping.get)(viterbi_path)

    return viterbi_path_surrogate.astype(np.int8)

def surrogate_viterbi_path(viterbi_path, n_states):
    """
    Generate a surrogate Viterbi path while keeping the segment 
    structure intact. Each segment (continuous run of the same state) is 
    reassigned to a new state, ensuring that no two consecutive segments 

    Parameters:
    --------------
    viterbi_path (numpy.ndarray):   
        1D array representing the original Viterbi path with unique state segments.
    n_states (int):                
        The total number of states.

    Returns:
    ----------  
    viterbi_path_surrogate (numpy.ndarray): 
        A 1D array with the same segmentation pattern but reassigned states, ensuring 
        that no segment is mapped to the same state as the previous one.
    """
    # Detect segment boundaries (where the state changes)
    segment_start_indices = np.where(np.diff(viterbi_path) != 0)[0] + 1
    segment_start_indices = np.insert(segment_start_indices, 0, 0)  # Include the first index

    # Extract unique states and shuffle them for reassignment
    original_states = np.unique(viterbi_path)
    shuffled_states = original_states.copy()
    
    # Ensure shuffled states are different from the original sequence
    while np.any(shuffled_states == original_states):
        np.random.shuffle(shuffled_states)

    # Assign states ensuring no consecutive segments have the same value
    viterbi_path_surrogate = np.zeros_like(viterbi_path, dtype=np.int8)
    last_state = None
    available_states = shuffled_states.copy()

    for i, start in enumerate(segment_start_indices):
        end = segment_start_indices[i + 1] if i + 1 < len(segment_start_indices) else len(viterbi_path)

        # Choose a new state that is different from the last assigned state
        possible_states = available_states[available_states != last_state]
        new_state = np.random.choice(possible_states)
        
        # Assign the new state to the segment
        viterbi_path_surrogate[start:end] = new_state
        last_state = new_state

    return viterbi_path_surrogate
    
def calculate_baseline_difference(vpath_array, R_data, state, pairwise_statistic, state_com):
    """
    Calculate the difference between the specified statistics of a state and all other states combined.

    Parameters:
    --------------
    vpath_data (numpy.ndarray): 
        The Viterbi path as of integer values that range from 1 to n_states.
    R_data (numpy.ndarray):     
        The dependent-variable associated with each state.
    state(numpy.ndarray):       
        The state for which the difference is calculated from.
    pairwise_statistic (str)             
        The chosen statistic to be calculated. Valid options are "mean" or "median".

    Returns:
    ----------  
    difference (float)            
        The calculated difference between the specified state and all other states combined.
    """
    if pairwise_statistic == 'median':
        # Calculate the median for the specific state
        state_R_data = np.nanmedian(R_data[vpath_array == state])
        # Calculate the median for all other states
        other_R_data = np.nanmedian(R_data[vpath_array != state])
    elif pairwise_statistic == 'mean':
        # Calculate the mean for the specific state
        state_R_data = np.nanmean(R_data[vpath_array == state])
        # Calculate the mean for all other states
        other_R_data = np.nanmean(R_data[vpath_array != state])
    else:
        raise ValueError("Invalid stat value")
    # Detect any difference
    # difference = np.abs(state_R_data) - np.abs(other_R_data)
    if state_com=="larger":
        difference = state_R_data - other_R_data
    else:
        difference =  other_R_data - state_R_data
    
    return difference

def calculate_statepair_difference(vpath_array, R_data, state_1, state_2, stat):
    """
    Calculate the difference between the specified statistics of two states.

    Parameters:
    --------------
    vpath_data (numpy.ndarray): 
        The Viterbi path as of integer values that range from 1 to n_states.
    R_data (numpy.ndarray):     
        The dependent-variable associated with each state.
    state_1 (int):              
        First state for comparison.
    state_2 (int):              
        Second state for comparison.
    statistic (str):            
        The chosen statistic to be calculated. Valid options are "mean" or "median".

    Returns:
    ----------  
    difference (float):           
        The calculated difference between the two states.
    """
    if stat == 'mean':
        state_1_R_data = np.nanmean(R_data[vpath_array == state_1])
        state_2_R_data = np.nanmean(R_data[vpath_array == state_2])
    elif stat == 'median':
        state_1_R_data = np.nanmedian(R_data[vpath_array == state_1])
        state_2_R_data = np.nanmedian(R_data[vpath_array == state_2])
    else:
        raise ValueError("Invalid stat value")
    # Detect any difference
    difference = state_1_R_data - state_2_R_data
    return difference

def test_statistics_calculations(Din, Rin, perm, test_statistics, reg_pinv, method, category_columns=[], test_combination=False, idx_data=None, permute_beta=False, beta = None, test_indices=None):
    """
    Calculates the test_statistics array and pval_perms array based on the given data and method.

    Parameters:
    --------------
    Din (numpy.ndarray): 
        The data array.
    Rin (numpy.ndarray): 
        The dependent variable.
    perm (int): 
        The permutation index.
    pval_perms (numpy.ndarray): 
        The p-value permutation array.
    test_statistics (numpy.ndarray): 
        The permutation array.
    reg_pinv (numpy.ndarray or None):  
        The regularized pseudo-inverse of D_data
    method (str): 
        The method used for permutation testing.
    category_columns (dict):
        A dictionary marking the columns where t-test ("t_test_cols") and F-test ("f_anova_cols") have been applied.
    test_combination (str), default=False:       
        Specifies the combination method.
        Valid options: "True", "across_columns", "across_rows".
    idx_data (numpy.ndarray), default=None: 
        An array containing the indices for each session. The array can be either 1D or 2D:
        For a 1D array, a sequence of integers where each integer labels the session number. For example, [1, 1, 1, 1, 2, 2, 2, ..., N, N, N, N, N, N, N, N].
        For a 2D array, each row represents the start and end indices for the trials in a given session, with the format [[start1, end1], [start2, end2], ..., [startN, endN]].   
    permute_beta (bool, optional), default=False: 
        A flag indicating whether to permute beta coefficients.
    beta (numpy.ndarray), default=None:
        beta coefficient for each session.
        It has a shape (num_session, p, q), where the first dimension 
        represents the session, the second dimension represents the featires, 
        and the third dimension represent dependent variables. 
    test_indices (numpy.ndarray), default=None:
        Indices for data points that belongs to the test-set for each session.

    Returns:
    ----------  
    test_statistics (numpy.ndarray): 
        Updated test_statistics array.
    base_statistics (numpy.ndarray): 
        Updated pval_perms array.
    pval_matrix (numpy.ndarray): 
        P-values derived from t and f statistics using General linear models.
    """
    pval_matrix= None
    t_stats = None
    F_stats = None
    if method == 'multivariate':

        if category_columns["t_test_cols"]==[] and category_columns["f_anova_cols"]==[] and category_columns["f_reg_cols"]==[]:
            # We wont have a p-value matrix since we are not doing GLM inference here

            nan_values = np.sum(np.isnan(Rin))>0
            if nan_values:
                # NaN values are detected
                if test_combination in [True, "across_rows"]:
                    # Calculate F-statitics with no NaN values.
                    F_stats, p_value =calculate_nan_regression_f_test(Din, Rin, reg_pinv, idx_data, permute_beta, perm, nan_values)
                    # Get the base statistics and store p-values as z-scores to the test statistic
                    base_statistics, pval_matrix = calculate_combined_z_scores(p_value, test_combination)
                    test_statistics[perm] =abs(base_statistics) 
                else:
                    # Calculate the explained variance if R got NaN values.
                    base_statistics, F_stats, t_stats=calculate_regression_statistics(Din, Rin, reg_pinv, idx_data, permute_beta, perm, beta, test_indices, nan_values)
                    test_statistics[perm,:] =base_statistics           
            else:
                # No- NaN values are detected
                if idx_data is not None and permute_beta==True:
                    # Calculate predicted values with no NaN values
                    if test_indices is not None:
                        idx_test = np.concatenate(test_indices, axis=0)
                        Rin =Rin[idx_test,:]
                        Din =Din[idx_test,:]
                        # calculate beta coefficients
                        R2_stats, F_stats, t_stats =calculate_ols_predictions(Rin, Din, idx_data, beta, perm, permute_beta, regression_statistics=True)
                    else:    
                        # calculate beta coefficients
                        R2_stats, F_stats, t_stats =calculate_ols_predictions(Rin, Din, idx_data, beta, perm, permute_beta, regression_statistics=True)
                        
                    base_statistics = R2_stats #r_squared
                else:
                    # Calculate statistics with zero Nan values
                    base_statistics, F_stats, t_stats=calculate_regression_statistics(Din, Rin, reg_pinv)
            
                if test_combination in [True, "across_rows"]:
                    # Calculate the degrees of freedom for the model and residuals
                    df1 = Din.shape[1]  # Number of predictors 
                    df2 = Din.shape[0] - df1

                    pval = 1 - f.cdf(F_stats, df1, df2)
                    # Get the base statistics and store p-values as z-scores to the test statistic
                    base_statistics = calculate_combined_z_scores(pval, test_combination)[0]
                    test_statistics[perm] =abs(base_statistics) 
                else:
                    # Store the R^2 values in the test_statistics array
                    test_statistics[perm] = base_statistics
                    
        else:
            # Now we have to do t- or f-statistics
            # If we are doing test_combinations, we need to calculate f-statistics on every column
            if test_combination in [True, "across_columns"]:
                nan_values = np.sum(np.isnan(Rin))>0
                # Calculate the explained variance if R got NaN values.
                _, p_values =calculate_nan_regression_f_test(Din, Rin, reg_pinv, idx_data, permute_beta, perm, nan_values, beta)
                # Get the base statistics and store p-values as z-scores to the test statistic
                base_statistics, pval_matrix = calculate_combined_z_scores(p_values, test_combination)

                test_statistics[perm] =abs(base_statistics) 
            
            else:
            # If we are not perfomring test_combination, we need to perform a columnwise operation.  
            # We perform f-test if category_columns has flagged categorical columns otherwise it will be R^2 
                # Initialize variables  which
                #base_statistics =np.zeros_like(test_statistics[0,:]) if perm ==0 else None
                base_statistics =np.zeros_like(test_statistics[0,:])
                pval_matrix =np.zeros_like(test_statistics[0,:])
                for col in range(Rin.shape[1]):
                    # Get the R_column
                    R_column = Rin[:, col]
                    # Calculate f-statistics of columns of interest 
                    nan_values = np.sum(np.isnan(Rin[:,col]))>0 
                    if category_columns["f_anova_cols"] and col in category_columns["f_anova_cols"]:
                        # Nan values
                        if permute_beta:
                            # Calculate base statistics per column
                            if test_indices is not None:
                                base_statistics[col], pval_matrix[col] =calculate_nan_anova_f_test(Din[test_indices[col],:], Rin[test_indices[col],col], reg_pinv[:,test_indices[col]], idx_data, permute_beta, perm, nan_values, beta=np.expand_dims(beta[:,:,col],axis=2))
                            else:    
                                base_statistics[col], pval_matrix[col] =calculate_nan_anova_f_test(Din, R_column, reg_pinv, idx_data, permute_beta, perm, nan_values, beta=np.expand_dims(beta[:,:,col],axis=2))
                        else:
                            # Then we need to calculate beta
                            base_statistics[col], pval_matrix[col]=calculate_nan_anova_f_test(Din, R_column, reg_pinv, idx_data, permute_beta, perm, nan_values)
                        test_statistics[perm,col] = base_statistics[col]   
                          
                    elif category_columns["f_reg_cols"] and col in category_columns["f_reg_cols"]:
                        # Nan values
                        if permute_beta:
                            # Calculate base statistics per column
                            if test_indices is not None:
                                base_statistics[col], pval_matrix[col] =calculate_nan_regression_f_test(Din[test_indices[col],:], Rin[test_indices[col],col], reg_pinv[:,test_indices[col]], idx_data, permute_beta, perm, nan_values, beta=np.expand_dims(beta[:,:,col],axis=2))
                            else:    
                                base_statistics[col], pval_matrix[col] =calculate_nan_regression_f_test(Din, R_column, reg_pinv, idx_data, permute_beta, perm, nan_values, beta=np.expand_dims(beta[:,:,col],axis=2))
                        else:
                            # Then we need to calculate beta
                            base_statistics[col], pval_matrix[col]=calculate_nan_regression_f_test(Din, R_column, reg_pinv, idx_data, permute_beta, perm, nan_values)
                        test_statistics[perm,col] = base_statistics[col]  
                    else:
                        # Check for NaN values
                        if nan_values:
                            if permute_beta:
                                # This is done for across session testing
                                # Calculate the explained variance if R got NaN values.
                                base_statistics[col], F_stats, t_stats=calculate_regression_statistics(Din, Rin[:, col], reg_pinv, idx_data, permute_beta, perm, np.expand_dims(beta[:,:,col],axis=2), test_indices[col])  
                            else:
                                base_statistics[col], F_stats, t_stats=calculate_regression_statistics(Din, Rin[:, col], reg_pinv, idx_data, permute_beta, perm)        
                        else:
                            if beta is None:
                                # Fit the original model 
                                beta_hat = reg_pinv @ Rin[:, col]  # Calculate regression_coefficients (beta)
                                # # # # Include intercept
                                # # # Din = np.hstack((np.ones((Din.shape[0], 1)), Din))
                                # Calculate the predicted values
                                R_pred = Din @ beta_hat
                            else:
                                # Update R_column
                                R_column = Rin[test_indices[col], col]
                                # Calculate predicted values using the test_set
                                R_pred = calculate_ols_predictions(R_column, Din[test_indices[col],:], idx_data, beta[:,:,col], perm, permute_beta)
                            # Calculate the residual sum of squares (rss)
                            rss = np.sum((R_column-R_pred)**2, axis=0)
                            # Calculate the total sum of squares (tss)
                            tss = np.sum((R_column - np.mean(R_column, axis=0))**2, axis=0)
                            # Calculate R^2
                            base_statistics[col] = 1 - (rss / tss) #r_squared
                        # Store the R^2 values in the test_statistics array
                        test_statistics[perm,col] = base_statistics[col]        
    # Calculate for univariate tests              
    elif method == "univariate":
        if category_columns["t_test_cols"]==[] and category_columns["f_anova_cols"]==[]and category_columns["f_reg_cols"]==[]:
            # We wont have a p-value matrix since we are not doing GLM inference here
            pval_matrix = None
            # Only calcuating the correlation matrix, since there is no need for t- or f-test
            if np.sum(np.isnan(Din))>0 or np.sum(np.isnan(Rin))>0:
                # Calculate the correlation matrix while handling NaN values 
                # column by column without removing entire rows.
                if test_combination in [True, "across_columns", "across_rows"]: 
                    if permute_beta:
                        f_statistic , p_value =calculate_f_statistics_and_explained_variance_univariate(Din, Rin, idx_data, beta, perm, reg_pinv, permute_beta, test_combination=test_combination, test_indices_list=test_indices)
                        #base_statistics =np.squeeze(f_statistic)
                        base_statistics, pval_matrix =calculate_combined_z_scores(p_value, test_combination)
                        test_statistics[perm] =abs(base_statistics) 
                    else:
                        # Return parametric p-values
                        correlation_matrix ,p_value =calculate_nan_correlation_matrix(Din, Rin, True)
                        base_statistics, pval_matrix =calculate_combined_z_scores(p_value,test_combination)
                        # get test statistics
                        test_statistics[perm, :] = abs(base_statistics) # Notice that shape of test_statistics are different
                elif permute_beta:
                    # r2-statistics
                    base_statistics, _ =calculate_f_statistics_and_explained_variance_univariate(Din, Rin, idx_data, beta, perm, reg_pinv, permute_beta, test_indices_list=test_indices)
                    test_statistics[perm, :, :] = base_statistics
                else:
                    # Return base statistics and pvalues if perm==0 => get parametric p-values
                    base_statistics,pval_matrix =calculate_nan_correlation_matrix(Din, Rin, True) if perm==0 else calculate_nan_correlation_matrix(Din, Rin)
                    test_statistics[perm, :, :] = np.abs(base_statistics)
            else:
                if test_combination in [True, "across_columns", "across_rows"]: 
                    if permute_beta:
                        # Calculate geometric mean of p-values
                        f_statistics, p_value =calculate_f_statistics_and_explained_variance_univariate(Din, Rin, idx_data, beta, perm, reg_pinv, permute_beta, test_combination=test_combination, test_indices=test_indices)
                        #### base statistics => f-statistics
                        # base_statistics =np.squeeze(corr_statistics)
                        base_statistics, pval_matrix =calculate_combined_z_scores(p_value)
                        test_statistics[perm] =abs(base_statistics) 
                    else:    
                        # Return parametric p-values
                        p_values = np.zeros((Din.shape[1],Rin.shape[1]))
                        base_statistics = np.zeros((Din.shape[1],Rin.shape[1]))
                        for i in range(Din.shape[1]):
                            for j in range(Rin.shape[1]):
                                # get correlation coefficients and pvalues
                                base_statistics[i,j], p_values[i, j] = pearsonr(Din[:, i], Rin[:, j])

                        # Get the geometric mean p-values based on test combination
                        #pval_matrix =geometric_pvalue(pval_matrix, test_combination)  
                        # base statistics => Z_score
                        base_statistics, pval_matrix =calculate_combined_z_scores(p_values, test_combination)

                        test_statistics[perm] =abs(base_statistics)     

                elif permute_beta:
                    base_statistics, _ =calculate_f_statistics_and_explained_variance_univariate(Din, Rin, idx_data, beta, perm, reg_pinv, permute_beta, test_indices_list=test_indices)
                    test_statistics[perm, :, :] = np.abs(base_statistics)
                
                elif perm==0:
                    # get the p-values as well when it is the first permutation
                    pval_matrix = np.zeros((Din.shape[1],Rin.shape[1]))
                    base_statistics = np.zeros((Din.shape[1],Rin.shape[1]))
                    for i in range(Din.shape[1]):
                        for j in range(Rin.shape[1]):
                            # get correlation coefficients and pvalues
                            base_statistics[i,j], pval_matrix[i, j] = pearsonr(Din[:, i], Rin[:, j])
                    test_statistics[perm, :, :] = np.abs(base_statistics)

                else:
                    # Calculate correlation coeffcients without NaN values
                    corr_coef = np.corrcoef(Din, Rin, rowvar=False)
                    corr_matrix = corr_coef[:Din.shape[1], Din.shape[1]:]
                    base_statistics = corr_matrix
                    test_statistics[perm, :, :] = np.abs(base_statistics)
        else: 
            pval_matrix = np.zeros((Din.shape[-1],Rin.shape[-1]))
            base_statistics = np.zeros((Din.shape[-1],Rin.shape[-1]))
            for col in range(Rin.shape[1]):
                if category_columns["t_test_cols"] and col in category_columns["t_test_cols"]:
                    nan_values = True if np.sum(np.isnan(Din))>0 or np.sum(np.isnan(Rin))>0 else False
                    # Perform  t-statistics per column if nan_values=True 
                    t_test, pval = calculate_nan_t_test(Din, Rin[:, col], nan_values=nan_values)    
                    # Store values
                    pval_matrix[:, col] = pval
                    if test_combination is False:
                        test_statistics[perm, :, col] = np.abs(t_test)
                    # save t-test to base_statistics
                    if perm==0 and test_combination==False:
                        base_statistics[:,col]= t_test 
                elif category_columns["f_anova_cols"] and col in category_columns["f_anova_cols"]:
                    nan_values = True if np.sum(np.isnan(Din))>0 or np.sum(np.isnan(Rin))>0 else False
                    # Perform f-statistics
                    f_statistic, pval =calculate_anova_f_test(Din, Rin[:, col], nan_values=nan_values)
                    # Store values
                    pval_matrix[:, col] = pval
                    if test_combination is False:
                        test_statistics[perm, :, col] = np.abs(f_statistic)
                    # Insert base statistics
                    if perm==0 and test_combination==False:
                            base_statistics[:,col]= f_statistic       

                elif category_columns["f_reg_cols"] and col in category_columns["f_reg_cols"]:
                    nan_values = True if np.sum(np.isnan(Din))>0 or np.sum(np.isnan(Rin))>0 else False
                    # Perform f-statistics
                    f_statistic, pval =calculate_reg_f_test(Din, Rin[:, col], idx_data, beta, perm, reg_pinv, permute_beta, test_indices=test_indices)
                    # Store values 
                    pval_matrix[:, col] = pval
                    if test_combination is False:
                        test_statistics[perm, :, col] = np.abs(f_statistic)
                    # Insert base statistics
                    if perm==0 and test_combination==False:
                        base_statistics[:,col]= f_statistic    
                                                          
                else:
                    # Perform correlation analysis and handle NaN values
                    if np.sum(np.isnan(Din))>0 or np.sum(np.isnan(Rin))>0:
                    # Calculate correlation matrix while handling NaN values column by column
                        corr_array, pval =calculate_nan_correlation_matrix(Din, Rin[:, col], True)
                        base_statistics[:, col] =np.squeeze(corr_array)
                        pval_matrix[:, col] = np.squeeze(pval)

                    else:
                        #Calculate correlation coefficient matrix - Faster calculation
                        corr_coef = np.corrcoef(Din, Rin[:, col], rowvar=False)
                        # get the correlation matrix
                        corr_array = np.squeeze(corr_coef[:Din.shape[1], Din.shape[1]:])
                        # Store as correlation coefficients instead
                        base_statistics[:, col] =np.squeeze(corr_array)
                    test_statistics[perm, :, col] = np.abs(base_statistics[:, col])
                    # Insert base statistics
                    # if perm==0 and test_combination==False:
                    #     base_statistics[:,col]= np.squeeze(corr_array)
                            
                          
            if test_combination in [True, "across_columns", "across_rows"]:
                #base_statistics = calculate_combined_z_scores(base_statistics_com, test_combination) if perm==0 else base_statistics_com
                base_statistics, pval_matrix = calculate_combined_z_scores(pval_matrix, test_combination) 
                test_statistics[perm,:] =abs(calculate_combined_z_scores(pval_matrix, test_combination) [0])
                #pval_matrix =geometric_pvalue(pval_matrix, test_combination)


    elif method =="cca":
        # Create CCA object with 1 component
        cca = CCA(n_components=1)
        # Fit the CCA model to your data
        cca.fit(Din, Rin)
        # Transform the input data using the learned CCA model
        X_c, Y_c = cca.transform(Din, Rin)
        # Calcualte the correlation coefficients between X_c and Y_c
        base_statistics = np.corrcoef(X_c, Y_c, rowvar=False)[0, 1]
        # Update test_statistics
        test_statistics[perm] = np.abs(base_statistics)
        pval_matrix = None

    # Check if perm is 0 before returning the result
    stats_results = {"test_statistics":test_statistics,
                     "base_statistics":base_statistics,
                     "pval_matrix": pval_matrix,
                     "F_stats": F_stats,
                     "t_stats": t_stats}

    return stats_results
        
def calculate_combined_z_scores(p_values, test_combination=None):
    """
    Calculate test statistics of z-scores converted from p-values based on the specified combination.

    Parameters:
    --------------
    p_values (numpy.ndarray):  
        Matrix of p-values.
    test_combination (str):       
        Specifies the combination method.
        Valid options: "True", "across_columns", "across_rows".
        Default is "True".

    Returns:
    ----------  
    result (numpy.ndarray):       
        Test statistics of z-scores converted from p-values.
    """
    # Cap p-values slightly below 1 to avoid infinite z-scores
    epsilon = 1e-15
    #p_values =np.expand_dims(p_values,axis=1) if p_values.ndim==1 else p_values
    adjusted_pval = np.clip(p_values, epsilon, 1 - epsilon) #  restricts the values in pval_matrix to lie within the range [epsilon, 1 - epsilon]
    if test_combination == True:        
        pval = np.squeeze(np.exp(np.mean(np.log(adjusted_pval))))                   
        z_scores = norm.ppf(1 - np.array(pval))
        test_statistics = z_scores
    elif test_combination == "across_columns" or test_combination == "across_rows":
        axis = 0 if test_combination == "across_columns" else 1
        # Apply the geoemtric mean based on it is a 2D or 1D array
        pval = np.squeeze(np.exp(np.mean(np.log(adjusted_pval), axis=axis))) if p_values.ndim==2 else np.squeeze(np.exp(np.mean(np.log(adjusted_pval))))
        z_scores = norm.ppf(1 - np.array(pval))
        test_statistics = z_scores
    else:
        z_scores = norm.ppf(1 - np.array(adjusted_pval))
        test_statistics = np.squeeze(z_scores)

    return test_statistics, pval

# Define the inverse Fisher z-transformation function
def inverse_fisher_z(z_matrix):
    """
    Convert z-scores back to correlation coefficients using the inverse Fisher z-transformation.
    
    Parameters:
    z_matrix (ndarray): 
        A matrix of z-scores.
    
    Returns:
    ndarray: 
        A matrix of correlation coefficients.
    """
    return (np.exp(2 * z_matrix) - 1) / (np.exp(2 * z_matrix) + 1)

def pval_correction(result_dic=None, pval=None, method='fdr_bh', alpha=0.05, include_nan=True, nan_diagonal=False):
    """
    Adjusts p-values for multiple testing.

    Parameters:
    --------------
    pval (numpy.ndarray): 
        numpy array of p-values.
    method (str, optional): method used for FDR correction, default='fdr_bh.
        bonferroni : one-step correction
        sidak : one-step correction
        holm-sidak : step down method using Sidak adjustments
        holm : step-down method using Bonferroni adjustments
        simes-hochberg : step-up method (independent)   
        hommel : closed method based on Simes tests (non-negative)
        fdr_bh : Benjamini/Hochberg (non-negative)
        fdr_by : Benjamini/Yekutieli (negative)
        fdr_tsbh : two stage fdr correction (non-negative)
        fdr_tsbky : two stage fdr correction (non-negative)
    alpha (float, optional): 
        Significance level, default= 0.05.
    include_nan, default=True: 
        Include NaN values during the correction of p-values if True. Exclude NaN values if False.
    nan_diagonal, default=False: 
        Add NaN values to the diagonal if True.

    Returns:
    ---------- 
    pval_corrected (numpy.ndarray): 
        numpy array of corrected p-values.
    significant (numpy.ndarray): 
        numpy array of boolean values indicating significant p-values.
    """
    # Use the dictionary values if provided
    if result_dic is not None:
        pval = result_dic["pval"]


    if pval is None:
        raise ValueError("Missing required parameters: pval")
    
    # Input validation
    if nan_diagonal and pval.ndim != 2:
        raise ValueError("If nan_diagonal is True, input pval must be a 2D array.")
    
    if include_nan:
        # Flatten the matrix and keep track of NaN positions
        flat_pval = pval.flatten()
        nan_positions = np.isnan(flat_pval)

        # Replace NaN values with 1 (or any value representing non-significance) for correction
        flat_pval[nan_positions] = 1

        # Perform multiple testing correction
        significant, pval_corrected, _, _ = smt.multipletests(flat_pval, alpha=alpha, method=method, returnsorted=False)

        # Replace the NaN values back in the corrected p-values
        pval_corrected[nan_positions] = np.nan
        significant[nan_positions] = np.nan

        # Reshape the corrected p-value and significant arrays back to the original shape
        pval_corrected = pval_corrected.reshape(pval.shape)
        significant = significant.reshape(pval.shape)

    else:
        # Flatten the matrix and remove NaN values for correction
        flat_pval = pval.flatten()
        non_nan_positions = ~np.isnan(flat_pval)
        flat_pval_no_nan = flat_pval[non_nan_positions]

        # Perform multiple testing correction on non-NaN values
        significant_no_nan, pval_corrected_no_nan, _, _ = smt.multipletests(flat_pval_no_nan, alpha=alpha, method=method, returnsorted=False)

        # Create an array filled with NaN values
        pval_corrected = np.full_like(flat_pval, np.nan)
        significant = np.full_like(flat_pval, np.nan)

        # Assign the corrected values to their respective positions in the original shape
        pval_corrected[non_nan_positions] = pval_corrected_no_nan
        significant[non_nan_positions] = significant_no_nan

        # Reshape the corrected p-value and significant arrays back to the original shape
        pval_corrected = pval_corrected.reshape(pval.shape)
        significant = significant.reshape(pval.shape)

    if nan_diagonal:
        pval_corrected =np.fill_diagonal(pval_corrected, np.nan)
        significant =np.fill_diagonal(significant, np.nan)

    # Return the corrected p-values and boolean values indicating significant p-values
    return pval_corrected, significant

def pval_FWER_correction(result_dic=None, test_statistics=None, Nperm=None, method=None):
    """
    Compute Family-Wise Error Rate (FWER) corrected p-values for multivariate or univariate methods.

    Parameters:
    --------------
    result_dic (dict, default None:
        A dictionary containing "test_statistics", "Nperm", and "method".
    test_statistics (numpy.ndarray), default None:
        The permutation array, where the first row/element contains observed statistics.
    Nperm (int), default None:
        The number of permutations.
    method (str), default None:
        The method used for permutation testing. Can be "multivariate" or "univariate".

    Returns:
    ----------
    pval_FWER (numpy.ndarray):
        FWER-corrected p-values.
    """
    # Use the dictionary values if provided
    if result_dic is not None:
        test_statistics = result_dic["test_statistics"]
        Nperm = result_dic['Nperm']
        method = result_dic['method']

    if test_statistics is None or Nperm is None or method is None:
        raise ValueError("Missing required parameters: test_statistics, Nperm, or method.")

    if method == "multivariate":
        if test_statistics.shape[0] == Nperm:  # Case 1: Without timepoints
            test_statistics = np.expand_dims(test_statistics, axis=1) if test_statistics.ndim == 1 else test_statistics
            # Compute the maximum statistic for each permutation
            max_stats = np.max(test_statistics[1:], axis=1)  # Shape: (Nperm - 1,)

            # Get the observed (unpermuted) statistics (first permutation)
            observed_stats = test_statistics[0, :]  # Shape: (F,)

            # Compute FWER-corrected p-values for each feature
            pval_FWER = (np.sum(max_stats[:, np.newaxis] >= observed_stats, axis=0) + 1) / (Nperm + 1)  # Shape: (F,)
        else:  # Case 2: With timepoints
            n_T = test_statistics.shape[0]
            test_statistics = np.expand_dims(test_statistics, axis=2) if test_statistics[0, :].ndim == 1 else test_statistics
            # Compute the maximum statistic for each timepoint and permutation
            max_stats = np.max(test_statistics[:, 1:, :], axis=2)  # Shape: (T, Nperm - 1)

            # Get the observed (unpermuted) statistics (first permutation for each timepoint)
            observed_stats = test_statistics[:, 0, :]  # Shape: (T, F)

            # Compute FWER-corrected p-values for each timepoint and feature
            pval_FWER = (np.sum(max_stats[:, :, np.newaxis] >= observed_stats[:, np.newaxis, :], axis=1) + 1) / (Nperm + 1)  # Shape: (T, F)

    elif method == "univariate":
        if test_statistics.shape[0] == Nperm:  # Case 1: Without timepoints
            test_statistics = np.expand_dims(test_statistics, axis=2) if test_statistics[0, :].ndim == 1 else test_statistics
            maxT_statistics = np.max(np.abs(test_statistics[1:, :, :]), axis=(1, 2))  # Shape: (Nperm - 1,)
            observed_test_stats = np.abs(test_statistics[0])  # Shape: (p, q)

            # Use broadcasting to compare observed statistics against MaxT statistics - Get a comparison for every combination of permutation, feature, and outcome.
            pval_FWER = (np.sum(maxT_statistics[:, np.newaxis, np.newaxis] >= observed_test_stats, axis=0) + 1) / (Nperm + 1)  # Shape: (p, q)
        else:  # Case 2: With timepoints
            n_T = test_statistics.shape[0]
            test_statistics = np.expand_dims(test_statistics, axis=3) if test_statistics[0, :].ndim == 2 else test_statistics
            pval_FWER = np.zeros((n_T, test_statistics.shape[-2], test_statistics.shape[-1]))  # Shape: (T, p, q)

            for t in range(n_T):
                maxT_statistics = np.max(np.abs(test_statistics[t, 1:, :, :]), axis=(1, 2))  # Shape: (Nperm - 1,)
                observed_test_stats = np.abs(test_statistics[t, 0])  # Shape: (p, q)

                # Use broadcasting to compare observed statistics against MaxT statistics - Get a comparison for every combination of permutation, feature, and outcome.
                pval_FWER[t, :, :] = (np.sum(maxT_statistics[:, np.newaxis, np.newaxis] >= observed_test_stats, axis=0) + 1) / (Nperm + 1)

    else:
        raise ValueError("Invalid method. Must be 'multivariate' or 'univariate'.")

    return np.squeeze(pval_FWER) if pval_FWER.ndim > 2 else pval_FWER

def pval_cluster_based_correction(result_dic = None, test_statistics=[], pval=None, alpha=0.05, individual_feature=False):
    """
    Perform cluster-based correction on test statistics using the output from permutation testing.
    The function corrects p-values by using the test statistics and p-values obtained from permutation testing.
    It converts the test statistics into z-scores, thresholds them to identify clusters, and uses the cluster sizes to adjust the p-values.
        
    Parameters:
    ------------
    test_statistics (numpy.ndarray): 
        2D or 3D array of test statistics.
        For a 2D array, it should have a shape of (timepoints, permutations).
        For a 3D array, it should have a shape of (timepoints, permutations, p), 
        where p represents the number of predictors/features. The first dimension corresponds to timepoints, 
        the second dimension to different permutations, and the third (if present) to multiple features.
    pval (numpy.ndarray): 
        1D or 2D array of p-values obtained from permutation testing.
        For a 1D array, it should have a shape of (timepoints), containing a single p-value per timepoint.
        For a 2D array, it should have a shape of (timepoints, p), where p represents the number of predictors/features.
    alpha (float, optional), default=0.05: 
        Significance level for cluster-based correction.
    individual_feature (bool, optional), default=False: 
        If True, the cluster-based correction is performed separately for each feature in the test_statistics.
        If False, the correction is applied to the entire p-value matrix.
        
    Returns:
    ----------
    p_values (numpy.ndarray): 
        Corrected p-values after cluster-based correction.
    """
    # Use the dictionary values if provided
    if result_dic is not None:
        test_statistics = result_dic.get("test_statistics", test_statistics)
        pval = result_dic.get("pval", pval)

    if test_statistics is [] or pval is None:
        raise ValueError("Missing required parameters: test_statistics or pval.\n"
                         "Remember to set 'test_statistics_option=True' to export the test_statistics when running the test")

    if individual_feature:
        if test_statistics.ndim==3:
            q_size = test_statistics.shape[-1]
            p_values = np.zeros_like(pval)
        else:
            test_statistics = np.expand_dims(test_statistics,2)
            q_size = test_statistics.shape[-1]
            pval = np.expand_dims(pval,axis=1)
            p_values = np.zeros_like(pval)
        for q_i in range(q_size):
            # Compute mean and standard deviation under the null hypothesis
            mean_h0 = np.squeeze(np.mean(test_statistics[:,:,q_i], axis=1))
            std_h0 = np.std(test_statistics[:,:,q_i], axis=1)

            # Initialize array to store maximum cluster sums for each permutation
            Nperm = test_statistics[:,:,q_i].shape[1]
            # Not including the first permuation
            max_cluster_sums = np.zeros(Nperm-1)

            # Define zval_thresh threshold based on alpha
            zval_thresh = norm.ppf(1 - alpha)
            
            # Iterate over permutations to find maximum cluster sums
            for perm in range(Nperm-1):
                # Take each permutation map and transform to Z
                thresh_nperm = (test_statistics[:,perm+1,q_i])
                if np.sum(thresh_nperm)!=0:
                    #thresh_nperm = permmaps[perm, :]
                    thresh_nperm = (thresh_nperm - np.mean(thresh_nperm)) / np.std(thresh_nperm)
                    # Threshold line at p-value
                    thresh_nperm[np.abs(thresh_nperm) < zval_thresh] = 0

                    # Find clusters
                    cluster_label = label(thresh_nperm > 0)
                    if len(np.unique(cluster_label)) > 1:
                        temp_cluster_sums = [np.sum(thresh_nperm[cluster_label == label]) for label in range(1, len(np.unique(cluster_label)))]
                        if temp_cluster_sums:
                            max_cluster_sums[perm] = max(temp_cluster_sums)
                        else:
                            max_cluster_sums[perm] = 0  # No clusters
            # Calculate cluster threshold
            cluster_thresh = np.percentile(max_cluster_sums, 100 - (100 * alpha))

            # Convert p-value map calculated using permutation testing into z-scores
            pval_zmap = norm.ppf(1 - pval[:,q_i])
            # Threshold the p-value map based on alpha
            pval_zmap[(pval_zmap)<zval_thresh] = 0

            # Find clusters in the real thresholded pval_zmap
            # If they are too small, set them to zero
            cluster_labels = label(pval_zmap>0)
        
            for cluster in range(1,len(np.unique(cluster_labels))):
                if np.sum(pval_zmap[cluster_labels == cluster]) < cluster_thresh:
                    #print(np.sum(region.intensity_image))
                    pval_zmap[cluster_labels == cluster] = 0
                    
            # Convert z-map to p-values
            p_values[:,q_i] = 1 - norm.cdf(pval_zmap)
            p_values[p_values[:,q_i] == 0.5, q_i] = 1
    
    else:    
        # Compute mean and standard deviation under the null hypothesis
        mean_h0 = np.squeeze(np.mean(test_statistics, axis=1))
        std_h0 = np.std(test_statistics, axis=1)

        # Initialize array to store maximum cluster sums for each permutation
        Nperm = test_statistics.shape[1]
        # Not including the first permuation
        max_cluster_sums = np.zeros(Nperm-1)

        # Define zval_thresh threshold based on alpha
        zval_thresh = norm.ppf(1 - alpha)
        
        # Iterate over permutations to find maximum cluster sums
        for perm in range(Nperm-1):
            # 
            if test_statistics.ndim==3:
                thresh_nperm = np.squeeze(test_statistics[:, perm+1, :])
                thresh_nperm = (thresh_nperm - mean_h0) / std_h0

                # Threshold image at p-value
                thresh_nperm[np.abs(thresh_nperm) < zval_thresh] = 0

                # Find clusters using connected components labeling
                cluster_label = label(thresh_nperm > 0)
                regions = regionprops(cluster_label, intensity_image=thresh_nperm)
                if regions:
                    # Sum values inside each cluster
                    temp_cluster_sums = [np.sum(region.intensity_image) for region in regions]
                    if temp_cluster_sums:
                        # Store the sum of values for the biggest cluster
                        max_cluster_sums[perm] = max(temp_cluster_sums)
                    else:
                        max_cluster_sums[perm] = 0  # No clusters
                    
            # Otherwise it is a 2D matrix
            else: 
                # Take each permutation map and transform to Z
                thresh_nperm = (test_statistics[:,perm+1])
                if np.sum(thresh_nperm)!=0:
                    #thresh_nperm = permmaps[perm, :]
                    thresh_nperm = (thresh_nperm - np.mean(thresh_nperm)) / np.std(thresh_nperm)
                    # Threshold line at p-value
                    thresh_nperm[np.abs(thresh_nperm) < zval_thresh] = 0

                    # Find clusters
                    cluster_label = label(thresh_nperm > 0)

                    if len(np.unique(cluster_label)>0) or np.sum(cluster_label)==0:
                        # Sum values inside each cluster
                        temp_cluster_sums = [np.sum(thresh_nperm[cluster_label == label]) for label in range(1, len(np.unique(cluster_label)))]
                        if temp_cluster_sums:
                            # Store the sum of values for the biggest cluster
                            max_cluster_sums[perm] = max(temp_cluster_sums)
        # Calculate cluster threshold
        cluster_thresh = np.percentile(max_cluster_sums, 100 - (100 * alpha))

        # Convert p-value map calculated using permutation testing into z-scores
        pval_zmap = norm.ppf(1 - pval)
        # Threshold the p-value map based on alpha
        pval_zmap[(pval_zmap)<zval_thresh] = 0

        # Find clusters in the real thresholded pval_zmap
        # If they are too small, set them to zero
        cluster_labels = label(pval_zmap>0)
        
        if test_statistics.ndim==3:
            regions = regionprops(cluster_labels, intensity_image=pval_zmap)

            for region in regions:
                # If real clusters are too small, remove them by setting to zero
                if np.sum(region.intensity_image) < cluster_thresh:
                    pval_zmap[cluster_labels == region.label] = 0
        else: 
            for cluster in range(1,len(np.unique(cluster_labels))):
                if np.sum(pval_zmap[cluster_labels == cluster]) < cluster_thresh:
                    #print(np.sum(region.intensity_image))
                    pval_zmap[cluster_labels == cluster] = 0
                
        # Convert z-map to p-values
        p_values = 1 - norm.cdf(pval_zmap)
        p_values[p_values == 0.5] = 1
    return p_values

def get_indices_array(idx_data):
    """
    Generates an indices array based on given data indices.

    Parameters:
    --------------
    idx_data (numpy.ndarray): 
        The data indices array.

    Returns:
    ----------  
    idx_array (numpy.ndarray): 
        The generated indices array.
        
    Example:
    ----------      
    >>> idx_data = np.array([[0, 3], [3, 6], [6, 9]])
    >>> get_indices_array(idx_data)
    array([0, 0, 0, 1, 1, 1, 2, 2, 2])

    """
    # Create a copy of idx_data to avoid modifying the original outside the function
    idx_data_copy = np.copy(idx_data)
    
    # # # Check if any values in column 1 are equal to any values in column 2
    # # # If equal remove one value from the second column
    # # # if np.any(np.isin(idx_data_copy[:, 0], idx_data_copy[:, 1])):
    # # #     idx_data_copy[:, 1] -= 1

    # Get an array of indices based on the given idx_data ranges
    max_value = np.max(idx_data_copy[:, 1])
    idx_array = np.zeros(max_value, dtype=int)
    for count, (start, end) in enumerate(idx_data_copy):
        idx_array[start:end] = count
    return idx_array


def get_indices_range(size, step):
    """
    Create a 2D matrix of start and end indices with a fixed step size.

    Parameters:
    --------------
    size (int): 
        The total size of the data to generate indices for.
    step (int): 
        The step size for each range.

    Returns:
    ----------  
    indices (ndarray): 
        A 2D NumPy array where each row represents the start and end indices.
    
    Example:
    ----------
    >>> size = 1000
    >>> step = 250
    >>> get_indices_range(size, step)
    array([[   0,  250],
           [ 250,  500],
           [ 500,  750],
           [ 750, 1000]])
    """
    # Generate start and end indices
    start_values = np.arange(0, size, step)
    end_values = np.arange(step, size + step, step)
    end_values[-1] = size  # Ensure the last value is exactly the size

    # Combine into a 2D array
    indices = np.column_stack((start_values, end_values))

    return indices


def get_indices_timestamp(n_timestamps, n_subjects):
    """
    Generate indices of the timestamps for each subject in the data.

    Parameters:
    --------------
    n_timestamps (int): 
        Number of timestamps.
    n_subjects (int): 
        Number of subjects.

    Returns:
    ----------  
    indices (ndarray): 
        Array representing the indices of the timestamps for each subject.

    Example:
    ----------
    >>> n_timestamps = 3
    >>> n_subjects = 4
    >>> get_indices_timestamp(n_timestamps, n_subjects)
    array([[ 0,  3],
           [ 3,  6],
           [ 6,  9],
           [ 9, 12]])
    """
    indices = np.column_stack([np.arange(0, n_timestamps * n_subjects, n_timestamps),
                               np.arange(0 + n_timestamps, n_timestamps * n_subjects + n_timestamps, n_timestamps)])

    return indices

def get_indices_session(data_label):
    """
    Generate session indices in the data based on provided labels.
    This is done by using 'data_label' to define sessions and generates corresponding indices. 
    The resulting 'idx_data_sessions' array represents the intervals for each session in the data.
    
    Parameters:
    --------------
    data_label (ndarray): 
        Array representing the labels for data to be indexed into sessions.

    Returns:
    ----------  
    idx_data_sessions (ndarray): 
        The indices of datapoints within each session. It should be a 2D array 
        where each row represents the start and end index for a trial. 

    Example:
    ----------
    >>> data_label = np.array([0, 0, 0, 1, 1, 2])
    >>> get_indices_session(data_label)
    array([[0, 3],
           [3, 5],
           [5, 6]])

    """
    # Get unique labels from the data_label array
    unique_labels = np.unique(data_label)

    # Initialize an array to store session indices
    idx_data_sessions  = np.zeros((len(unique_labels), 2)).astype(int)

    # Iterate over unique labels
    for session in range(len(unique_labels)):
        # Count occurrences of the current label in the data_label array
        occurrences = len(data_label[data_label == unique_labels[session]])

        # Update the session indices array
        if session == 0:
            idx_data_sessions [session, 1] = occurrences
        else:
            idx_data_sessions [session, 0] = idx_data_sessions [session - 1, 1]
            idx_data_sessions [session, 1] = idx_data_sessions [session - 1, 1] + occurrences

    # Return the generated session indices array
    return idx_data_sessions 

def get_indices_from_list(data_list, count_timestamps = True):
    """
    Generate indices representing the start and end timestamps for each subject or session from a given data list.

    Parameters:
    --------------
    data_list (list): 
        List containing data for each subject or session.
    count_timestamps (bool), default=True: 
        If True, counts timestamps for each element in data_list, otherwise assumes each element in data_list is already a count of timestamps.

    Returns:
    ----------  
    indices (ndarray): 
        Array with start and end indices for each subject's timestamps.
    
    Example:
    ----------
    >>> data_list = [[1, 2, 3], [4, 5], [6]]
    >>> get_indices_from_list(data_list, count_timestamps=True)
    array([[0, 3],
           [3, 5],
           [5, 6]])

    >>> data_list = [3, 2, 1]
    >>> get_indices_from_list(data_list, count_timestamps=False)
    array([[0, 3],
           [3, 5],
           [5, 6]])
    """
    # Initialize an empty NumPy array to store start and end indices for each subject
    indices = np.zeros((len(data_list), 2), dtype=int)
    
    # Iterate through each element in the data list along with its index
    for i, data in enumerate(data_list):
        if count_timestamps:
            # Get the number of timestamps for the current subject or session
            n_timestamps = len(data)
        else: 
            n_timestamps = data 
        
        # Update indices based on whether it's the first subject or subsequent ones
        if i == 0:
            indices[i, 1] = n_timestamps  # For the first subject, set the end index
        else:
            indices[i, 0] = indices[i - 1, 1]  # Set the start index based on the previous subject's end index
            indices[i, 1] = indices[i - 1, 1] + n_timestamps  # Set the end index
        
    # Return the generated indices array
    return indices

def get_indices_update_nan(idx_data, nan_mask):
    """
    Update interval indices based on missing values in the data.

    Parameters:
    -----------
    idx_data (numpy.ndarray):
        Array of shape (n_intervals, 2) representing the start and end indices of each interval.
    nan_mask (bool):
        Boolean mask indicating the presence of missing values in the data.

    Returns:
    --------
    idx_data_update (numpy.ndarray):
        Updated interval indices after accounting for missing values.
    """
    # Find the indices of missing values
    nan_vals = np.where(nan_mask)
    #nan_flat = nan_vals.flatten()
    # Digitize the indices of missing values to determine which interval they belong to
    count_vals_digitize = np.digitize(nan_vals, idx_data[:, 0]) - 1
    
    if len(nan_vals[0]) > 1:
        # Sort the digitized values and count the occurrences
        count_vals_digitize_flat = count_vals_digitize.flatten()  # Convert to tuple
        #count_vals_digitize_tuple= tuple(count_vals_digitize_flat.sort())
        counts = Counter(count_vals_digitize_flat)
        
        # Update the interval indices
        idx_data_update = idx_data.copy()
        for i in range(len(idx_data)):
            if i == 0:
                idx_data_update[0, 1] -= counts[i]
                idx_data_update[1:] -= counts[i]
            else:
                idx_data_update[i:] -= counts[i]
    else:
        # If only one missing value, update the interval indices accordingly
        idx_data_update = idx_data.copy()
        count_vals_digitize = count_vals_digitize[0]
        if count_vals_digitize == 0:
            idx_data_update[0, 1] -= 1
            idx_data_update[1:] -= 1
        else:
            idx_data_update[count_vals_digitize-1, 1] -= 1
            idx_data_update[count_vals_digitize:] -= 1
    
    return idx_data_update

def get_concatenate_data_memmap(D_raw, filename="D_con.dat"):
    """
    Saves a list of NumPy arrays (D_raw) into a memory-mapped file to optimize RAM usage.
    
    Parameters:
    -----------
    D_raw : list of np.ndarray
        List containing session-wise NumPy arrays with the same number of columns.
    filename : str, optional
        Name of the memory-mapped file to store the concatenated dataset (default is "D_con.dat").
    
    Returns:
    --------
    np.memmap
        Memory-mapped NumPy array containing the concatenated data.
    """
    if not D_raw:
        raise ValueError("D_raw cannot be empty.")
    
    # Define the shape dynamically based on D_raw
    total_samples = sum(d.shape[0] for d in D_raw)
    num_features = D_raw[0].shape[1]
    
    # Create a memory-mapped file
    D_con_dat = np.memmap(filename, dtype=D_raw[0].dtype, mode="w+", shape=(total_samples, num_features))
    
    # Write data incrementally
    start = 0
    for d in D_raw:
        end = start + d.shape[0]
        D_con_dat[start:end] = d  # Copy data into memory-mapped file
        start = end

    # Convert memmap to a regular NumPy array
    D_con = np.array(D_con_dat)
    
    # Explicitly delete the memmap object before removing the file
    del D_con_dat
    
    # Remove the temporary memory-mapped file
    os.remove(filename)

    return D_con 

def get_concatenate_subjects(D_sessions):
    """
    Converts a 3D matrix into a 2D matrix by concatenating timepoints of every subject into a new D-matrix.

    Parameters:
    --------------
    D_sessions (numpy.ndarray): 
        D-matrix for each subject.

    Returns:
    ----------  
    D_con (numpy.ndarray): 
        Concatenated D-matrix.
    """
    D_con = []

    for i in range(D_sessions.shape[1]):
        # Extend D-matrix with selected trials
        D_con.extend(D_sessions[:, i, :])

    return np.array(D_con)

def get_concatenate_sessions(D_sessions, R_sessions=None, idx_sessions=None):
    """
    Converts a  3D matrix into a 2D matrix by concatenating timepoints of every trial session into a new D-matrix.

    Parameters:
    --------------
    D_sessions (numpy.ndarray): 
        D-matrix for each session.
    R_sessions (numpy.ndarray): 
        R-matrix time for each trial.
    idx_sessions (numpy.ndarray): 
        Indices representing the start and end of trials for each session.

    Returns:
    ----------  
    D_con (numpy.ndarray): 
        Concatenated D-matrix.
    R_con (numpy.ndarray): 
        Concatenated R-matrix.
    idx_sessions_con (numpy.ndarray): 
        Updated indices after concatenation.
    """
    if idx_sessions is None:
        raise ValueError("idx_sessions cannot be None")
    D_con, R_con, idx_sessions_con = [], [], np.zeros_like(idx_sessions)

    for i, (start_idx, end_idx) in enumerate(idx_sessions):
        # Iterate over trials in each session
        for j in range(start_idx, end_idx):
            # Extend D-matrix with selected trials
            D_con.extend(D_sessions[:, j, :])
            if R_sessions is not None:
                # Extend time list for each trial
                R_con.extend([R_sessions[j]] * D_sessions.shape[0])


        # Update end index for the concatenated D-matrix
        idx_sessions_con[i, 1] = len(D_con)

        if i < len(idx_sessions) - 1:
            # Update start index for the next session if not the last iteration
            idx_sessions_con[i + 1, 0] = idx_sessions_con[i, 1]

    # Convert lists to numpy arrays
    return np.array(D_con), np.array(R_con), idx_sessions_con


def reconstruct_concatenated_to_3D(D_con, D_original=None, n_timepoints=None, n_entities=None, n_features = None):
    """
    Reshape a concatenated 2D matrix back into its original 3D format (timepoints, trials, channels).
    
    This function converts a concatenated 2D matrix `D_con` (e.g., from HMM Gamma values)
    back into its original 3D shape. If the original session matrix `D_original` is provided,
    the function will infer the number of timepoints, trials, and channels from its shape. 
    Otherwise, the user must provide the correct dimensions.
    
    Parameters:
    ------------
    D_con (numpy.ndarray): 
        A 2D concatenated D-matrix of shape ((n_timepoints * n_entities), n_features).
    D_original (numpy.ndarray, optional): 
        A 3D array containing the original D-matrices for each session, with shape (n_timepoints, n_entities, n_features).
    n_timepoints (int, optional): 
        A number of timepoints per trial, is required if `D_original` is not provided.
    n_entities (int, optional): 
        A number of e.g. trials or subjects per session, is required if `D_original` is not provided.
    n_features (int, optional): 
        Number of features (e.g. channels), required if `D_original` is not provided.

    Returns:
    ---------
    D_reconstruct (numpy.ndarray): 
        A 3D array containing the reconstructed D-matrix for each session, with shape (n_timepoints, n_entities, n_features).

    Raises:
    --------
    ValueError: 
        If `D_original` is provided and is not a 3D numpy array, or if the provided dimensions do not match the shape of `D_con`.
        If `n_timepoints`, `n_trials`, or `n_features` are not provided when `D_original` is missing.
        If the shape of `D_con` does not match the expected dimensions based on the input parameters.
    """
    # Input validation and initialization
    if D_original is not None and len([arg for arg in [n_timepoints, n_entities, n_features] if arg is not None]) == 0:
        if not isinstance(D_original, np.ndarray) or D_original.ndim != 3:
            raise ValueError("Invalid input: D_original must be a 3D numpy array.")
        n_timepoints, n_entities, n_features = D_original.shape
        D_reconstruct = np.zeros_like(D_original)
    else:
        if None in [n_timepoints, n_entities, n_features]:
            raise ValueError("Invalid input: n_timepoints, n_trials, and n_features must be provided if D_original is not provided.")
        D_reconstruct = np.zeros((n_timepoints, n_entities, n_features))
    
    # Check if the shape of D_con matches the expected shape
    if D_con.shape != (n_timepoints * n_entities, n_features):
        raise ValueError("Invalid input: D_con does not match the expected shape.")

    # Assign values from D_con to D_reconstruct
    for i in range(n_entities):
        start_idx = i * n_timepoints
        end_idx = (i + 1) * n_timepoints
        D_reconstruct[:, i, :] = D_con[start_idx:end_idx, :]
    return D_reconstruct



def pad_vpath(vpath, lag_val, indices_tde=None):
    """
    Pad the Viterbi path with repeated first and last rows.

    This function adds padding to the beginning and end of a given Viterbi path (vpath) from a Hidden Markov Model 
    by repeating the first and last rows a specified number of times (lag_val). This is useful for maintaining 
    boundary conditions in scenarios such as sequence alignment or signal processing where the state 
    transitions need to be preserved.

    Parameters:
    ------------
    vpath (numpy.ndarray): 
        A 2D array representing the Viterbi path, where each row corresponds to a specific state in the HMM 
        and each column represents different features or observations.
    lag_val (int): 
        The number of times to repeat the first and last rows for padding.
    indices_tde (list of tuples, optional): 
        A list of tuples, where each tuple contains the start and end indices of individual sequences 
        within the vpath. If provided, padding is applied to each sequence separately.
    indices_tde (numpy.ndarray): 
        Is a 2D array where each row represents the start and end index for a session for the TDE-HMM dataset.
        
    Returns:
    ---------
    numpy.ndarray: 
        A new 2D array containing the padded Viterbi path, with shape ((lag_val + n_rows + lag_val), n_features), 
        where n_rows is the original number of rows in vpath and n_features is the number of features.

    Raises:
    --------
    ValueError: 
        If `lag_val` is not a positive integer, or if `vpath` is not a 2D numpy array.
    """
    # Input validation
    if not isinstance(vpath, np.ndarray) or vpath.ndim != 2:
        raise ValueError("Invalid input: vpath must be a 2D numpy array.")
    if not isinstance(lag_val, int) or lag_val <= 0:
        raise ValueError("Invalid input: lag_val must be a positive integer.")
    if indices_tde is not None:
        if not isinstance(indices_tde, np.ndarray) or vpath.ndim != 2 or indices_tde[-1][-1]!=len(vpath):
            raise ValueError("Invalid input: indices_tde does not match with vpath.")
    if indices_tde is None:
        # Get the first and last rows
        first_row = vpath[0]
        last_row = vpath[-1]

        # Create padding for the beginning and the end
        beginning_padding = np.tile(first_row, (lag_val, 1))
        end_padding = np.tile(last_row, (lag_val, 1))

        # Concatenate the padding with the original vpath
        vpath_pad = np.vstack((beginning_padding, vpath, end_padding))
    else:
        # Multiple sequence padding based on indices_tde
        vpath_list=[]
        for start, end in indices_tde:
            # Get the first and last rows
            first_row = vpath[start]
            last_row = vpath[end-1]

            # Create padding for the beginning and the end
            beginning_padding = np.tile(first_row, (lag_val, 1))
            end_padding = np.tile(last_row, (lag_val, 1))

            # Append each session to the empty list
            vpath_list.append(np.vstack((beginning_padding, vpath[start:end], end_padding)) )
            # Concatenate the padding with the original vpath
            vpath_pad = np.concatenate(vpath_list,axis=0)
    return vpath_pad

def get_event_epochs(input_data, index_data, filtered_R_data, event_markers, 
                               fs, fs_target=None, ms_before_stimulus=0, epoch_window_tp=None):
    """
    Extract time-locked data epochs based on stimulus events.

    This function processes 2D input data to extract epochs aligned to specific stimulus events. 
    The epochs are extracted based on provided event files and are resampled to the target rate. 
    The function also returns relevant indices and concatenates filtered R data across sessions.

    Parameters:
    ------------
    input_data (numpy.ndarray): 
        2D array containing gamma values for the session, structured as ((number of timepoints * number of trials), number of states).
    index_data (numpy.ndarray): 
        2D array containing preprocessed indices for the session.
    filtered_R_data (list): 
        List of filtered R data arrays for each session based on the events.
    event_markers (list): 
        List of event information for each session.
    fs (int, optional): 
        The original sampling frequency in Hz. Defaults to 1000 Hz.
    fs_target (int, optional): 
        The target sampling frequency in Hz after resampling. Defaults to 250 Hz.
    ms_pre_stimulus (int, optional): 
        Time in milliseconds to offset the start of the epoch before the stimulus onset. Defaults to 0 ms.
    epoch_window_tp
        Epoch window length in time points. If None, a default duration of 1 second (equal to fs_target) is used.

    Returns:
    ---------
    epoch_data (numpy.ndarray): 
        3D array of extracted data epochs, structured as (number of timepoints, number of trials, number of states).
    epoch_indices (numpy.ndarray): 
        Array of indices corresponding to the extracted epochs for each session.
    concatenated_R_data (numpy.ndarray): 
        Concatenated array of R data across all sessions.
    """
    if fs_target== None:
        fs_target = fs.copy()
    # Calculate the downsampling factor
    downsampling_factor = fs / fs_target
    # Set default duration to 1 second if None
    epoch_window_tp = fs_target if epoch_window_tp is None else epoch_window_tp 
    # Calculate the shift for the stimulus onset
    stimulus_shift = ms_before_stimulus / downsampling_factor if ms_before_stimulus != 0 else 0

    # Initialize lists to store gamma epochs, filtered R data, and index data
    data_epochs_list = []  
    filtered_R_data_list = []  
    valid_epoch_counts = []  

    # Iterate over each event file corresponding to a session
    for idx, events in enumerate(event_markers):
        # Extract data values for the specific session using preprocessed indices
        data_session = input_data[index_data[idx, 0]:index_data[idx, 1], :]


        # Downsample the event time indices
        downsampled_events = (events[:, 0] / downsampling_factor).astype(int)

        # Calculate differences between consecutive events
        event_differences = np.diff(downsampled_events, axis=0)

        # Identify valid events that are sufficiently spaced apart
        valid_event_indices = (event_differences >= epoch_window_tp)

        # Ensure the first event is included if it meets the downsample condition
        if event_differences[0] >= epoch_window_tp:
            valid_event_indices = np.concatenate(([True], valid_event_indices))

        # Filter events that meet the downsample condition
        valid_event_indices &= (len(data_session) - downsampled_events >= epoch_window_tp)

        # Select filtered event indices based on the downsample condition
        filtered_event_indices = downsampled_events[valid_event_indices]

        # Counter for the number of valid trials
        trial_count = 0  

        # Iterate over each filtered event
        for event_index in filtered_event_indices:
            start_index = event_index + stimulus_shift  # Adjust start index to include time before stimulus
            end_index = start_index + epoch_window_tp  # Define end index for the epoch

            # Append the data for this epoch to the data_epochs_list
            data_epochs_list.append(data_session[start_index:end_index, :])

            trial_count += 1  # Increment the trial counter

        # Append the filtered R data to the filtered_R_data_list
        filtered_R_data_list.append(filtered_R_data[idx][valid_event_indices])

        # Store the count of valid epochs for this session in the valid_epoch_counts
        valid_epoch_counts.append(np.sum(valid_event_indices))

    # Convert the data_epochs_list to a NumPy array and transpose it for correct dimensions
    epoch_data = np.transpose(np.array(data_epochs_list), (1, 0, 2))

    # Concatenate all filtered R data along the first axis
    epoch_R_data = np.concatenate(filtered_R_data_list, axis=0)

    # Calculate the indices for the epoch data using a custom function
    epoch_indices = get_indices_from_list(valid_epoch_counts, count_timestamps=False)

    # Return the processed data
    return epoch_data, epoch_indices, epoch_R_data

def categorize_columns_by_statistical_method(R_data, method, Nperm, identify_categories=False, category_lim=None,permute_beta=False, test_combination=False, pairwise_statistic=False):
    """
    Detects categorical columns in R_data and categorizes them for later statistical testing (t-tests, F-tests, etc.).
    This function helps identify which columns are binary or categorical, and applies permutation inference based on the test statistics.

    Parameters:
    -----------
    R_data : numpy.ndarray 
        The 3D array (e.g., N x T x q) containing the data where categorical values need to be detected.
    method : str, optional
        The statistical method applied to the columns. Supported values are:
        "univariate", "multivariate", "osr", "osa".
    identify_categories : bool, list, or numpy.ndarray, optional (default=False)
        If True, automatically identify categorical columns. 
        If a list or ndarray, the provided column indices are used for categorization.
    category_lim : int or None, optional (default=None)
        The maximum allowed number of unique categories for an F-test. Used to prevent misidentifying 
        continuous variables (like age) as categorical.
    permute_beta : bool, optional (default=False)
        Determines whether to use permutation testing on regression beta values.
    test_combination : bool, optional (default=False)
        If True, combination testing (e.g., z-scores) is applied.
    pairwise_statistic : str, optional (default="mean")
        The statistic used in pairwise comparisons for methods like "osr" or "osa". 
        Supported values are "mean" or "median".

    Returns:
    -----------
    category_columns : dict
        A dictionary with the following keys:
        - 't_test_cols': Columns where t-tests are applied (binary variables).
        - 'f_anova_cols': Columns where F-tests (ANOVA) are applied (categorical variables).
        - 'f_reg_cols': Columns to apply F-regression on (continuous variables).
        - Other keys depending on method, such as 'r_squared', 'corr_coef', or 'z_score' for different tests.
    """
    category_columns = {'t_test_cols': [], 'f_anova_cols': [], 'f_reg_cols': []} 
    idx_cols =np.arange(R_data.shape[-1])
    # Perform categorical detection based on identify_categories input
    # This checks if identify_categories is either True or a list/ndarray
    if identify_categories == True or isinstance(identify_categories, (list,np.ndarray)):
        # Initialize variable
        if identify_categories==True:
        # If identify_categories is True, the function will automatically identify binary columns
            if method!="multivariate" or permute_beta:
                category_columns["t_test_cols"] = [col for col in range(R_data.shape[-1]) if np.unique(R_data[0,:, col]).size == 2]
            if category_lim != None:
                # If method is not "multivariate" or permute_beta is True, identify binary columns in R_data
                if method == "multivariate":
                    category_columns["f_anova_cols"] = [col for col in range(R_data.shape[-1]) 
                                    if np.unique(R_data[0,:, col]).size >= 2  # Check if more than 2 unique values
                                    and np.unique(R_data[0,:, col]).size < category_lim] # Check if the data type is above category_lim
                else:
                    category_columns["f_anova_cols"] = [col for col in range(R_data.shape[-1]) 
                                                    if np.unique(R_data[0,:, col]).size > 2  # Check if more than 2 unique values
                                                    and np.unique(R_data[0,:, col]).size < category_lim] # Check if the data type is above category_lim
                # idx_test is a list of all binary and categorical columns
                idx_test = category_columns["t_test_cols"]+category_columns["f_anova_cols"]
                # The remaining columns, which are not binary or categorical, are treated as continuous
                if permute_beta or Nperm==1 and method=="multivariate":
                    category_columns["f_reg_cols"] = list(idx_cols[~np.isin(idx_cols,idx_test)]) 
                elif permute_beta is False and method=="multivariate":
                    category_columns["r_squared_cols"] = list(idx_cols[~np.isin(idx_cols,idx_test)]) 
                elif permute_beta is False and method=="univariate":
                    category_columns["corr_coef_cols"] = list(idx_cols[~np.isin(idx_cols,idx_test)]) 
                if test_combination!=False:
                    category_columns['z_score'] = 'all_columns'

            else:

                unique_counts = [np.unique(R_data[0, :, col]).size for col in range(R_data.shape[-1])]

                if max(unique_counts) > category_lim:
                    warnings.warn(
                        f"Detected more than {category_lim} unique numbers in column {idx_cols[np.array(unique_counts)>category_lim]} dataset. "
                        f"If this is not intended as categorical data, you can ignore this warning. "
                        f"Otherwise, consider defining 'category_lim' to set the maximum allowed categories or specifying the indices of categorical columns."
                    )
                 
        else:
            # Identify user-defined binary columns
            if method!="multivariate" or permute_beta:
                # Customize columns defined by the user
                category_columns["t_test_cols"] = [col for col in identify_categories if np.unique(R_data[0,:, col]).size == 2]
            # Remove binary columns from the provided categorical columns to get non-binary columns
            identify_categories_filtered = [value for value in identify_categories if value not in category_columns["t_test_cols"]]
            if category_lim != None:
                # If category_lim is provided, add columns with unique values between 2 and category_lim to 'f_anova_cols'
                category_columns["f_anova_cols"] = [col for col in identify_categories_filtered 
                                                   if np.unique(R_data[0,:, col]).size > 2 
                                                   and np.unique(R_data[0,:, col]).size < category_lim]
            else:
                # Otherwise, add columns with more than 2 unique values
                category_columns["f_anova_cols"] = [col for col in identify_categories_filtered 
                                                   if np.unique(R_data[0,:, col]).size > 2]
    # Handling cases where no categorical detection is requested
    else:
        # If test_combination is True, apply z-score to all columns
        if test_combination!=False:
            category_columns['z_score'] = 'all_columns'
        # If method is univariate, apply r^2 score or correlation coefficient depending on permute_beta
        elif method == "univariate":
            category_columns['r_squared_cols' if permute_beta else 'corr_coef_cols'] = 'all_columns'
        # If method is multivariate, apply r^2 coefficient
        elif method == "multivariate":
            category_columns['r_squared_cols'] = 'all_columns'
        # If method is either osr or osa, apply the chosen pairwise_statistic (mean or median)
        elif method == "osr" or method =="osa":
            category_columns[pairwise_statistic] = 'all_columns'
            
    return category_columns

def calculate_regression_statistics(Din, Rin, reg_pinv=None, idx_data=None, permute_beta=None, perm=0, beta=None, test_indices=None, nan_values=None):
    """
    Calculate the R-squared values for the regression of each dependent variable 
    in Rin on the independent variables in Din, while handling NaN values column-wise.

    Parameters:
    --------------
    Din (numpy.ndarray): 
        Input data matrix for the independent variables.
    Rin (numpy.ndarray): 
        Input data matrix for the dependent variables.
    reg_pinv (numpy.ndarray), default None: 
        The regularized pseudo-inverse of D_data
    idx_data (numpy.ndarray): 
        Marks the indices for each trial within the session.
        It is a 2D array where each row represents the start and end index for a session.
    permute_beta (bool, optional): 
        A flag indicating whether to permute beta coefficients.
    beta (numpy.ndarray):
        beta coefficient for each session.
        It has a shape (num_session, p, q), where the first dimension 
        represents the session, the second dimension represents the featires, 
        and the third dimension represent dependent variables. 
    test_indices (numpy.ndarray):
        Indices for data points that belongs to the test-set for each session.
    nan_values (bool, optional): 
        A flag indicating there are NaN values.

    Returns:
    ----------  
        R2_stats (numpy.ndarray): Array of R-squared values for each regression.
    """
    

    n, p = Din.shape
    q = Rin.shape[-1]
    R2_stats = np.zeros(q) 
    F_stats = np.zeros(q) 
    t_stats = np.zeros((p, q))  # Initialize t-statistics matrix (12 x 15) 

    if nan_values:
        Rin = np.expand_dims(Rin, axis=1) if Rin.ndim==1 else Rin
        
        df1 =p     
        df2_list = []  # To store df2 for each regression
        
        # Calculate t-statistic for each pair of columns (D_column, R_data)
        for q_i in range(q):
            if permute_beta and idx_data is not None:
                test_idx = np.concatenate(test_indices,axis=0)
                R_column = np.expand_dims(Rin[test_idx, q_i],axis=1)
                valid_indices = np.all(~np.isnan(R_column), axis=1)
                nan_values = np.any(np.isnan(valid_indices))
                beta_column = beta[:,:,q_i]
                # Calculate the predicted values using permuted beta
                R_pred =calculate_ols_predictions(R_column, Din[test_idx,:], idx_data, beta_column, perm, permute_beta, nan_values,  valid_indices)
                R_pred = np.expand_dims(R_pred,axis=1) if R_pred.ndim==1 else R_pred
                n_valid =sum(valid_indices)
                df2 = n_valid - p  # Compute df2 for the current regression
                df2_list.append(df2)  # Store df2
                # Loop over each session to compute session-specific predictions and t-statistics
                current_index = 0
                for idx, idx_test in enumerate(test_indices):
                    n_session = len(idx_test) 
                    Din_session = Din[idx_test, :]
                    Rin_session = Rin[idx_test, :]
                    beta_session = beta[idx, :, :]  # Shape: (p, q)
                    
                    # Compute residuals for this session
                    residuals = Rin_session - R_pred[current_index:current_index + n_session, :]
                    
                    # Compute residual variance for each dependent variable in this session
                    df2_session = Din_session.shape[0] - p  # Degrees of freedom for this session
                    residual_variance_session = np.sum(residuals**2, axis=0) / df2_session  # Shape: (q,)
                    
                    # Compute standard error for each predictor in this session
                    se_beta_session = np.sqrt(residual_variance_session / np.sum(Din_session**2, axis=0)[:, np.newaxis])  # Shape: (p, q)
                    
                    # Compute t-statistics for this session and accumulate
                    t_stats += beta_session / se_beta_session  # Accumulate t-stats across sessions
                    current_index += n_session  # Update start index for next session
                # Average t-stats across sessions
                t_stats /= len(test_indices)

            elif idx_data is not None: 
                # Do not permute beta but calculate each session individually
                R_column = np.expand_dims(Rin[:, q_i],axis=1)
                valid_indices = np.all(~np.isnan(R_column), axis=1)
                # Detect if there are any NaN values
                nan_values= np.any(np.isnan(valid_indices))
                beta_column = beta[:,:,q_i]
                # Calculate the predicted values without permuting beta, since permute_beta =False
                R_pred =calculate_ols_predictions(R_column, Din, idx_data, beta_column, perm, permute_beta, nan_values,  valid_indices)
                R_pred = np.expand_dims(R_pred,axis=1) if R_pred.ndim==1 else R_pred
                n_valid =sum(valid_indices)
                df2 = n_valid - p  # Compute df2 for the current regression
                df2_list.append(df2)  # Store df2
  
                
            else:
                R_column = np.expand_dims(Rin[:, q_i],axis=1)
                valid_indices = np.all(~np.isnan(R_column), axis=1)
                # Calculate beta using the regularized pseudo-inverse of D_data
                beta = reg_pinv[:,valid_indices] @ R_column[valid_indices]  # Calculate regression_coefficients (beta)
                # Calculate the predicted values
                R_pred = Din[valid_indices] @ beta
                n_valid =sum(valid_indices)
                df2 = n_valid - p  # Compute df2 for the current regression
                df2_list.append(df2)  # Store df2

            
            # Calculate the total sum of squares (tss)
            tss = np.sum((R_column[valid_indices] - np.mean(R_column[valid_indices], axis=0))**2, axis=0)
            # Calculate the residual sum of squares (rss)
            rss = np.sum((R_column[valid_indices]-R_pred)**2, axis=0)

            # Calculate R^2 for the current dependent variable
            R2_stats[q_i] = 1 - (rss / tss)
            # Calculate F_stats
            F_stats[q_i] = (R2_stats[q_i] / df1) / ((1 - R2_stats[q_i]) / df2)

            if permute_beta == False:
                # Calculate residual variance and standard error for each predictor
                residual_variance = rss / df2
                se_beta = np.sqrt(residual_variance / np.sum((Din - np.mean(Din, axis=0)) ** 2, axis=0))

                # Calculate t-statistics for each predictor
                t_stats[:, q_i] = beta.flatten() / se_beta
    else:
        
        # Fit the  model 
        beta= reg_pinv @ Rin  # Calculate regression_coefficients (beta)
        # Calculate the predicted values
        R_pred = Din @ beta   
        # Calculate the residual sum of squares (rss)
        rss = np.sum((Rin-R_pred)**2, axis=0)
        # Calculate the total sum of squares (tss)
        tss = np.sum((Rin - np.nanmean(Rin, axis=0))**2, axis=0)

        # Calculate R^2 for the current dependent variable
        R2_stats = 1 - (rss / tss)

        # Degress of freedom
        df1 = p  
        df2 = n - p
        # Calculate F_stats
        F_stats = (R2_stats / df1) / ((1 - R2_stats) / df2)
        # Calculate residual variance and standard error for each predictor
        residual_variance = rss / df2
        for q_i in range(len(residual_variance)):
            # Calculate standard error for each predictor in Din for the current dependent variable
            se_beta = np.sqrt(residual_variance[q_i] / np.sum((Din - np.mean(Din, axis=0)) ** 2, axis=0))
            # Calculate t-statistics for each predictor for the current dependent variable
            t_stats[:, q_i] = beta[:,q_i].flatten() / se_beta
    return R2_stats, F_stats, t_stats

def regresstion_stats(Din, Rin,R_pred, beta_perm, idx_data):
    """
    Compute regression statistics (R-squared, F-statistics, and t-statistics) for ordinary least squares (OLS) regression 
    across multiple sessions.

    Parameters:
    --------------
    Din (numpy.ndarray): 
        The design matrix (D-matrix) containing independent variables. Shape: (n, p), 
        where n is the number of observations and p is the number of predictors.   
    Rin (numpy.ndarray): 
        The dependent variable matrix (R-matrix) containing observed values. Shape: (n, q), 
        where q is the number of dependent variables.  
    R_pred (numpy.ndarray): 
        The predicted response matrix. Shape: (n, q).
    beta_perm (numpy.ndarray): 
        The array of permuted regression coefficients for each session. Shape: (num_sessions, p, q).
    idx_data (numpy.ndarray): 
        A 2D array where each row represents the start and end indices for a session. Shape: (num_sessions, 2).

    Returns:
    ----------
    R2_stats (numpy.ndarray): 
        R-squared values for each dependent variable. Shape: (q,).
    F_stats (numpy.ndarray): 
        F-statistics for each dependent variable. Shape: (q,).
    t_stats (numpy.ndarray): 
        Average t-statistics across sessions for each predictor and dependent variable. Shape: (p, q).
    """

    n, p = Din.shape
    q = Rin.shape[-1]
    # Initialize matrices for statistics
    rss = np.sum((Rin - R_pred) ** 2, axis=0)  # Residual sum of squares (shape: q)
    tss = np.sum((Rin - np.nanmean(Rin, axis=0)) ** 2, axis=0)  # Total sum of squares (shape: q)

    # Calculate R^2 for each dependent variable
    R2_stats = 1 - (rss / tss)

    # Degrees of freedom
    df1 = p
    df2 = n - p

    # Calculate F-statistics for each dependent variable
    F_stats = (R2_stats / df1) / ((1 - R2_stats) / df2)

    t_stats = np.zeros((p, q))  # T-statistics matrix (p x q)

    # Loop over each session to compute session-specific predictions and t-statistics
    for idx, (start, end) in enumerate(idx_data):
        Din_session = Din[start:end, :]
        Rin_session = Rin[start:end, :]
        beta_session = beta_perm[idx, :, :]  # Shape: (p, q)
        
        # Compute predicted response for this session
        R_pred[start:end, :] = Din_session @ beta_session
        
        # Compute residual variance for each dependent variable in this session
        df2_session = Din_session.shape[0] - p  # Degrees of freedom for this session

        # Compute residuals for this session
        residuals = Rin_session - R_pred[start:end, :]
        residual_variance_session = np.sum(residuals**2, axis=0) / df2_session  # Shape: (q,)
        
        # Compute standard error for each predictor in this session
        se_beta_session = np.sqrt(residual_variance_session / np.sum(Din_session**2, axis=0)[:, np.newaxis])  # Shape: (p, q)
        
        # Compute t-statistics for this session and accumulate
        t_stats += beta_session / se_beta_session  # Accumulate t-stats across sessions

    # Average t-stats across sessions
    t_stats /= len(idx_data)

    return R2_stats, F_stats, t_stats


def preprocess_response(Rin):
    """
    Converting R_in into to dummy variables, and centering the data around zero.

    Parameters:
    --------------
    Rin (numpy.ndarray or pandas.Series): 
        Input array representing the dependent variable. Can be 1D or 2D. 
        If 1D, it will be flattened and converted to dummy variables.

    Returns:
    ----------
    Rin_centered (numpy.ndarray): 
        A 2D array of centered dummy variables based on the input response.
    """
    # Ensure Rin is a 2D array
    Rin = np.atleast_2d(Rin)

    # Handle the case where Rin was originally a 1D array
    if Rin.shape[0] == 1:
        Rin = Rin.T  # Transpose to make it a column vector if necessary

    # Convert to dummy variables and center
    Rin = pd.get_dummies(Rin.flatten(), drop_first=False).values
    Rin_centered = Rin - np.mean(Rin, axis=0)  # Center the response data around 0

    return Rin_centered

def calculate_nan_anova_f_test(Din, Rin, reg_pinv, idx_data, permute_beta, perm=0, nan_values=False, beta= None):
    """
    Calculate the f-test values for the regression of each dependent variable 
    in Rin on the independent variables in Din, while handling NaN values column-wise.

    Parameters:
    --------------
    Din (numpy.ndarray): 
        Input data matrix for the independent variables.
    Rin (numpy.ndarray): 
        Input data matrix for the dependent variables.
    reg_pinv (numpy.ndarray): 
        The regularized pseudo-inverse of D_data.
    idx_data (numpy.ndarray): 
        Marks the indices for each trial within the session.
        It is a 2D array where each row represents the start and end index for a session.       
    permute_beta (bool, optional): 
        A flag indicating whether to permute beta coefficients.
    perm (int): 
        The permutation index.
    nan_values (bool, optional), default=False:: 
        A flag indicating whether there are NaN values.
    beta (numpy.ndarray):
    
    Returns:
    ----------  
        R2_test (numpy.ndarray): Array of f-test values for each regression.
    """
    if nan_values:
        # Calculate F-statistics if there are Nan_values
        # Expand the dimension of Rin, if it is just a single array and center Rin
        Rin = preprocess_response(Rin)
        q = Rin.shape[-1]
        p_value = np.zeros(q)
        f_statistic = np.zeros(q)
        # Calculate t-statistic for each pair of columns (D_column, R_data)
        for i in range(q):
            # Indentify columns with NaN values
            R_column = np.expand_dims(Rin[:, i],axis=1)
            valid_indices = np.all(~np.isnan(R_column), axis=1)
                  
            if permute_beta and idx_data is not None:
                # Calculate the predicted values using permuted beta
                R_pred =calculate_ols_predictions(R_column, Din, idx_data, beta, perm, permute_beta, nan_values,  valid_indices)
 
            elif idx_data is not None: # Do not permute beta but calculate each session individually
                # Calculate the predicted values without permuting beta, since permute_beta =False
                R_pred =calculate_ols_predictions(R_column, Din, idx_data, beta, perm, permute_beta, nan_values,  valid_indices)
                
            else:
                # Calculate beta coefficients using regularized pseudo-inverse of D_data
                beta = reg_pinv[:,valid_indices] @ R_column[valid_indices]  # Calculate regression_coefficients (beta)
                # Calculate the predicted values
                R_pred = Din[valid_indices] @ beta
            # Calculate the total sum of squares (tss)
            tss = np.sum((R_column[valid_indices] - np.mean(R_column[valid_indices], axis=0))**2, axis=0)
            # Calculate the residual sum of squares (rss)
            rss = np.sum((R_column[valid_indices]-R_pred)**2, axis=0)
            # Calculate the parametric p-values using F-statistics
            # Calculate the explained sum of squares (ESS)
            ess = tss - rss
            # Calculate the degrees of freedom for the model and residuals
            df1 = Din.shape[1]  # Number of predictors including intercept
            df_resid = Din.shape[0] - df1
            # Calculate the mean squared error (MSE) for the model and residuals
            MSE_model = ess / df1
            MSE_resid = rss / df_resid
            # Calculate the F-statistic
            base_statistics = (MSE_model / MSE_resid)# Calculate R^2
            # Store the R2 in an array
            f_statistic[i] = base_statistics
            p_value[i] = 1 - f.cdf(f_statistic, df1, df_residual)
    else:
        # Expand the dimension of Rin, if it is just a single array and center Rin
        Rin = preprocess_response(Rin)
        if permute_beta:    
            if beta is None:
                # permute beta and calulate predicted values
                beta = calculate_ols_beta(reg_pinv, Rin, idx_data)[0]
            R_pred =calculate_ols_predictions(Rin, Din, idx_data, beta, perm, permute_beta)
        else:
            # Calculate f-statistics

            # Fit the original model 
            beta = reg_pinv @ Rin  # Calculate regression_coefficients (beta)
            # Calculate the predicted values
            R_pred = Din @ beta
        # Calculate the residuals
        residuals = Rin - R_pred
        
        # Calculate sum of squares for the model (SS Model) and residuals (SS Residual)
        ss_total = np.sum((Rin - np.mean(Rin, axis=0))**2)
        ss_residual = np.sum(residuals**2)
        ss_model = ss_total - ss_residual
        
        # Degrees of freedom
        n = Rin.shape[0]  # Number of observations
        p = Rin.shape[1]  # Number of predictors
        df1 = p  # Degrees of freedom for the model (excluding intercept)
        df_residual = n - p  # Degrees of freedom for the residuals
        
        # Mean squares
        ms_model = ss_model / df1
        ms_residual = ss_residual / df_residual
        
        # F-statistic
        f_statistic = ms_model / ms_residual
        p_value = 1 - f.cdf(f_statistic, df1, df_residual)
    return f_statistic, p_value

def calculate_nan_regression_f_test(Din, Rin, reg_pinv, idx_data, permute_beta, perm=0, nan_values=False, beta= None):
    """
    Calculate the f-test values for the regression of each dependent variable 
    in Rin on the independent variables in Din, while handling NaN values column-wise.

    Parameters:
    --------------
    Din (numpy.ndarray): 
        Input data matrix for the independent variables.
    Rin (numpy.ndarray): 
        Input data matrix for the dependent variables.
    reg_pinv (numpy.ndarray): 
        The regularized pseudo-inverse of D_data.
    idx_data (numpy.ndarray): 
        Marks the indices for each trial within the session.
        It is a 2D array where each row represents the start and end index for a session.       
    permute_beta (bool, optional): 
        A flag indicating whether to permute beta coefficients.
    perm (int): 
        The permutation index.
    nan_values (bool, optional), default=False:: 
        A flag indicating whether there are NaN values.
    beta (numpy.ndarray):
    
    Returns:
    ----------  
        R2_test (numpy.ndarray): Array of f-test values for each regression.
    """
    if nan_values:
        # Calculate F-statistics if there are Nan_values
        Rin = np.expand_dims(Rin, axis=1) if Rin.ndim==1 else Rin
        q = Rin.shape[-1]
        f_statistic = np.zeros(q)
        p_value = np.zeros(q)
        # Calculate t-statistic for each pair of columns (D_column, R_data)
        for i in range(q):
            # Indentify columns with NaN values
            R_column = np.expand_dims(Rin[:, i],axis=1)
            valid_indices = np.all(~np.isnan(R_column), axis=1)
                  
            if permute_beta and idx_data is not None:
                # Calculate the predicted values using permuted beta
                R_pred =calculate_ols_predictions(R_column, Din, idx_data, beta, perm, permute_beta, nan_values,  valid_indices)
 
            elif idx_data is not None: # Do not permute beta but calculate each session individually
                # Calculate the predicted values without permuting beta, since permute_beta =False
                R_pred =calculate_ols_predictions(R_column, Din, idx_data, beta, perm, permute_beta, nan_values,  valid_indices)
                
            else:
                # Calculate beta coefficients using regularized pseudo-inverse of D_data
                beta = reg_pinv[:,valid_indices] @ R_column[valid_indices]  # Calculate regression_coefficients (beta)
                # Calculate the predicted values
                R_pred = Din[valid_indices] @ beta
            # Calculate the total sum of squares (tss)
            tss = np.sum((R_column[valid_indices] - np.mean(R_column[valid_indices], axis=0))**2, axis=0)
            # Calculate the residual sum of squares (rss)
            rss = np.sum((R_column[valid_indices]-R_pred)**2, axis=0)
            # Calculate the parametric p-values using F-statistics
            # Calculate the explained sum of squares (ESS)
            ess = tss - rss
            # Calculate the degrees of freedom for the model and residuals
            df1 = Din.shape[1]  # Number of predictors including intercept
            df_resid = Din.shape[0] - df1
            # Calculate the mean squared error (MSE) for the model and residuals
            MSE_model = ess / df1
            MSE_resid = rss / df_resid
            # Calculate the F-statistic
            base_statistics = (MSE_model / MSE_resid)# Calculate R^2
            # Store the R2 in an array
            f_statistic[i] = base_statistics
            p_value[i] = 1 - f.cdf(base_statistics, df1, df_resid)
    else:
        # Expand the dimension of Rin, if it is just a single array
        Rin = np.expand_dims(Rin, axis=1) if Rin.ndim==1 else Rin
        if permute_beta:    
            if beta is None:
                # permute beta and calulate predicted values
                beta = calculate_ols_beta(reg_pinv, Rin, idx_data)[0]
            R_pred =calculate_ols_predictions(Rin, Din, idx_data, beta, perm, permute_beta)
        else:
            # Calculate f-statistics
            # Fit the original model 
            beta = reg_pinv @ Rin  # Calculate regression_coefficients (beta)
            # Calculate the predicted values
            R_pred = Din @ beta
        # Calculate the residual sum of squares (rss)
        rss = np.sum((Rin-R_pred)**2, axis=0)
        # Calculate the total sum of squares (tss)
        tss = np.sum((Rin - np.nanmean(Rin, axis=0))**2, axis=0)
        # Calculate the parametric p-values using F-statistics
        # Calculate the explained sum of squares (ESS)
        ess = tss - rss
        # Calculate the degrees of freedom for the model and residuals
        df1 = Din.shape[1]  # Number of predictors including intercept
        df_resid = Din.shape[0] - df1 # Degrees of freedom for the residuals
        # Calculate the mean squared error (MSE) for the model and residuals
        MSE_model = ess / df1
        MSE_resid = rss / df_resid
        # Calculate the F-statistic
        f_statistic = (MSE_model / MSE_resid)
    
        p_value = 1 - f.cdf(f_statistic, df1, df_resid)

    return f_statistic, p_value

def calculate_f_statistics_and_explained_variance_univariate(Din, Rin, idx_data, beta, perm, reg_pinv, permute_beta, test_combination=False, test_indices_list=None):
    
    """
    Computes F-statistics and explained variance (R²) for  univariate tests.

    Parameters:
    --------------
    Din (numpy.ndarray): 
        Input data matrix for the independent variables.
    Rin (numpy.ndarray): 
        Input data matrix for the dependent variables.
    idx_data (numpy.ndarray): 
        An array containing the indices for each session. The array can be either 1D or 2D:
        For a 1D array, a sequence of integers where each integer labels the session number. For example, [1, 1, 1, 1, 2, 2, 2, ..., N, N, N, N, N, N, N, N].
        For a 2D array, each row represents the start and end indices for the trials in a given session, with the format [[start1, end1], [start2, end2], ..., [startN, endN]].  
    beta (numpy.ndarray):
        beta coefficient for each session.
        It has a shape (num_session, p, q), where the first dimension 
        represents the session, the second dimension represents the featires, 
        and the third dimension represent dependent variables. 
    perm (int): 
        The permutation index.    
    reg_pinv (numpy.ndarray): 
        The regularized pseudo-inverse of D_data
    permute_beta (bool, optional): 
        A flag indicating whether to permute beta coefficients.
    test_combination (str), default=False:       
        Specifies the combination method.
        Valid options: "True", "across_columns", "across_rows".
    test_indices_list (numpy.ndarray), default=None:
        Indices for data points that belongs to the test-set for each session.
    
    Returns:
    --------
    base_statistics (numpy.ndarray): 
        The expanded base statistics array.
    pval_matrix (numpy.ndarray): 
        calculated p-values estimated from the F-statistic
    """
    base_statistics = np.zeros((Din.shape[-1],Rin.shape[-1]))
    pval_matrix = np.zeros((Din.shape[1], Rin.shape[1]))
    test_indices = np.concatenate(test_indices_list, axis=0)
    for q_i in range(Rin.shape[-1]):
        # Identify columns with NaN values
        R_column = np.expand_dims(Rin[test_indices, q_i], axis=1)
        valid_indices = np.all(~np.isnan(R_column), axis=1)

        if test_combination !=False:
            for p_j in range(Din.shape[-1]):
                D_column = np.expand_dims(Din[test_indices[0 if len(test_indices) == 1 else q_i], p_j], axis=1)
                reg_pinv_column = np.expand_dims(reg_pinv[p_j, test_indices[0 if len(test_indices) == 1 else q_i]], axis=0)
                beta_column = np.squeeze(calculate_ols_beta(reg_pinv_column, R_column, idx_data)[0]) if beta is None else beta[:,p_j,q_i]
                nan_values = np.any(np.isnan(valid_indices)) or np.any(np.isnan(D_column))
                R_pred =calculate_ols_predictions(R_column, D_column, idx_data, beta_column, perm, permute_beta, nan_values,  valid_indices)
                # Calculate the residual sum of squares (rss)
                rss = np.sum((np.expand_dims(R_column[valid_indices,q_i],axis=1)-R_pred)**2, axis=0)
                # Calculate the total sum of squares (tss)
                tss = np.sum((R_column[valid_indices,q_i] - np.nanmean(R_column[valid_indices,q_i], axis=0))**2, axis=0)
                ess = tss - rss
                # Calculate the degrees of freedom for the model and residuals
                df1 = D_column.shape[1]  # Number of predictors including intercept
                df_resid = D_column.shape[0] - df1
                # Calculate the mean squared error (MSE) for the model and residuals
                MSE_model = ess / df1
                MSE_resid = rss / df_resid
                # Calculate the F-statistic
                f_statistics = MSE_model / MSE_resid
                # Store base statistics
                base_statistics[p_j, q_i] = f_statistics 
                # Calculate the p-value for the F-statistic
                pval = 1 - f.cdf(f_statistics, df1, df_resid)
                # Store the p-value
                pval_matrix[p_j, q_i] = pval 

        else:
            # Explained variance
            for p_j in range(Din.shape[-1]):
                D_column = np.expand_dims(Din[test_indices, p_j], axis=1)
                reg_pinv_column = np.expand_dims(reg_pinv[p_j, test_indices], axis=0)
                beta_column = np.squeeze(calculate_ols_beta(reg_pinv_column, R_column, idx_data)[0]) if beta is None else beta[:,p_j,q_i]
                nan_values = np.any(np.isnan(valid_indices)) or np.any(np.isnan(D_column))
                R_pred =calculate_ols_predictions(R_column, D_column, idx_data, beta_column, perm, permute_beta, nan_values,  valid_indices)
                # Calculate the residual sum of squares (rss)
                rss = np.sum((R_column - R_pred)**2, axis=0)
                # Calculate the total sum of squares (tss)
                tss = np.sum((R_column - np.mean(R_column, axis=0))**2, axis=0)
                base_statistics[p_j, q_i] = 1 - (rss / tss) #r_squared 

    return base_statistics, pval_matrix


def calculate_beta_session(reg_pinv, Rin, idx_data, permute_beta, category_lim, test_indices_list, train_indices_list):
    """
    Calculate beta coefficients for each session. 
    If there are NaN values the procedure will be done per column.

    Parameters:
    --------------
    reg_pinv (numpy.ndarray): 
        The regularized pseudo-inverse of D_data.
    Rin (numpy.ndarray): 
        Input data matrix for the dependent variables.
    idx_data (numpy.ndarray): 
        Marks the indices for each trial within the session.
        It is a 2D array where each row represents the start and end index for a session.    
    permute_beta (bool, optional), default=False: 
        A flag indicating whether to permute beta coefficients.
    category_lim : int or None, optional, default=10
        Maximum allowed number of categories for F-test. Acts as a safety measure for columns 
        with integer values, like age, which may be mistakenly identified as multiple categories.  
    """

    # detect nan values
    nan_values = np.sum(np.isnan(Rin))>0

    # Do it columnwise if NaN values are detected
    if nan_values:
        Rin = np.expand_dims(Rin, axis=1) if Rin.ndim==1 else Rin
        q = Rin.shape[-1]
        beta = np.zeros((len(idx_data),len(reg_pinv),Rin.shape[1] ))
        # Calculate beta coefficients for each session
        for col in range(q):
            # Indentify columns with NaN values
            R_column = np.expand_dims(Rin[:, col],axis=1)
            valid_indices = np.all(~np.isnan(R_column), axis=1)
                    
            if permute_beta and idx_data is not None:
                # Calculate the predicted values using permuted beta
                beta_col, test_indices_list, train_indices_list = calculate_ols_beta(reg_pinv, R_column, idx_data,  category_lim, test_indices_list, train_indices_list)
                beta[:,:,col] = np.squeeze(beta_col)

            else:
                # Calculate beta coefficients using regularized pseudo-inverse of D_data
                beta[:,:,col] = reg_pinv[:,valid_indices] @ R_column[valid_indices]  # Calculate regression_coefficients (beta)
    else:
        # permute beta and calulate predicted values
        #beta, test_indices_list, train_indices_list = calculate_ols_beta(reg_pinv, Rin, idx_data, category_lim, test_indices_list, train_indices_list)
        beta = []
        for indices in train_indices_list:
            session_beta = reg_pinv[:,indices] @ Rin[indices, :]
            beta.append(session_beta)
        beta =np.array(beta)    
    return beta, test_indices_list, train_indices_list
        
def calculate_ols_beta(reg_pinv, Rin, idx_data,  category_lim= 10, test_indices_list=[], train_indices_list=[]):
    """
    Calculate beta for ordinary least squares regression.

    Parameters:
    -----------
    reg_pinv (numpy.ndarray): 
        The regularized pseudo-inverse of D_data
    Rin (numpy.ndarray):
        Response matrix.
    idx_data (numpy.ndarray):
        Indices representing the start and end of trials.
    nan_values (numpy.ndarray):
        Whether to handle NaN values. Default is False.

    Returns:
    --------
    beta (numpy.ndarray):
        Beta coefficients
    test_indices_list (list)
    """
    seed =0
    np.random.seed(seed)  # Set seed for reproducibility
    # detect nan values
    nan_values = np.sum(np.isnan(Rin))>0
    beta = []
    if nan_values:
        # Handle NaN values by identifying columns with NaN
        Rin = np.expand_dims(Rin, axis=1) if Rin.ndim==1 else Rin
        indices = np.all(~np.isnan(Rin), axis=1)
        indices_range = np.arange(len(indices))
        nan_indices = indices_range[~indices]
        
        bool_data = ~np.isin(indices_range, nan_indices)
        # make a train test split, which we are going to estimate the beta's from for each session.
        if train_indices_list ==[]:
            for start, end in idx_data:
                idx_range = np.arange(start, end)
        
                # Find matches
                matches = np.isin(nan_indices, idx_range)
                matched_values = nan_indices[matches]
                # Calculate the range length considering matched_values
                range_length = end - start - len(matched_values) if len(matched_values) >0 else end - start
                
                unique_values = np.unique(Rin[idx_range[bool_data[idx_range]],:])
                if len(unique_values)<category_lim:
                    # Create the train test split
                    train_indices, test_indices = train_test_split(np.arange(range_length), test_size=0.5, stratify=Rin[idx_range[bool_data[idx_range]],:], random_state=seed)
                else:
                    # Perform random split for continuous values
                    train_indices, test_indices = train_test_split(np.arange(end-start), test_size=0.5, random_state=seed)
                    
                train_indices.sort()
                test_indices.sort()
                # adjust the indices so they account for the NaN values
                for value in matched_values:
                    index_increase_train =train_indices>=value
                    train_indices =train_indices[index_increase_train]+1
                    index_increase_test =test_indices>=value
                    test_indices =test_indices[index_increase_test]+1
                    
                train_indices+=start
                test_indices+=start
                test_indices_list.append(test_indices)
                train_indices_list.append(train_indices)

                session_beta = reg_pinv[:,train_indices] @ Rin[train_indices, :]
                beta.append(session_beta) 
        else:
            for indices in train_indices_list:
                session_beta = reg_pinv[:,indices] @ Rin[indices, :]
                beta.append(session_beta)  
                  
    elif Rin.ndim==2: 
        if train_indices_list ==[]:
            for start, end in idx_data:
                unique_values = np.unique(Rin[start:end,:])
                if len(unique_values)<category_lim:
                    train_indices, test_indices = train_test_split(np.arange(end-start), test_size=0.5, stratify=Rin[start:end,:], random_state=seed)
                else:
                    # Perform random split for continuous values
                    train_indices, test_indices = train_test_split(np.arange(end-start), test_size=0.5, random_state=seed)
                
                train_indices.sort()
                test_indices.sort()
                train_indices+=start
                test_indices+=start
                
                session_beta = reg_pinv[:,train_indices] @ Rin[train_indices, :]
                beta.append(session_beta)
                test_indices_list.append(test_indices)
                train_indices_list.append(train_indices)
        else:
            for indices in train_indices_list:
                session_beta = reg_pinv[:,indices] @ Rin[indices, :]
                beta.append(session_beta)
                

    else:
        # Column wise calculation
        if train_indices_list ==[]:
            for start, end in idx_data:
                if len(unique_values)<category_lim:
                    train_indices, test_indices = train_test_split(np.arange(end-start), test_size=0.5, stratify=Rin[start:end], random_state=seed)
                else:
                    # Perform random split for continuous values
                    train_indices, test_indices = train_test_split(np.arange(end-start), test_size=0.5, random_state=seed)
                train_indices.sort()
                test_indices.sort()
                train_indices+=start
                test_indices+=start
                test_indices_list.append(test_indices)
                train_indices_list.append(train_indices)

                session_beta = reg_pinv[:,train_indices] @ Rin[train_indices]
                beta.append(session_beta)
        else:
            for indices in train_indices_list:
                session_beta = reg_pinv[:,indices] @ Rin[indices, :]
                beta.append(session_beta)
                
    return np.array(beta), test_indices_list, train_indices_list


def train_test_indices(R_data, idx_data,  category_lim= 10):
    """
    Calculate beta for ordinary least squares regression.

    Parameters:
    -----------
    reg_pinv (numpy.ndarray): 
        The regularized pseudo-inverse of D_data
    R_data (numpy.ndarray):
        Response matrix.
    idx_data (numpy.ndarray):
        Indices representing the start and end of trials.
    nan_values (numpy.ndarray):
        Whether to handle NaN values. Default is False.

    Returns:
    --------
    beta (numpy.ndarray):
        Beta coefficients
    test_indices_list (list)
    """
    # Initialize list to store lengths of non-NaN values at each timepoint
    R_len = []

    # Loop through each timepoint and count non-NaN values
    for t in range(R_data.shape[0]):
        non_nan_count = np.sum(~np.isnan(R_data[t, :]),axis=0)
        R_len.append(non_nan_count)

    # Find the timepoint with the longest length
    max_length = np.argmax(R_len) 
    #Rin = R_data[max_length,~np.isnan(R_data[max_length, :])] # Now only look at values that are not NaN for the longest list of values
    Rin = R_data[max_length,:] # Now only look at values that are not NaN for the longest list of values
    test_indices_list=[]
    train_indices_list=[]
    seed =0
    np.random.seed(seed)  # Set seed for reproducibility
    # detect nan values
    nan_values = np.sum(np.isnan(Rin))>0

    if nan_values:
        # Handle NaN values by identifying columns with NaN
        Rin = np.expand_dims(Rin, axis=1) if Rin.ndim==1 else Rin
        indices = np.all(~np.isnan(Rin), axis=1)
        indices_range = np.arange(len(indices))
        nan_indices = indices_range[~indices]
        
        bool_data = ~np.isin(indices_range, nan_indices)

        idx_data_update = update_indices(~indices, idx_data)
        # make a train test split, which we are going to estimate the beta's from for each session.
        if train_indices_list ==[]:
            for start, end in idx_data_update:
                idx_range = np.arange(start, end)
        
                # Find matches
                matches = np.isin(nan_indices, idx_range)
                matched_values = nan_indices[matches]
                # Calculate the range length considering matched_values
                range_length = end - start - len(matched_values) if len(matched_values) >0 else end - start
                
                unique_values = np.unique(Rin[idx_range[bool_data[idx_range]],:])
                if len(unique_values)<category_lim:
                    # Create the train test split
                    train_indices, test_indices = train_test_split(np.arange(range_length), test_size=0.5, stratify=Rin[idx_range[bool_data[idx_range]],:], random_state=seed)
                else:
                    # Perform random split for continuous values
                    train_indices, test_indices = train_test_split(np.arange(end-start), test_size=0.5, random_state=seed)
                    
                train_indices.sort()
                test_indices.sort()
                # adjust the indices so they account for the NaN values
                for value in matched_values:
                    index_increase_train =train_indices>=value
                    train_indices =train_indices[index_increase_train]+1
                    index_increase_test =test_indices>=value
                    test_indices =test_indices[index_increase_test]+1
                    
                train_indices+=start
                test_indices+=start
                test_indices_list.append(test_indices)
                train_indices_list.append(train_indices)
                  
    elif Rin.ndim==2: 
        if train_indices_list ==[]:
            for start, end in idx_data:
                unique_values = np.unique(Rin[start:end,:])
                if len(unique_values)<category_lim:
                    train_indices, test_indices = train_test_split(np.arange(end-start), test_size=0.5, stratify=Rin[start:end,:], random_state=seed)
                else:
                    # Perform random split for continuous values
                    train_indices, test_indices = train_test_split(np.arange(end-start), test_size=0.5, random_state=seed)
                
                train_indices.sort()
                test_indices.sort()
                train_indices+=start
                test_indices+=start
                test_indices_list.append(test_indices)
                train_indices_list.append(train_indices)
        indices = np.all(~np.isnan(Rin), axis=1)

    else:
        # Column wise calculation
        if train_indices_list ==[]:
            for start, end in idx_data:
                if len(unique_values)<category_lim:
                    train_indices, test_indices = train_test_split(np.arange(end-start), test_size=0.5, stratify=Rin[start:end], random_state=seed)
                else:
                    # Perform random split for continuous values
                    train_indices, test_indices = train_test_split(np.arange(end-start), test_size=0.5, random_state=seed)
                train_indices.sort()
                test_indices.sort()
                train_indices+=start
                test_indices+=start
                test_indices_list.append(test_indices)
                train_indices_list.append(train_indices)
        indices = np.all(~np.isnan(Rin), axis=1)
    #idx_data_update =update_indices(~indices, idx_data) if nan_values else idx_data.copy()

    return train_indices_list, test_indices_list, ~indices

def train_test_update_indices(train_indices_list, test_indices_list, nan_indices):
    """
    Update train and test indices after removing specified NaN indices and re-indexing the remaining values.

    Parameters:
    --------------
    train_indices_list (list of list of int): 
        A list where each element is a list of sorted train indices for different segments.
    test_indices_list (list of list of int): 
        A list where each element is a list of sorted test indices for different segments.
    nan_indices (numpy.ndarray): 
        A list of indices to be removed from both train and test lists.
        
    Returns:
    ----------  
    train_indices_list_update (list of list of int): 
        The updated train indices with specified NaN indices removed and remaining indices re-indexed.
    test_indices_list_update (list of list of int): 
        The updated test indices with specified NaN indices removed and remaining indices re-indexed.
    """
    # Combine all indices from train and test, and sort them
    all_indices = sorted(set([idx for sublist in train_indices_list + test_indices_list for idx in sublist]))
    
    # Remove specified indices
    updated_all_indices = [idx for idx in all_indices if idx not in nan_indices]
    
    # Create a mapping from old indices to new indices
    index_map = {old_idx: new_idx for new_idx, old_idx in enumerate(updated_all_indices)}
    
    # Update each sublist in train_indices and test_indices
    train_indices_list_update = [
        [index_map[idx] for idx in sublist if idx not in nan_indices]
        for sublist in train_indices_list
    ]
    
    test_indices_list_update = [
        [index_map[idx] for idx in sublist if idx not in nan_indices]
        for sublist in test_indices_list
    ]
    return train_indices_list_update, test_indices_list_update

def calculate_ols_predictions(Rin, Din, idx_data, beta, perm, permute_beta=False, nan_values=False,  valid_indices=None, regression_statistics=False):
    """
    Calculate predictions for ordinary least squares regression.

    Parameters:
    -----------
    reg_pinv (numpy.ndarray): 
        The regularized pseudo-inverse of D_data.
    D_data (numpy.ndarray): 
        The input data array.
    R_data (numpy.ndarray): 
        The dependent variable.
        Design matrix.
    idx_data (numpy.ndarray): 
        Marks the indices for each trial within the session.
        It is a 2D array where each row represents the start and end index for a session.
    perm (int): 
        Value marking the number of permutations that have been performed. 
    permute_beta (bool, optional): 
        Whether to permute beta. Default is False.
    nan_values (bool, optional): 
        Whether to handle NaN values. Default is False.
    valid_indices (numpy.ndarray, optional): 
        Valid indices. Default is None.
    regression_statistics (bool, optional): 
        Flag indicating whether to compute regression statistics (R-squared, F-statistics, and t-statistics). Default is False.

    Returns:
    --------
    R_pred (numpy.ndarray): 
        Predicted values from the OLS regression when `regression_statistics` is False.
        
    R2_stats (numpy.ndarray), F_stats (numpy.ndarray), t_stats (numpy.ndarray): 
        If `regression_statistics` is True, returns R-squared, F-statistics, and t-statistics for each session.
 
    """
    if nan_values:
        R_pred = []
        valid_indices_range = np.arange(len(valid_indices))
        invalid_indices = valid_indices_range[~valid_indices]

        # permute beta
        beta_perm = np.random.permutation(np.array(beta)) if permute_beta and perm != 0 else beta
        
        for idx, (start, end) in enumerate(idx_data):
            idx_range = np.arange(start, end)
            bool_data = ~np.isin(idx_range, invalid_indices)
            R_pred.append(np.dot(Din[idx_range[bool_data], :], beta_perm[idx]))
        R_pred =np.concatenate(R_pred, axis=0)
        if regression_statistics == False:
            return R_pred
        else:
            R2_stats, F_stats, t_stats = regresstion_stats(Din, Rin,R_pred, beta_perm, idx_data)
            return R2_stats, F_stats, t_stats
    
    elif Rin.ndim==2: 
        R_pred = np.zeros((len(Din), Rin.shape[-1]))
        # Permute beta if perm is not equal to 0
        beta_perm = np.random.permutation(beta) if permute_beta and perm != 0 else beta
        beta_perm = np.expand_dims(beta_perm, axis=1) if beta_perm.ndim ==1 else beta_perm
        for idx, (start, end) in enumerate(idx_data):
            # Make prediction with beta
            if beta_perm[idx, :].ndim ==1:
                # Reshape beta_perm[idx, :] to a 2D array with a single row or column based on Din[start:end, :].shape
                beta_reshaped = beta_perm[idx, :].reshape(-1, 1) if Din[start:end, :].shape[-1] != 1 else beta_perm[idx, :].reshape(1, -1)
                # Perform the matrix multiplication
                R_pred[start:end, :] = Din[start:end, :] @ beta_reshaped
            else:
                R_pred[start:end,:] = Din[start:end, :] @ beta_perm[idx, :]
        if regression_statistics == False:
            return R_pred
        else:
            R2_stats, F_stats, t_stats = regresstion_stats(Din, Rin, R_pred, beta_perm, idx_data)
            return R2_stats, F_stats, t_stats
    else:
        # Column wise calculation
        R_pred = []
        # Permute beta
        beta_perm = np.random.permutation(np.array(beta)) if permute_beta and perm != 0 else np.array(beta)
        for idx, (start, end) in enumerate(idx_data):
            idx_range = np.arange(start, end)
            R_pred.append(np.dot(Din[idx_range, :], beta_perm[idx]))
        R_pred= np.concatenate(R_pred, axis=0)
        if regression_statistics == False:
            return R_pred
        else:
            R2_stats, F_stats, t_stats = regresstion_stats(Din, Rin,R_pred, beta_perm, idx_data)
            return R2_stats, F_stats, t_stats


def calculate_nan_correlation_matrix(D_data, R_data, pval_parametric=False):
    """
    Calculate the correlation matrix between independent variables (D_data) and dependent variables (R_data),
    while handling NaN values column by column of dimension p without  without removing entire rows.
    
    Parameters:
    --------------
    D_data (numpy.ndarray): 
        Input D-matrix for the independent variables.
    R_data (numpy.ndarray): 
        Input R-matrix for the dependent variables.
    pval_parametric (bool). Default is False: 
        Flag to mark if parametric p-values should calculated alongside the correlation cofficients or not.

    Returns:
    ----------  
    correlation_matrix (numpy.ndarray): 
        correlation matrix between columns in D_data and R_data.
    """
    # Initialize a matrix to store correlation coefficients
    p, q = D_data.shape[1], (R_data.shape[1] if R_data.ndim > 1 else 1)
    correlation_matrix = np.full((p, q), np.nan)
    pval_matrix = np.full((p, q), np.nan)
    # Calculate correlation coefficient for each pair of columns (D_column, R_column)
    for p_i in range(p):
        D_column = D_data[:, p_i]
        for q_j in range(q):
            # Do it column by column if R_data got more than 1 column
            R_column = R_data[:, q_j] if R_data.ndim>1 else R_data
            # If there are no variability between variables then set the value to NaN
            if np.all(D_column == D_column[0]) or np.all(R_column == R_column[0]):

                pval_matrix[p_i, q_j]  = np.nan 

                correlation_matrix[p_i, q_j] = np.nan  
            else:
                # Find non-NaN indices for both D_column and R_column
                valid_indices = ~np.isnan(D_column) & ~np.isnan(R_column)           
                if pval_parametric:
                    #pval_matrix = np.zeros(corr_matrix.shape)
                    corr_coef, pval= pearsonr(D_column[valid_indices], R_column[valid_indices])
                    correlation_matrix[p_i, q_j] = corr_coef 
                    pval_matrix[p_i, q_j]  = pval
                else:
                    # Calculate correlation coefficient matrix
                    corr_coef = np.corrcoef(D_column[valid_indices], R_column[valid_indices], rowvar=False)
                    # get the correlation matrix
                    correlation_matrix[p_i, q_j] = corr_coef[0, 1] 
        
        
    return correlation_matrix, pval_matrix

def geometric_pvalue(p_values, test_combination):
    """
    Calculate the geometric combination of p-values.
    
    Parameters:
    --------------
    p_values (numpy.ndarray): 
        A 2D array representing the parametric p-values between variables.
        
    test_combination (bool or str): 
        Specifies the method for combining the p-values:
        - True: Compute the geometric mean of all p-values (1-by-1).
        - "across_columns": Compute the geometric mean for each column, returning an array of shape (1-by-q).
        - "across_rows": Compute the geometric mean for each row, returning an array of shape (1-by-p).
        
    Returns:
    ----------
    corr_combination (numpy.ndarray): 
        The combined p-values based on the specified test_combination method.
    """
    # Calculate the geometric mean
    if test_combination== True:
        corr_combination=np.nanmean(p_values)
    elif test_combination== "across_columns":
        corr_combination=np.nanmean(p_values, axis=0)
    elif test_combination== "across_rows":
        corr_combination = np.nanmean(p_values, axis=1)
    return corr_combination

def calculate_anova_f_test(D_data, R_column, nan_values=False):
    """
    Calculate F-statistics for each feature of D_data against categories in R_data, while handling NaN values column by column without removing entire rows.
        - The function handles NaN values for each feature in D_data without removing entire rows.
        - NaN values are omitted on a feature-wise basis, and the F-statistic is calculated for each feature.
        - The resulting array contains F-statistics corresponding to each feature in D_data.

    Parameters:
    --------------
    D_data (numpy.ndarray): 
        The input matrix of shape (n_samples, n_features).
    R_column (numpy.ndarray): 
        The categorical labels corresponding to each sample in D_data.

    Returns:
    ----------  
    f_test (numpy.ndarray): 
        F-statistics for each feature in D_data against the categories in R_data.
 
    """
    if nan_values:
        p = D_data.shape[1]
        f_test = np.zeros(p)
        pval_array = np.zeros(p)
        
        for i in range(p):
            D_column = np.expand_dims(D_data[:, i],axis=1)
            # Find rows where both D_column and R_data are non-NaN
            valid_indices = np.all(~np.isnan(D_column) & ~np.isnan(R_column), axis=1)
            categories =np.unique(R_column)
            # Omit NaN rows in single columns - nan_policy='omit'    
            f_stats, pval = f_oneway(*[D_column[R_column*valid_indices == category] for category in categories])
            # Store the t-statistic in the matrix
            f_test[i] = f_stats
            pval_array[i] = pval
    else:
        # Calculate f-statistics if there are no NaN values
        f_test, pval_array = f_oneway(*[D_data[R_column == category] for category in np.unique(R_column)])   
        
    return f_test, pval_array

def calculate_nan_t_test(Din, R_column, nan_values=False):
    """
    Calculate the t-statistics between paired independent (D_data) and dependent (R_data) variables, while handling NaN values column by column without removing entire rows.
        - The function handles NaN values for each feature in D_data without removing entire rows.
        - NaN values are omitted on a feature-wise basis, and the t-statistic is calculated for each feature.
        - The resulting array contains t-statistics corresponding to each feature in D_data.

    Parameters:
    --------------
    Din (numpy.ndarray): 
        The input matrix of shape (n_samples, n_features).
    R_column (numpy.ndarray): 
        The binary labels corresponding to each sample in D_data.

    Returns:
    ----------  
    t_test (numpy.ndarray):
        t-statistics for each feature in D_data against the binary categories in R_data.
 
    """
    if nan_values:
        # Initialize a matrix to store t-statistics
        p = Din.shape[1]
        t_test = np.zeros(p)
        pval_array = np.zeros(p)
        # Extract non-NaN values for each group
        groups = np.unique(R_column)
        # Calculate t-statistic for each pair of columns (D_column, R_data)
        for i in range(p):
            D_column = np.expand_dims(Din[:, i],axis=1)
                
            # Find rows where both D_column and R_data are non-NaN
            # valid_indices = np.all(~np.isnan(D_column) & ~np.isnan(R_data), axis=1)
            # Omit NaN rows in single columns - nan_policy='omit'    
            t_stat, pval = ttest_ind(D_column[R_column == groups[0]], D_column[R_column == groups[1]], nan_policy='omit')

            # Store the t-statistic in the matrix
            t_test[i] = t_stat
            pval_array[i] = pval  
    else:
        # Get the t-statistic if there are no NaN values
        t_test_group = np.unique(R_column)
        # Get the t-statistic
        t_test, pval_array = ttest_ind(Din[R_column == t_test_group[0]], Din[R_column == t_test_group[1]]) 
    return t_test, pval_array


def calculate_reg_f_test(Din, Rin, idx_data, beta, perm, reg_pinv, permute_beta, test_indices=None):
    """
    Calculate F-statistics for each feature of Din against categories in R_data, while handling NaN values column by column without removing entire rows.
        - The function handles NaN values for each feature in Din without removing entire rows.
        - NaN values are omitted on a feature-wise basis, and the F-statistic is calculated for each feature.
        - The resulting array contains F-statistics corresponding to each feature in Din.

    Parameters:
    --------------
    Din (numpy.ndarray): 
        The input matrix of shape (n_samples, n_features).
    R_column (numpy.ndarray): 
        The categorical labels corresponding to each sample in Din.

    Returns:
    ----------  
    f_statistic (numpy.ndarray): 
        F-statistics for each feature in Din against the categories in R_data.
 
    """
    p_dim = Din.shape[1]
    q_dim =Rin.ndim if Rin.ndim==1 else Rin.shape[-1]
    f_statistics = np.zeros(p_dim)
    pval_array = np.zeros(p_dim)
    # base_statistics = np.zeros((Din.shape[-1],Rin.shape[-1]))
    # pval_matrix = np.zeros((p_dim, 1))
    if test_indices is not None:
        for q_i in range(q_dim):
            # Identify columns with NaN values
            #R_column = np.expand_dims(Rin[test_indices[0] if len(test_indices) == 1 else test_indices[q_i], q_i], axis=1)
            R_column =np.expand_dims(Rin[test_indices[0]], axis=1) if Rin.ndim==1 else np.expand_dims(Rin[test_indices[q_i], q_i], axis=1)
            #R_column = np.expand_dims(Rin[test_indices[0] if len(test_indices) == 1 else test_indices[q_i], q_i], axis=1)
            valid_indices = np.all(~np.isnan(R_column), axis=1)

            for p_j in range(p_dim):
                #D_column =np.expand_dims(Din[test_indices[0]], axis=1) if len(test_indices)==1 else np.expand_dims(Din[test_indices[0], q_i], axis=1)
                #reg_pinv_column =np.expand_dims(reg_pinv[test_indices[0]], axis=1) if Rin.ndim==1 else np.expand_dims(reg_pinv[test_indices[0], q_i], axis=1)
                D_column = np.expand_dims(Din[test_indices[0 if len(test_indices) == 1 else q_i], p_j], axis=1)
                reg_pinv_column = np.expand_dims(reg_pinv[p_j, test_indices[0 if len(test_indices) == 1 else q_i]], axis=0)
                beta_column = np.squeeze(calculate_ols_beta(reg_pinv_column, R_column, idx_data)[0]) if beta is None else beta[:,p_j,q_i]
                nan_values = np.any(np.isnan(valid_indices)) or np.any(np.isnan(D_column))
                R_pred =calculate_ols_predictions(R_column, D_column, idx_data, beta_column, perm, permute_beta, nan_values,  valid_indices)
                # Calculate the residual sum of squares (rss)
                rss = np.sum((np.expand_dims(R_column[valid_indices,q_i],axis=1)-R_pred)**2, axis=0)
                # Calculate the total sum of squares (tss)
                tss = np.sum((R_column[valid_indices,q_i] - np.nanmean(R_column[valid_indices,q_i], axis=0))**2, axis=0)
                ess = tss - rss
                # Calculate the degrees of freedom for the model and residuals
                df1 = D_column.shape[1]  # Number of predictors including intercept
                df_resid = D_column.shape[0] - df1
                # Calculate the mean squared error (MSE) for the model and residuals
                MSE_model = ess / df1
                MSE_resid = rss / df_resid
                # Calculate the F-statistic
                f_statistic = MSE_model / MSE_resid
                # Calculate the p-value for the F-statistic
                pval = 1 - f.cdf(f_statistic, df1, df_resid)
                # Store the p-value
                f_statistics[p_j] =f_statistic
                pval_array[p_j] = pval 
    else:
        for q_i in range(q_dim):
            # Identify columns with NaN values
            R_column = np.expand_dims(Rin, axis=1) if Rin.ndim==1 else Rin
            valid_indices = np.all(~np.isnan(R_column), axis=1)

            for p_j in range(p_dim):
                D_column =  np.expand_dims(Din[:, p_j], axis=1)
                reg_pinv_column = np.expand_dims(reg_pinv[p_j,:], axis=1) #np.expand_dims(reg_pinv, axis=1) if reg_pinv.ndim==1 else reg_pinv
                
                # reg_pinv[:,train_indices] @ Rin[train_indices, :]
                # np.dot(D_column, beta_perm))
                # Calculate beta coefficients using regularized pseudo-inverse of D_data
                beta = reg_pinv_column[valid_indices].T @ R_column[valid_indices] if reg_pinv_column.shape[-1]==1 else  reg_pinv_column[valid_indices] @ R_column[valid_indices]  # Calculate regression_coefficients (beta)
                # Predicted R
                R_pred = D_column @ beta
                # Calculate the residual sum of squares (rss)
                rss = np.sum((np.expand_dims(R_column[valid_indices,q_i],axis=1)-R_pred)**2, axis=0)
                # Calculate the total sum of squares (tss)
                tss = np.sum((R_column[valid_indices,q_i] - np.nanmean(R_column[valid_indices,q_i], axis=0))**2, axis=0)
                ess = tss - rss
                # Calculate the degrees of freedom for the model and residuals
                df1 = D_column.shape[1]  # Number of predictors including intercept
                df_resid = D_column.shape[0] - df1
                # Calculate the mean squared error (MSE) for the model and residuals
                MSE_model = ess / df1
                MSE_resid = rss / df_resid
                # Calculate the F-statistic
                f_statistic = MSE_model / MSE_resid
                # Calculate the p-value for the F-statistic
                pval = 1 - f.cdf(f_statistic, df1, df_resid)
                # Store the p-value
                pval_array[p_j,] = pval       
                f_statistics[p_j] =f_statistic  
        
    return f_statistics, pval_array

def detect_significant_intervals(pval, alpha):
    """
    Detect intervals of consecutive True values in a boolean array.

    Parameters:
    ------------
    p_values (numpy.ndarray): 
        An array of p-values. 
    alpha (float, optional): 
        Threshold for significance.

    Returns:
    ----------  
    intervals (list of tuple): 
        A list of tuples representing the start and end indices
        (inclusive) of each interval of consecutive True values.

    Example:
    ----------  
        array = [False, False, False, True, True, True, False, False, True, True, False]
        detect_intervals(array)
        output: [(3, 5), (8, 9)]
    """
    # Boolean array of p-values
    array = pval<alpha
    intervals = []  # List to store intervals
    start_index = None  # Variable to track the start index of each interval

    # Iterate through the array
    for i, value in enumerate(array):
        if value:
            # If True, check if it's the start of a new interval
            if start_index is None:
                start_index = i
        else:
            # If False, check if the end of an interval is reached
            if start_index is not None:
                intervals.append((start_index, i - 1))  # Store the interval
                start_index = None  # Reset start index for the next interval

    # Handle the case where the last interval extends to the end of the array
    if start_index is not None:
        intervals.append((start_index, len(array) - 1))

    return intervals

def vpath_check_2D(vpath):
    """
    Validate whether a 2D matrix of the Viterbi path is one-hot encoded or 
    if a 1D array contains integers.

    Parameters:
    ------------
    vpath (numpy.ndarray): 
        A numpy array that can be either 2D or 1D.

    Returns:
    ----------
    bool: 
        Returns True if the following conditions are met:
        - For a 2D array: The array is one-hot encoded, meaning each row contains exactly one '1' 
          (or 1.0) and all other elements are '0' (or 0.0).
        - For a 1D array: The array contains only integer values.
        Returns False if any of these conditions are not satisfied.

    Example:
    ----------
        # Example 1: 2D one-hot encoded array
        matrix = np.array([[0, 1, 0], [1, 0, 0], [0, 0, 1]])
        vpath_check_2D(matrix)
        output: True

        # Example 2: 1D integer array
        array = np.array([1, 2, 1, 0])
        vpath_check_2D(array)
        output: True
    """
    
    if vpath.ndim==2:
        # Check that each element is either 0 or 1 (or 0.0 or 1.0)
        if not np.all(np.isin(vpath, [0, 1])):
            return False
        
        # Check that each row has exactly one 1
        row_sums = np.sum(vpath, axis=1)
        if not np.all(row_sums == 1):
            return False
    else:
        # now vpath is a 1D array
        if np.issubdtype(vpath.dtype, np.integer) == False:
            return False

    return True   
    
# Helper function to conditionally squeeze arrays
def squeeze_first_dim(array):
    """
    Conditionally squeeze a 3D numpy array if its first dimension has size 1.

    Parameters:
    ------------
    array (numpy.ndarray or None): 
        A numpy array that may be 3-dimensional. Can also be None.

    Returns:
    ----------
    numpy.ndarray or None: 
        - If the input array is 3D and its first dimension has size 1, 
          the array is squeezed along the first dimension and the result is returned.
        - If the input array is not 3D, or its first dimension is not of size 1, 
          the array is returned as is.
        - If the input is None, None is returned.
    """
    if array is not None and array.ndim == 3:
        return np.squeeze(array)
    return array


def update_indices(nan_mask, idx_data):
    """
    Updates the index array to account for removed NaN values.

    Parameters:
    nan_mask (np.ndarray): 
        A boolean array where True indicates NaN positions.
    idx_data (np.ndarray): 
        A 2D array of shape (n, 2) where each row contains [start, end] indices.

    Returns:
    idx_data_update (np.ndarray): 
        A 2D array of updated indices after removing NaN values.
    """
    # Get valid indices after removing NaNs
    valid_indices = np.where(~nan_mask)[0]

    # Initialize updated idx_data
    idx_data_update = np.zeros_like(idx_data)

    # Update idx_data based on valid indices
    for i, (start, end) in enumerate(idx_data):
        valid_start = np.searchsorted(valid_indices, start)
        valid_end = np.searchsorted(valid_indices, end - 1, side='right')
        idx_data_update[i, 0] = valid_start
        idx_data_update[i, 1] = valid_end

    return idx_data_update


def create_test_summary(Rin, base_statistics,pval, predictor_names, outcome_names, method, F_stats_list, t_stats_list,n_T, n_N, n_p, n_q, test_indices_list=None):
    """
    Create a summary report for the test.

    Parameters:
    --------------
    Rin (numpy.ndarray): 
        Input data matrix for the dependent variables (shape: n_samples x n_outcomes).
    base_statistics (numpy.ndarray): 
        Array of R² or correlation coefficients, depending on the method used.
    pval (numpy.ndarray): 
        Array of p-values corresponding to the base statistics.
    predictor_names (list of str): 
        List of names for the predictors.
    outcome_names (list of str): 
        List of names for the outcomes.
    method (str): 
        Specifies the method used for testing. Options are:
        - "multivariate": For regression analysis with multiple predictors and outcomes.
        - Other: For other tests
    F_stats_list (numpy.ndarray): 
        Array of F-statistics across permutations (shape: n_T x Nperm x n_q for time-dependent data, or Nperm x n_q for time-independent data).
    t_stats_list (numpy.ndarray): 
        Array of t-statistics across permutations (shape: n_T x Nperm x n_p x n_q for time-dependent data, or Nperm x n_p x n_q for time-independent data).
    n_T (int): 
        Number of timepoints (set to 1 for time-independent data).
    n_N (int): 
        Number of observations.
    n_p (int): 
        Number of predictors.
    n_q (int): 
        Number of outcomes.
    Returns:
    ----------
    test_summary (dict): 
        A dictionary containing the summary report of the test
    """

    if method=="multivariate":
        df1 = n_p
        if np.any(np.isnan(Rin)):
            if Rin.shape[0]==n_T:
                df2 = []  # To store df2 for each regression
                for q_i in range(Rin.shape[-1]):
                    R_column = np.expand_dims(Rin[0,:, q_i], axis=1) if test_indices_list is None else np.expand_dims(Rin[0,np.concatenate(test_indices_list,axis=0), q_i], axis=1) 
                    n_valid  = np.sum(np.all(~np.isnan(R_column), axis=1))
                    df2_column = n_valid - n_p  # Compute df2 for the current regression
                    df2.append(df2_column)  # Store df2
                df2 =np.array(df2)
            else:
                df2 = []  # To store df2 for each regression
                for q_i in range(Rin.shape[-1]):
                    R_column = np.expand_dims(Rin[:, q_i], axis=1) if test_indices_list is None else np.expand_dims(Rin[np.concatenate(test_indices_list,axis=0), q_i], axis=1)
                    n_valid  = np.sum(np.all(~np.isnan(R_column), axis=1))
                    df2_column = n_valid - n_p  # Compute df2 for the current regression
                    df2.append(df2_column)  # Store df2
                df2 =np.array(df2)
        else:
            df2 = n_N - n_p
        if n_p==1 or n_q==1:
            perm_p_values_F = np.zeros((n_T,n_q))
            perm_p_values_t = np.zeros((n_T,n_p,n_q))
            perm_ci_lower = np.zeros((n_T,n_p,n_q))
            perm_ci_upper = np.zeros((n_T,n_p,n_q))
            t_stats = np.zeros((n_T,n_p,n_q))
            F_stats =[]
            t_stats =[]
            for t in range(n_T):
                perm_p_values_F[t,:] = np.mean(np.abs(F_stats_list[t,1:]) >= np.abs(F_stats_list[t,0]), axis=0)
                perm_p_values_t[t,:] = np.mean(np.abs(t_stats_list[t,1:]) >= np.abs(t_stats_list[t,0]), axis=0)
                perm_ci_lower[t,:] = np.percentile(t_stats_list[t,1:], 2.5, axis=0)
                perm_ci_upper[t,:] = np.percentile(t_stats_list[t,1:], 97.5, axis=0)
                F_stats.append(F_stats_list[t,0])
                t_stats.append(t_stats_list[t,0])
            F_stats = np.squeeze(np.array(F_stats))
            t_stats = np.array(t_stats)
        else: 
            perm_p_values_F = (np.mean(np.abs(F_stats_list[0,1:]) >= np.abs(F_stats_list[0,0]), axis=0))
            perm_p_values_t = (np.mean(np.abs(t_stats_list[0,1:]) >= np.abs(t_stats_list[0,0]), axis=0))
            perm_ci_lower = (np.percentile(t_stats_list[0,1:], 2.5, axis=0))
            perm_ci_upper = (np.percentile(t_stats_list[0,1:], 97.5, axis=0))
            F_stats = F_stats_list[0,0]
            t_stats = t_stats_list[0,0]

        # Create Model Summary DataFrame
        test_summary = {
            "Predictor": np.repeat(predictor_names, n_q),
            "Outcome": outcome_names,
            "R²": base_statistics,
            "p-value (R²)": pval,
            "df1": df1,
            "df2": df2,
            "F-stat": F_stats,
            "T-stat": t_stats,
            "p-value (F-stat)": perm_p_values_F,
            "p-value (t-stat)": perm_p_values_t,
            "LLCI": perm_ci_lower,
            "ULCI": perm_ci_upper
        }

    else:
        # Other tests
            test_summary = {
            "Predictor": np.repeat(predictor_names, n_q),
            "Outcome": np.tile(outcome_names, n_p),
            "Base statistics": base_statistics,
            "P-value": pval,
            "Timepoints": n_T
        }

    return test_summary

def display_test_summary(result_dict, output="both", timepoint=0, return_tables=False):
    """
    Display or export test summary from result_dict.

    Parameters:
    --------------
    result_dict (dict): 
        A dictionary including:
        - 'base_statistics': Array of base statistics (e.g., correlation coefficients).
        - 'pval': Array of p-values from permutation testing.
        - 'test_summary': A dictionary containing the summary report of the test
        
    output (str, optional): 
        Specifies the output to display. Options are:
        - "both": Display both Model Summary and Coefficients Table (default).
        - "model": Display only the Model Summary.
        - "coef": Display only the Coefficients Table.
        
    timepoint (int, optional): 
        Specifies the timepoint index if T-statistics are time-dependent.
        
    return_tables (bool, optional):
        If True, returns the Model Summary and/or Coefficients Table as pandas DataFrames.
        If False, simply displays the tables (default).

    Returns:
    ----------
    None if `return_tables` is False.
    If `return_tables` is True:
        - Returns a tuple (model_summary, coef_table) if output="both".
        - Returns model_summary if output="model".
        - Returns coef_table if output="coef".
    """

    if result_dict["method"] == "multivariate":
        t_stats = result_dict["test_summary"]["T-stat"]
        n_predictors = t_stats.shape[-2]
        model_summary = coef_table = None
        
        # Check if T-statistics are 2D or 3D (time-dependent)
        if t_stats.ndim == 2 or t_stats.ndim == 3 and t_stats.shape[0] == 1:
            # Time-independent case
            if output in ["both", "model"]:
                model_summary = pd.DataFrame({
                    "Outcome": result_dict["test_summary"]["Outcome"],
                    "R²": result_dict["test_summary"]["R²"].round(4),
                    "F-stat": result_dict["test_summary"]["F-stat"].round(4),
                    "df1": result_dict["test_summary"]["df1"],
                    "df2": result_dict["test_summary"]["df2"],
                    "p-value (R²)": result_dict["test_summary"]["p-value (R²)"].round(4),
                })
                if not return_tables:
                    print("\nModel Summary:")
                    print(model_summary.to_string(index=False))
            
            if output in ["both", "coef"]:
                coef_table = pd.DataFrame({
                    "Predictor": result_dict["test_summary"]["Predictor"],
                    "Outcome": np.tile(result_dict["test_summary"]["Outcome"], n_predictors),
                    "T-stat": t_stats.flatten(),
                    "p-value": result_dict["test_summary"]["p-value (t-stat)"].flatten(),
                    "LLCI": result_dict["test_summary"]["LLCI"].flatten(),
                    "ULCI": result_dict["test_summary"]["ULCI"].flatten()
                })
                if not return_tables:
                    print("\nCoefficients Table:")
                    print(coef_table.to_string(index=False))
        
        else:
            # Time-dependent case
            if output in ["both", "model"]:
                F_stat = result_dict["test_summary"]["F-stat"].round(4)
                base_stat = result_dict["test_summary"]["R²"].round(4)
                pval_stat =result_dict["test_summary"]["p-value (R²)"].round(4)
                if timepoint >= base_stat.shape[0]:
                    raise ValueError(f"Selected time point {timepoint} is out of range. "
                        f"Maximum available time point index is {base_stat.shape[0] - 1}.")
                model_summary = pd.DataFrame({
                    "Outcome": result_dict["test_summary"]["Outcome"],
                    "R²": base_stat[timepoint] if base_stat.ndim==1 else base_stat[timepoint,:],
                    "F-stat": F_stat[timepoint] if F_stat.ndim==1 else F_stat[timepoint,:],
                    "df1": result_dict["test_summary"]["df1"],
                    "df2": result_dict["test_summary"]["df2"],
                    "p-value (R²)": pval_stat[timepoint] if pval_stat.ndim==1 else pval_stat[timepoint,:],
                })
                if not return_tables:
                    print(f"\nModel Summary (timepoint {timepoint}):")
                    print(model_summary.to_string(index=False))
            
            if output in ["both", "coef"]:
                coef_table = pd.DataFrame({
                    "Predictor": result_dict["test_summary"]["Predictor"],
                    "Outcome": np.tile(result_dict["test_summary"]["Outcome"], n_predictors),
                    "T-stat": result_dict["test_summary"]["T-stat"][timepoint, :].flatten(),
                    "p-value": result_dict["test_summary"]["p-value (t-stat)"][timepoint, :].flatten(),
                    "LLCI": result_dict["test_summary"]["LLCI"][timepoint, :].flatten(),
                    "ULCI": result_dict["test_summary"]["ULCI"][timepoint, :].flatten()
                })
                if not return_tables:
                    print(f"\nCoefficients Table (timepoint {timepoint}):")
                    print(coef_table.to_string(index=False))

        # Return tables if requested
        if return_tables:
            if output == "both":
                return model_summary, coef_table
            elif output == "model":
                return model_summary
            elif output == "coef":
                return coef_table
                
    elif result_dict["method"] == "osr":
        if result_dict["test_summary"]['Timepoints'] == 1:
            # Extract necessary data from result_dict
            base_statistics = result_dict['test_statistics'][0,:]
            pval = result_dict['pval']
            predictors = result_dict['test_summary']['Predictor']
            outcomes = result_dict['test_summary']['Outcome']
                
            # Generate Model Summary
            max_stat = np.max(np.abs(base_statistics), axis=0)
            min_pval = np.min(pval, axis=0)
            n_predictors =len(np.unique(result_dict["test_summary"]["Predictor"]))

            # unit extraction
            if 'all_columns' in result_dict["statistical_measures"].values():
                key = list(result_dict["statistical_measures"].keys())[0]
                # Get the unit for each column
                unit_key = key.split('_cols')[0]
                
            # Check if all outcomes have the same prefix and end with a number
            prefix = outcomes[0].split(' ')[0]
            if all(re.match(rf"^{prefix} \d+$", outcome) for outcome in outcomes):
                # Sorting using the numerical part of each string
                outcomes = sorted(np.unique(outcomes), key=lambda x: int(x.split(' ')[1]))

                model_summary = pd.DataFrame({
                    "Unit": [f"{unit_key}-diff"],  
                    "Nperm": [result_dict["Nperm"]],  
                    "Max Statistic": [max_stat], 
                    "Min P-value": [min_pval],  

                })
            if not return_tables:
                print(f"\nModel Summary (OSR-{result_dict['test_summary']['state_com']}):")
                print(model_summary.to_string(index=False))

            if output in ["both", "coef"]:
                coef_table = pd.DataFrame({
                    "State": predictors,
                    f"{unit_key} difference": base_statistics,
                    "P-value": pval
                })
                if not return_tables:
                    print(f"\nCoefficients Table (OSR-{result_dict['test_summary']['state_com']}):")
                    print(coef_table.to_string(index=False))
    elif result_dict["method"] == "osa":
        if result_dict["test_summary"]['Timepoints'] == 1:
            # Extract necessary data from result_dict
            base_statistics = result_dict['test_statistics'][0,:]
            pval = result_dict['pval']
            predictors = result_dict['test_summary']['Predictor']
                
            # unit extraction
            if 'all_columns' in result_dict["statistical_measures"].values():
                key = list(result_dict["statistical_measures"].keys())[0]
                # Get the unit for each column
                unit_key = key.split('_cols')[0]
                
            model_summary = pd.DataFrame({
                "Unit": [f"{unit_key}-diff"],  
                "Nperm": [result_dict["Nperm"]],  
            })
            if not return_tables:
                print(f"\nModel Summary (OSA)):")
                print(model_summary.to_string(index=False))

            if output in ["both", "coef"]:
                result_dict['test_summary']['pairwise_comparisons']
                coef_table = pd.DataFrame({
                    "State X": [x for x, y in result_dict['test_summary']['pairwise_comparisons']],
                    "State Y": [y for x, y in result_dict['test_summary']['pairwise_comparisons']],
                    f"{unit_key} difference": base_statistics,
                    "P-value": [pval[x-1, y-1] for x, y in result_dict['test_summary']['pairwise_comparisons']]
                })
                if not return_tables:
                    print(f"\nCoefficients Table (OSA):")
                    print(coef_table.to_string(index=False))

        else:
            # Time-dependent case
            # Extract necessary data from result_dict
            base_statistics = result_dict['base_statistics'][timepoint,:]
            pval = result_dict['pval'][timepoint,:]
            predictors = result_dict['test_summary']['Predictor']
            outcomes = result_dict['test_summary']['Outcome']
                
            # Generate Model Summary
            max_stat = np.max(np.abs(base_statistics), axis=0)
            min_pval = np.min(pval, axis=0)
            n_predictors =len(np.unique(result_dict["test_summary"]["Predictor"]))

            # unit extraction
            if 'all_columns' in result_dict["statistical_measures"].values():
                key = list(result_dict["statistical_measures"].keys())[0]
                # Get the unit for each column
                unit_key = key.split('_cols')[0]

            model_summary = pd.DataFrame({
                "Outcome": np.unique(outcomes),
                "Max Statistic": max_stat,
                "Min P-value": min_pval,
                "Unit": unit_key,
                "Nperm": result_dict["Nperm"]
            })
            if not return_tables:
                print("\nModel Summary:")
                print(model_summary.to_string(index=False))

            if output in ["both", "coef"]:
                coef_table = pd.DataFrame({
                    "Predictor": result_dict["test_summary"]["Predictor"],
                    "Outcome": result_dict["test_summary"]["Outcome"],
                    "Base Statistic": base_statistics.flatten().round(5),
                    "P-value": pval.flatten().round(5)
                })
                if not return_tables:
                    print("\nCoefficients Table:")
                    print(coef_table.to_string(index=False))

                  # Return tables if requested
        if return_tables:
            if output == "both":
                return model_summary, coef_table
            elif output == "model":
                return model_summary
            elif output == "coef":
                return coef_table   
    else:
        if result_dict["test_summary"]['Timepoints'] == 1:
            # Extract necessary data from result_dict
            base_statistics = result_dict['base_statistics']
            pval = result_dict['pval']
            predictors = result_dict['test_summary']['Predictor']
            outcomes = result_dict['test_summary']['Outcome']
                
            # Generate Model Summary
            max_stat = np.max(np.abs(base_statistics), axis=0)
            min_pval = np.min(pval, axis=0)
            n_predictors =len(np.unique(result_dict["test_summary"]["Predictor"]))

            # unit extraction
            if 'all_columns' in result_dict["statistical_measures"].values():
                key = list(result_dict["statistical_measures"].keys())[0]
                # Get the unit for each column
                unit_key = key.split('_cols')[0]
                
            # Check if all outcomes have the same prefix and end with a number
            prefix = outcomes[0].split(' ')[0]
            if all(re.match(rf"^{prefix} \d+$", outcome) for outcome in outcomes):
                # Sorting using the numerical part of each string
                outcomes = sorted(np.unique(outcomes), key=lambda x: int(x.split(' ')[1]))

            model_summary = pd.DataFrame({
                "Outcome": outcomes,
                "Max Statistic": max_stat,
                "Min P-value": min_pval,
                "Unit": unit_key,
                "Nperm": result_dict["Nperm"]
            })
            if not return_tables:
                print("\nModel Summary:")
                print(model_summary.to_string(index=False))

            if output in ["both", "coef"]:
                coef_table = pd.DataFrame({
                    "Predictor": predictors,
                    "Outcome": result_dict["test_summary"]["Outcome"],
                    "Base Statistic": base_statistics.flatten(),
                    "P-value": pval.flatten()
                })
                if not return_tables:
                    print("\nCoefficients Table:")
                    print(coef_table.to_string(index=False))
        else:
            # Time-dependent case
            # Extract necessary data from result_dict
            base_statistics = result_dict['base_statistics'][timepoint,:]
            pval = result_dict['pval'][timepoint,:]
            predictors = result_dict['test_summary']['Predictor']
            outcomes = result_dict['test_summary']['Outcome']
                
            # Generate Model Summary
            max_stat = np.max(np.abs(base_statistics), axis=0)
            min_pval = np.min(pval, axis=0)
            n_predictors =len(np.unique(result_dict["test_summary"]["Predictor"]))

            # unit extraction
            if 'all_columns' in result_dict["statistical_measures"].values():
                key = list(result_dict["statistical_measures"].keys())[0]
                # Get the unit for each column
                unit_key = key.split('_cols')[0]

            model_summary = pd.DataFrame({
                "Outcome": np.unique(outcomes),
                "Max Statistic": max_stat,
                "Min P-value": min_pval,
                "Unit": unit_key,
                "Nperm": result_dict["Nperm"]
            })
            if not return_tables:
                print("\nModel Summary:")
                print(model_summary.to_string(index=False))

            if output in ["both", "coef"]:
                coef_table = pd.DataFrame({
                    "Predictor": result_dict["test_summary"]["Predictor"],
                    "Outcome": result_dict["test_summary"]["Outcome"],
                    "Base Statistic": base_statistics.flatten().round(5),
                    "P-value": pval.flatten().round(5)
                })
                if not return_tables:
                    print("\nCoefficients Table:")
                    print(coef_table.to_string(index=False))

                  # Return tables if requested
        if return_tables:
            if output == "both":
                return model_summary, coef_table
            elif output == "model":
                return model_summary
            elif output == "coef":
                return coef_table          
            
def update_permutation_matrix(permutation_matrix, nan_mask):
    """
    Updates a permutation matrix by removing NaN indices and adjusting remaining indices.

    Parameters:
    --------------
    permutation_matrix (numpy.ndarray): 
        A 2D array where each column represents a permutation.
    nan_mask (numpy.ndarray): 
        A boolean array indicating positions of NaN values in the original dataset.
    
    Returns:
    ----------
    updated_permutation_matrix (numpy.ndarray): 
        A 2D array with NaN indices removed and the remaining indices adjusted accordingly.
    """
    # Get the indices corresponding to NaN values
    indices = np.arange(len(permutation_matrix))
    nan_indices = indices[nan_mask]
    
    # Create a list of valid indices (excluding NaN indices)
    valid_indices = np.setdiff1d(indices, nan_indices)
    
    # Create an array to map old indices to new indices
    mapping_array = np.full(len(permutation_matrix), -1)  # Initialize with -1 for NaNs
    mapping_array[valid_indices] = np.arange(len(valid_indices))  # Map valid indices to new range
    
    # Apply the mapping to update the permutation matrix
    permutation_matrix_update = mapping_array[permutation_matrix]
    
    # Remove the -1 values column-wise
    permutation_matrix_update = np.array([
        col[col != -1] for col in permutation_matrix_update.T  # Transpose, filter, and transpose back
    ]).T
    
    return permutation_matrix_update

def __palm_quickperms(EB, M=None, nP=1000, CMC=False, EE=True):
    # Call palm_quickperms from palm_functions
    return palm_quickperms(EB, M, nP, CMC, EE)
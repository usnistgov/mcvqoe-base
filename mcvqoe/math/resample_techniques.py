# -*- coding: utf-8 -*-
"""
Created on Tue Jan 12 08:43:22 2021

@author: jkp4
"""
import numpy as np


def bootstrap_ci(x, p=0.95, R=1e4, stat=np.mean, method="percentile"):
    """
    Bootstrap confidence interval for array of data.

    Parameters
    ----------
    x : np.ndarray
        Data for which to calculate a confidence interval for stat.
    p : float, optional
        Confidence level of output interval. The default is 0.95.
    R : int, optional
        Number of resamples to calculate. The default is 1e4.
    stat : function, optional
        Statistic for confidence interval. The default is np.mean.
    method : str, optional
        Defines the method used for bootstrapping. May be either
        "percentile" or "t". "percentile" performs a "quick-and-dirty"
        confidence interval, where "t" performs a bootstrap-t confidence
        interval.

    Returns
    -------
    ci : np.ndarray
         Confidence interval of data for stat

    resamples : list
         Values of stat for each resample

    Notes
    -----
    .. [1] Tim C. Hesterberg (2015) What Teachers Should Know About the
    Bootstrap: Resampling in the Undergraduate Statistics Curriculum, The
    American Statistician, 69:4, 371-386, DOI: 10.1080/00031305.2015.1089789

    """
    
    # Force R to be an int
    if type(R) is not int:
        R = int(R)
    # Length of data
    N = len(x)
    # Note observed statistic
    obs = stat(x)
    # Array to store resample stat values in
    resamples = []
    # Random generator
    gen = np.random.default_rng()

    if method == "percentile" or method == "p":
        # Generate resampled data, RxN matrix
        resamp = gen.choice(x, size=(R, N))
        # Calculate stat for each resample
        resamples = stat(resamp, axis=1)

        # Lower bound of confidence interval
        q_l = (1 - p) / 2
        # Upper bound of confidence interval
        q_u = 1 - q_l
        # Confidence interval
        ci = np.quantile(resamples, [q_l, q_u])

    # Standard error known only for sample mean, at the moment
    elif (method == "t") and (stat == np.mean):
        # Generate resampled data, RxN matrix
        resamp = gen.choice(x, size=(R, N))
        # Calculate stat for each resample
        rs_stat = stat(resamp, axis=1)
        # Calculate standard error for each resample
        rs_se = np.std(resamp, axis=1)/np.sqrt(N)
        # Estimate t-statistic for each resample
        rs_ts = (rs_stat - obs)/rs_se

        # Get t-score quantiles for esimating confidence interval
        q_l = (1 - p) / 2
        # Upper bound of confidence interval
        q_u = 1 - q_l
        bounds = np.quantile(rs_ts, [q_l, q_u])

        # Calculate CI from observed mean, observed standard error, and
        # t-scores from estimated t-distribution
        se = np.std(x)/np.sqrt(N)
        # Note that the bounds flip, see Ref [1] equation (4)
        ci = obs - bounds[::-1]*se

    elif (method == "t") and (stat != np.mean):
        raise ValueError("Standard error for this statistic is not implemented.")

    return (ci, resamples)


def approx_permutation_test(
        x, y, accept_threshold=0.05, R=1e4,
        stat=np.mean, tail="two"):
    """
    Perform an approximate permutation test to test if two sets of data are
    from equivalent distributions.

    Null hypothesis in this test says that x is from the same distribution as
    y

    Parameters
    ----------
    x : NumPy Array
        Array of data from first condition

    y : NumPy Array
        Array of data from second condition

    accept_threshold : float
        Value that p-value is compared to either reject or accept the Null
        hypothesis. Default is 0.05.

    R : int
        Number of repetitions of resamples to perform. Default is 1e4

    stat : function
        Statistic to perform on data. Defaults to np.mean

    tail : str
        Determine if you do a one-sided or two-sided approximate permutation
        test. Acceptable values are "left", "right", or "two". If tail is
        "left", the test considers what fraction of resampled differences are
        less than the observed statistic. If tail is "right", the test
        considers what fraction of resampled differences are greater than the
        observed statistic. If tail is "two", the test considers what fraction
        of the absolute value of resampled differences are greater than the
        absolute value of the observed statistic.


    Return
    ------
    Boolean
        Rejection or not of the null hypothesis, in this case that data comes
        from same distribution. Explicitly if x and y are from distinct
        distributions this function will return True as the Null hypothesis
        assumes that they are from equivalent distributions. Alternatively if
        x and y are from the same distribution this function will return False.

    Examples
    --------
    Compare two extremely distinct data sets, returns True as the null
    hypothesis is rejected.

    >>> x = np.ones(120)
    >>> y = np.zeros(30)
    >>> mcvqoe.math.approx_permutation_test(x, y)
    True

    Compare two similar data sets, returns False as the null hypothesis is not
    rejected.

    >>> rng = np.random.default_rng()
    >>> x = rng.normal(0, 1, 100)
    >>> y = rng.normal(0.1, 1, 100)
    >>> mcvqoe.math.approx_permutation_test(x, y)
    False
    """

    # Force R to be an int
    if type(R) is not int:
        R = int(R)

    # Observed statistic
    observed = stat(x) - stat(y)

    # Number of trials in population 1
    m1 = len(x)
    # Number of trials in population 2
    m2 = len(y)

    # Total number of trials between populations
    n = m1 + m2
    # Combine both populations
    combo = np.concatenate((x, y))

    # Initialize difference array
    diffs = np.zeros((R, 1))

    # Random generator
    gen = np.random.default_rng()

    for k in range(R):
        # Create random permutation for resampling
        permIx = gen.permutation(n)

        # Grab first m elements of random order for population 1
        x_resamp = combo[permIx[0:m1]]
        # Grab remaining K elements of random order for population 2
        y_resamp = combo[permIx[m1:]]

        # Compute resample statistic (difference of means)
        diffs[k] = stat(x_resamp) - stat(y_resamp)

    # Calculate p-value for likelihood that observed came from mixed
    # distribution
    if tail == "left":
        # Consider how many resamples were lower than observed value (how far left is our observation?)
        pval_sum = diffs <= observed

    elif tail == "right":
        # Consider how many resamples were greater than observed value (how far right is our observation)
        pval_sum = diffs >= observed
    elif tail == "two":
        # Consider how many resamples were larger in magnitude than observed value (how far from either tale is our observation)
        pval_sum = abs(diffs) >= abs(observed)
    else:
        raise ValueError(
            "Unrecognized tail argument: {}. Must be either left, right, or two.".format(
                tail
            )
        )

    # Get fraction of resamples that achieved tail condtions
    pval = (np.count_nonzero(pval_sum)) / R

    if pval <= accept_threshold:
        # If pval is less than accept_threshold, reject Null hypothesis
        reject = True
    else:
        # If pval is greater than accept_threshold, do not reject Null hypothesis
        reject = False
    return reject


def standard_error(x):
    """
    Calculate standard error for data in x.

    This method assumes normality conditions are reasonable.

    Parameters
    ----------
    x : np.ndarray
        Data.

    Returns
    -------
    se : float
        Standard error of x

    """
    
    se = np.std(x) / np.sqrt(len(x))
    return se


def compare_uncs(x):
    """
    Calculate standard error and bootstrap based confidence intervals

    A nice sanity check that in well behaved circumstances, standard error is
    equivalent to bootstrap confidence interval results. Computes 95%
    confidence interval.

    Parameters
    ----------
    x : TYPE
        DESCRIPTION.

    Returns
    -------
    None.

    """
    
    x_mean = np.mean(x)

    gum_u = standard_error(x)

    x_unc = 1.96 * gum_u

    print(
        "GUM Uncertainty (95% C.I.): x = {:.4f}, ({:.4f},{:.4f})".format(
            x_mean, x_mean - x_unc, x_mean + x_unc
        )
    )

    b_u, _ = bootstrap_ci(x)
    print(
        "Bootstrap Uncertainty (95% C.I.): x = {:.4f}, ({:.4f},{:.4f})".format(
            x_mean, b_u[0], b_u[1]
        )
    )


def improved_autocorrelation(x, lag_max=None):
    """
    Detect lags at which there is likely autocorrelation.

    Determined according to the improved bounds given in 'Zhang NF (2006)
    Calculation of the uncertainty of the mean of autocorrelated measurements'.

    Parameters
    ----------
    x : numpy array
        Numerical data on which to detect autocorrelation.

    Returns
    -------
    numpy array
        Array of indices for lags where this is likely autocorrelation.

    """
    
    # Force x to behave be a numpy array
    x = np.array(x)
    # Calculate sample autocorrelation estimate
    N = len(x)
    if lag_max is None:
        # TODO: Experiment more with the best lag_max to use
        # # Zhang NF (2006) recommends using a maximum lag of N/4
        lag_max = int(np.floor(N/4))
        
        # However that feels it can give some fairly noisey results, we instead use
        # the maximum lag used by R acf method
        # lag_max = int(np.floor(10*np.log10(N)))
    
    # Initialize correlation estimates
    corrs = np.zeros(lag_max)
    # Get mean of data
    m = np.mean(x)
    denom = np.sum(np.power(x-m, 2))
    for k in range(lag_max):
        numerator = np.sum((x[:(N-k)] - m) * (x[k:] - m))
        corrs[k] = numerator/denom
    
    # Respective uncertainties
    sigmas = np.zeros(lag_max)
    sigmas[0] = 1/np.sqrt(N)
    for k in range(1, lag_max):
        summer = np.sum(np.power(corrs[1:k], 2))
        nummer = 1 + 2* summer
        sigmas[k] = np.sqrt(nummer/N)
    

    return np.argwhere(np.abs(corrs) > 1.96 * sigmas)


def bootstrap_datasets_ci(*datasets, R=int(1e4), alpha=0.5):
    """
    Bootstrap for averaging means from different datasets.

    Parameters
    ----------
    *datasets : numpy arrays
        Datasets from which to take sample means. In context, the datasets
        are the different M2E sessions within a test.
    R : int, optional
        Number of resamples. The default is int(1e4).
    alpha : float, optional
        Alpha level of the test. The default is 0.5.

    Returns
    -------
    ci : numpy array
        Two element array containing the upper and lower confidence bound on
        the mean.

    """
    
    ds = datasets
    # TODO: No need to limit this to first dataset
    N = len(ds[0])
    x_bars = np.zeros((len(ds), R))
    for ii, dataset in enumerate(ds):
        rs = np.random.choice(dataset, size=(N, R))
        x_bar = np.mean(rs, axis=0)
        x_bars[ii, :] = x_bar
    
    # Means across sessions
    x_bar_dist = np.mean(x_bars, axis=0)
    # percentiles
    ql = alpha/2
    qu = 1 - ql
    ci = np.quantile(x_bar_dist, [ql, qu])
    return ci
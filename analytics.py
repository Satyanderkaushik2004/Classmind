# ClassMind Analytics Engine

"""
This module contains pure functions for computing live snapshots and full reports.
"""

import numpy as np


def compute_live_snapshot(data):
    """
    Compute the live snapshot based on the given data.
    Args:
        data (list): List of metrics to analyze.
    Returns:
        dict: Computed live snapshot.
    """
    # Example calculation for live snapshot
    avg = np.mean(data)
    max_val = np.max(data)
    min_val = np.min(data)
    return {'average': avg, 'max': max_val, 'min': min_val}


def generate_full_report(data):
    """
    Generate a full report based on the given data.
    Args:
        data (list): List of metrics to analyze.
    Returns:
        dict: A comprehensive report.
    """
    avg = np.mean(data)
    variance = np.var(data)
    return {'average': avg, 'variance': variance, 'count': len(data)}

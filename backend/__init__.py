# -*- coding: utf-8 -*-
"""
NEUROLINK Research Backend Package
==================================
Connects actual MI-BCI EEG research models, calibration, and causal TTA protocols
to the NEUROLINK web interface via FastAPI and WebSocket.
"""
# Set before NumPy/SciPy imports; one BLAS thread per inference process.
import os
for _variable in ("OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_variable] = "1"
__version__ = "1.0.0"

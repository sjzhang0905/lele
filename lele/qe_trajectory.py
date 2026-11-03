"""Compatibility entry point for linear QE PWSCF results."""
def read_qe_frames(path,max_frames=None):
    from .qe_results import read_qe_output
    return read_qe_output(path).frames(max_frames)

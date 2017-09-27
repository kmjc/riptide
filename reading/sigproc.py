""" Read dedispersed time series from SIGPROC. """
##### Standard imports #####
import os
import struct

##### Non-standard imports #####
import numpy as np
from astropy.coordinates import SkyCoord
import astropy.units as uu

# SIGPROC keys and associated data types
# Copied from Ewan Barr's sigpyproc
sigproc_keydb = {
    "filename": str,
    "telescope_id": int,
    "telescope": str,
    "machine_id": int,
    "data_type": int,
    "rawdatafile": str,
    "source_name": str,
    "barycentric": int,
    "pulsarcentric": int,
    "az_start": float,
    "za_start": float,
    "src_raj": float,
    "src_dej": float,
    "tstart": float,
    "tsamp": float,
    "nbits": int,
    "nsamples": int,
    "fch1": float,
    "foff": float,
    "fchannel": float,
    "nchans": int,
    "nifs": int,
    "refdm": float,
    "flux": float,
    "period": float,
    "nbeams": int,
    "ibeam": int,
    "hdrlen": int,
    "pb": float,
    "ecc": float,
    "asini": float,
    "orig_hdrlen": int,
    "new_hdrlen": int,
    "sampsize": int,
    "bandwidth": float,
    "fbottom": float,
    "ftop": float,
    "obs_date": str,
    "obs_time": str,
    "signed": bool,
    "accel": float
    }

# These flags mark the boundaries of the header in a SIGPROC data file
sigproc_header_start_flag = 'HEADER_START'
sigproc_header_end_flag = 'HEADER_END'

def read_str(fobj):
    """ Read string from open binary file object. """
    size, = struct.unpack('i', fobj.read(4))
    return fobj.read(size).decode(encoding='utf-8')

def read_attribute(fobj, keydb):
    """ Read SIGPROC {key, value} pair from open binary file object. """
    key = read_str(fobj)
    if key == sigproc_header_end_flag:
        return key, None

    atype = keydb.get(key, None)
    if atype is None:
        errmsg = 'Type of SIGPROC header attribute \'{0:s}\' is unknown, please specify it.'.format(key)
        raise KeyError(errmsg)

    if atype == str:
        val = read_str(fobj)
    elif atype == int:
        val, = struct.unpack('i', fobj.read(4))
    elif atype == float:
        val, = struct.unpack('d', fobj.read(8))
    else:
        errmsg = 'Key \'{0:s}\' has unsupported type \'{1:s}\''.format(key, atype)
        raise ValueError(errmsg)
    return key, val

def read_all_attributes(fobj, keydb):
    """ Read all SIGPROC header attributes from given open file object into a dictionary.

    Parameters:
    -----------
        fobj: file
            Open file object to read.
        keydb: dict
            Dictionary (sigproc_key, type).

    Returns:
    --------
        attrs: dict
            Dictionary of attributes read from the file.
        size: int
            Size of the header in bytes
    """
    attrs = {}
    while True:
        key, val = read_attribute(fobj, keydb)
        if key == sigproc_header_end_flag:
            break
        attrs[key] = val
    return attrs, fobj.tell()

def read_sigproc_header(fobj, extra_keys={}):
    """ Read SIGPROC header from an open file object.

    Parameters:
    -----------
        fobj: file
            Open file object to read.
        extra_keys: dict
            Optional {key: type} dictionary, specifying how to parse any
            non-standard keys that could be found in the header.

    Returns:
    --------
        header: dict
            Dictionary containing the SIGPROC header attributes.
        bytesize: int
            Size of the header in bytes.
    """
    keydb = sigproc_keydb

    # Add any extra keys to header key database
    if extra_keys:
        keydb = sigproc_keydb.copy()
        keydb.update(extra_keys)

    # Read HEADER_START flag
    fobj.seek(0)
    flag = read_str(fobj)
    errmsg = 'File starts with \'{0:s}\' flag instead of the expected \'{1:s}\''.format(flag, sigproc_header_start_flag)
    assert flag == sigproc_header_start_flag, errmsg

    # Read all header attributes
    attrs = {}
    while True:
        key, val = read_attribute(fobj, keydb)
        if key == sigproc_header_end_flag:
            break
        attrs[key] = val

    return attrs, fobj.tell()

def parse_float_coord(f):
    """ Parse coordinate in SIGPROC's own decimal floating point,
    to either hours (RA) or degrees (Dec).
    """
    sign = np.sign(f)
    x = abs(f)
    hh, x = divmod(x, 10000.)
    mm, ss = divmod(x, 100.)
    return sign * (hh + mm / 60.0 + ss / 3600.0)


class SigprocHeader(dict):
    """ """
    def __init__(self, fname, extra_keys={}):
        self._fname = os.path.abspath(fname)
        with open(self.fname, 'rb') as fobj:
            (attrs, self._bytesize) = read_sigproc_header(fobj, extra_keys)
        super(SigprocHeader, self).__init__(attrs)

    @property
    def fname(self):
        """ Absolute path to original file. """
        return self._fname

    @property
    def bytesize(self):
        """ Number of bytes occupied by the header in the original file. """
        return self._bytesize

    @property
    def skycoord(self):
        """ astropy.SkyCoord object with the coordinates of the source. """
        rajd = parse_float_coord(self['src_raj'])
        dejd = parse_float_coord(self['src_dej'])
        return SkyCoord(rajd, dejd, unit=(uu.hour, uu.degree), frame='icrs')
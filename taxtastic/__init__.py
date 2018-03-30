from __future__ import print_function
from os import path

try:
    with open(path.join(path.dirname(__file__), 'data', 'ver')) as f:
        __version__ = f.read().strip().replace('-', '+', 1).replace('-', '.')
        __version__ = __version__.lstrip('v')
except Exception as e:
    __version__ = ''

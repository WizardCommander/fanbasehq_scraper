"""
Compatibility fix for Python 3.12+ collections module
This fixes aiohttp compatibility issues
"""

import collections
import collections.abc

# Fix for Python 3.12+ where MutableSet was moved to collections.abc
if not hasattr(collections, 'MutableSet'):
    collections.MutableSet = collections.abc.MutableSet
if not hasattr(collections, 'Mapping'):
    collections.Mapping = collections.abc.Mapping
if not hasattr(collections, 'MutableMapping'):
    collections.MutableMapping = collections.abc.MutableMapping
if not hasattr(collections, 'Sequence'):
    collections.Sequence = collections.abc.Sequence
if not hasattr(collections, 'Iterable'):
    collections.Iterable = collections.abc.Iterable
if not hasattr(collections, 'Callable'):
    collections.Callable = collections.abc.Callable
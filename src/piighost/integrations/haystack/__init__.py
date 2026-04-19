"""Haystack integration for PIIGhost.

Install with: uv add piighost[haystack]
"""

import importlib.util

if importlib.util.find_spec("haystack") is None:
    raise ImportError(
        "You must install haystack to use the Haystack integration, "
        "please install piighost[haystack]"
    )

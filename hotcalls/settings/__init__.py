"""
Django settings package for HotCalls.
Settings are chosen depending on the Environment.

The module contains multiple configurations, in addition to a base configuration.
"""

import os

try:
    ENVIRONMENT = os.environ["ENVIRONMENT"]
except KeyError as e:
    missing_variable = e.args[0]
    raise RuntimeError(f"Environment variable {missing_variable} is not set")

if ENVIRONMENT == "production":
    from .production import *
elif ENVIRONMENT == "staging":
    from .staging import *
elif ENVIRONMENT == "development":
    from .development import *
elif ENVIRONMENT == "minimal":
    from .minimal import *

import os

# The older test stages were written for the v2 data (3 cities). v3 tests choose v3 explicitly.
os.environ.setdefault("AVATITION_DATA", "v2")

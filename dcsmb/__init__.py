"""DCS mission builder: one mission.yaml -> .miz + HTML briefing + kneeboard pages."""
import contextlib
import io
import logging
import random

# pydcs draws some random values at import time (e.g. add_runway_waypoint's default
# distance); seed first so every build of an unchanged mission is byte-identical.
random.seed("dcsmb")

# pydcs probes for a Windows DCS install on import and prints a warning per
# unit type when it can't find one. That is expected on Linux; silence it.
with contextlib.redirect_stderr(io.StringIO()):
    logging.disable(logging.WARNING)
    import dcs  # noqa: F401
    logging.disable(logging.NOTSET)

"""DCS mission builder: one mission.yaml -> .miz + HTML briefing + kneeboard pages."""
import contextlib
import io
import logging

# pydcs probes for a Windows DCS install on import and prints a warning per
# unit type when it can't find one. That is expected on Linux; silence it.
with contextlib.redirect_stderr(io.StringIO()):
    logging.disable(logging.WARNING)
    import dcs  # noqa: F401
    logging.disable(logging.NOTSET)

import os

# Autograders run under Xvfb with DISPLAY set, so matplotlib would pick the Tk
# backend, whose first-use initialization can exceed `Options.time_limit` and be
# blamed on the student (see issue #205).  This only takes effect if matplotlib
# has not been imported yet, and code that calls `matplotlib.use(...)` opts out.
os.environ.setdefault("MPLBACKEND", "Agg")

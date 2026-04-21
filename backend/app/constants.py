# ---------------------------------------------------------------------------
# Application-wide constants
#
# Magic values that were previously inlined across pipeline.py, files.py, and
# report.py are collected here so they are easy to find and change in one place.
# ---------------------------------------------------------------------------

# MT scoring ----------------------------------------------------------------
MT_ERROR_LIMIT = 3          # consecutive MT failures before scoring is aborted
MT_QUALITY_THRESHOLD = 0.6  # score below this triggers a QA warning

# Preview endpoint ----------------------------------------------------------
PREVIEW_LIMIT_DEFAULT = 20   # default number of segments returned by /preview
PREVIEW_LIMIT_MAX = 100      # hard cap accepted via the ?limit= query param
PREVIEW_EXCERPT_LEN = 100    # max characters kept per segment in HTML report

# Redis progress key --------------------------------------------------------
PROGRESS_KEY_TTL = 3600      # seconds; progress keys expire after 1 hour

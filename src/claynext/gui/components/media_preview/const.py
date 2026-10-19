"""Preview zoom limits."""
from claynext.models.canvas import DEFAULT_CANVAS

FULLSCREEN_BG = DEFAULT_CANVAS["color"]

ZOOM_MIN = 0.20
ZOOM_MAX = 1.80
ZOOM_FIT = 1.0
ZOOM_DEFAULT = 0.75  # Startup view zoom (75% of fit)
ZOOM_WHEEL_FACTOR = 1.10

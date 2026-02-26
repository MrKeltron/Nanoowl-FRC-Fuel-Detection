# ==============================================================================
# distance.py - Distance estimation from pixel width
#
# Uses the pinhole camera model:
#   distance = (real_diameter * focal_length) / pixel_width
#
# HOW TO CALIBRATE focal_length:
#   1. Place the ball exactly 24 inches from the camera
#   2. Run the program and note the width_px value printed in the console
#   3. Set FOCAL_LENGTH_PX = (width_px * 24) in config.py
# ==============================================================================


def estimate_distance(width_px: int, config) -> float:
    """
    Estimates distance to the ball in inches using apparent pixel width.
    Returns 0.0 if width_px is 0 to avoid division by zero.
    """
    if width_px <= 0:
        return 0.0

    distance = (config.BALL_DIAMETER_INCHES * config.FOCAL_LENGTH_PX) / width_px
    return round(distance, 2)

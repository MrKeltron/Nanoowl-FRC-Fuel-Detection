# ==============================================================================
# networktables_publisher.py - Sends vision data to the roboRIO
# Uses pynetworktables (same library works on PC and Jetson)
# ==============================================================================

try:
    from networktables import NetworkTables
    NT_AVAILABLE = True
except ImportError:
    NT_AVAILABLE = False
    print("[NetworkTables] WARNING: pynetworktables not installed.")
    print("[NetworkTables] Run: pip install pynetworktables")
    print("[NetworkTables] NetworkTables publishing will be disabled.")


class NTPublisher:
    def __init__(self, config):
        self.enabled = config.ENABLE_NETWORKTABLES and NT_AVAILABLE
        self.table = None

        if not self.enabled:
            print("[NetworkTables] Publisher disabled.")
            return

        print(f"[NetworkTables] Connecting to robot at {config.ROBOT_IP}...")
        NetworkTables.initialize(server=config.ROBOT_IP)
        self.table = NetworkTables.getTable(config.NT_TABLE_NAME)
        print(f"[NetworkTables] Using table: '{config.NT_TABLE_NAME}'")

    def publish(self, detection: dict, distance: float, frame_width: int, frame_height: int):
        """
        Publishes ball data to NetworkTables.

        Keys published under the Vision table:
            ball_detected   - boolean
            ball_x          - x center in pixels
            ball_y          - y center in pixels
            ball_width_px   - bounding box width in pixels
            ball_distance   - estimated distance in inches
            ball_confidence - detection confidence
            frame_width     - camera frame width
            frame_height    - camera frame height
        """
        if not self.enabled or self.table is None:
            return

        if detection:
            self.table.putBoolean("ball_detected",   True)
            self.table.putNumber("ball_x",           detection["x_center"])
            self.table.putNumber("ball_y",           detection["y_center"])
            self.table.putNumber("ball_width_px",    detection["width_px"])
            self.table.putNumber("ball_distance",    distance)
            self.table.putNumber("ball_confidence",  detection["confidence"])
        else:
            self.table.putBoolean("ball_detected",   False)
            self.table.putNumber("ball_x",           -1)
            self.table.putNumber("ball_y",           -1)
            self.table.putNumber("ball_width_px",    0)
            self.table.putNumber("ball_distance",    -1)
            self.table.putNumber("ball_confidence",  0)

        self.table.putNumber("frame_width",  frame_width)
        self.table.putNumber("frame_height", frame_height)

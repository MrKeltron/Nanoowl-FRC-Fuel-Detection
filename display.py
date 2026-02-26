# ==============================================================================
# display.py - Draws detection results on the frame
# ==============================================================================

import cv2


def draw_detections(frame, detections: list, distances: list, config):
    """
    Draws bounding boxes, crosshairs, and data labels on the frame.
    Only annotates the best (highest confidence) detection prominently.
    All other detections are drawn dimly.
    """
    frame_h, frame_w = frame.shape[:2]

    # Draw center crosshair on frame
    cx, cy = frame_w // 2, frame_h // 2
    cv2.line(frame, (cx - 20, cy), (cx + 20, cy), (200, 200, 200), 1)
    cv2.line(frame, (cx, cy - 20), (cx, cy + 20), (200, 200, 200), 1)

    for i, (det, dist) in enumerate(zip(detections, distances)):
        x1, y1, x2, y2 = det["bbox"]
        bx, by = det["x_center"], det["y_center"]

        # Best detection = bright box, others = dimmer
        color = config.BOX_COLOR if i == 0 else (100, 100, 100)
        thickness = 2 if i == 0 else 1

        # Bounding box
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, thickness)

        # Crosshair on ball center
        cv2.drawMarker(frame, (bx, by), color,
                       markerType=cv2.MARKER_CROSS, markerSize=16, thickness=2)

        # Label (only on best detection to keep it clean)
        if i == 0:
            label_lines = [
                f"X: {bx}px  Y: {by}px",
                f"Width: {det['width_px']}px",
                f"Dist: {dist:.1f} in",
                f"Conf: {det['confidence']:.0%}"
            ]
            label_x = x1
            label_y = y1 - 10
            line_height = 18

            # Draw background box for readability
            max_text_w = max(cv2.getTextSize(l, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0][0]
                             for l in label_lines)
            bg_y1 = label_y - (len(label_lines) * line_height)
            bg_y1 = max(bg_y1, 0)
            cv2.rectangle(frame,
                          (label_x, bg_y1),
                          (label_x + max_text_w + 6, label_y + 4),
                          (0, 0, 0), -1)

            for j, line in enumerate(reversed(label_lines)):
                text_y = label_y - j * line_height
                if text_y > 0:
                    cv2.putText(frame, line,
                                (label_x + 3, text_y),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                                config.BOX_COLOR, 1, cv2.LINE_AA)

    return frame


def draw_fps(frame, fps: float):
    cv2.putText(frame, f"FPS: {fps:.1f}",
                (10, 25), cv2.FONT_HERSHEY_SIMPLEX,
                0.7, (0, 255, 0), 2, cv2.LINE_AA)


def draw_no_detection(frame):
    cv2.putText(frame, "No ball detected",
                (10, 55), cv2.FONT_HERSHEY_SIMPLEX,
                0.6, (0, 0, 255), 2, cv2.LINE_AA)

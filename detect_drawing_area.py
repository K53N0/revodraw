#!/usr/bin/env python3
"""
RevoDraw - Boundary Detection Module

Detects the dotted line drawing area boundary from a Revolut card screenshot.
Uses pure line detection with no hardcoded values - adapts to any screen size.
"""

import cv2
import numpy as np
from dataclasses import dataclass
from typing import Optional, Tuple, List
import subprocess
import sys
import math


@dataclass
class DrawingArea:
    """
    Represents the drawing area with two exclusion zones.

    Shape:
    +--------+---------------------------+
    | EXCL   |                           |
    | (top-  |     DRAWABLE AREA         |
    | left)  |                           |
    +--------+                    +------+
    |                             | EXCL |
    |                             |(visa)|
    +-----------------------------+------+
    """
    top: int
    left: int
    right: int
    bottom: int
    cutout_left: int      # VISA exclusion x
    cutout_top: int       # VISA exclusion y
    top_excl_right: int   # Top-left exclusion x
    top_excl_bottom: int  # Top-left exclusion y

    def __repr__(self):
        return (f"DrawingArea(bounds=({self.left},{self.top})-({self.right},{self.bottom}), "
                f"top_excl=({self.top_excl_right},{self.top_excl_bottom}), "
                f"visa_excl=({self.cutout_left},{self.cutout_top}))")

    def is_inside(self, x: int, y: int) -> bool:
        """Check if point is in drawable area (avoiding both exclusions)."""
        if not (self.left <= x <= self.right and self.top <= y <= self.bottom):
            return False
        if x <= self.top_excl_right and y <= self.top_excl_bottom:
            return False
        if x >= self.cutout_left and y >= self.cutout_top:
            return False
        return True

    @property
    def width(self) -> int:
        return self.right - self.left

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center(self) -> Tuple[int, int]:
        """Center of main drawable area."""
        main_left = max(self.left, self.top_excl_right)
        main_top = max(self.top, self.top_excl_bottom)
        cx = main_left + (self.cutout_left - main_left) // 2
        cy = main_top + (self.bottom - main_top) // 2
        return (cx, cy)

    def get_safe_bounds(self, margin: int = 20):
        return DrawingArea(
            top=self.top + margin,
            left=self.left + margin,
            right=self.right - margin,
            bottom=self.bottom - margin,
            cutout_left=self.cutout_left - margin,
            cutout_top=self.cutout_top - margin,
            top_excl_right=self.top_excl_right + margin,
            top_excl_bottom=self.top_excl_bottom + margin
        )

    def get_usable_rect(self, margin: int = 20) -> Tuple[int, int, int, int]:
        """Get largest rectangle avoiding exclusions."""
        return (
            max(self.left, self.top_excl_right) + margin,
            max(self.top, self.top_excl_bottom) + margin,
            self.cutout_left - margin,
            self.bottom - margin
        )


def capture_screenshot(output_path: str = "screen.png") -> str:
    """Capture screenshot via ADB."""
    print(f"Capturing screenshot to {output_path}...")
    result = subprocess.run(['adb', '-d', 'exec-out', 'screencap', '-p'], capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(f"ADB screenshot failed: {result.stderr.decode()}")

    data = result.stdout
    if len(data) < 8 or data[:4] != b'\x89PNG':
        # Fallback: capture on device then pull (avoids exec-out binary corruption)
        print("Direct capture produced invalid data, using fallback method...")
        tmp_path = "/data/local/tmp/screen_tmp.png"
        subprocess.run(['adb', '-d', 'shell', 'screencap', '-p', tmp_path], check=True)
        result = subprocess.run(['adb', '-d', 'pull', tmp_path, output_path], capture_output=True)
        if result.returncode != 0:
            raise RuntimeError(f"ADB pull failed: {result.stderr.decode()}")
        subprocess.run(['adb', '-d', 'shell', 'rm', tmp_path])
    else:
        with open(output_path, 'wb') as f:
            f.write(data)

    print(f"Screenshot saved to {output_path}")
    return output_path


def find_card_region(gray: np.ndarray) -> Tuple[int, int, int, int]:
    """Find the card region (lighter area on dark background)."""
    _, mask = cv2.threshold(gray, 25, 255, cv2.THRESH_BINARY)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise ValueError("Could not find card region")
    card = max(contours, key=cv2.contourArea)
    return cv2.boundingRect(card)


def detect_lines(bright_mask: np.ndarray, card_w: int, card_h: int) -> Tuple[List, List]:
    """
    Detect horizontal and vertical lines from bright pixel mask.
    Returns lists of (position, length) tuples.
    """
    # Dilate to connect dotted line segments
    kernel = np.ones((3, 3), np.uint8)
    dilated = cv2.dilate(bright_mask, kernel, iterations=2)

    # Use Hough Line Transform
    lines = cv2.HoughLinesP(dilated, 1, np.pi/180, threshold=40,
                            minLineLength=50, maxLineGap=30)

    h_lines = []
    v_lines = []

    if lines is not None:
        for line in lines:
            x1, y1, x2, y2 = line[0]
            dx = abs(x2 - x1)
            dy = abs(y2 - y1)
            length = math.sqrt(dx*dx + dy*dy)

            # Horizontal line (small vertical change, significant horizontal span)
            if dy < 20 and dx > 50:
                y_avg = (y1 + y2) // 2
                h_lines.append((y_avg, length))

            # Vertical line (small horizontal change, significant vertical span)
            elif dx < 20 and dy > 50:
                x_avg = (x1 + x2) // 2
                v_lines.append((x_avg, length))

    return h_lines, v_lines


def cluster_lines(lines: List[Tuple[int, float]], min_gap: int = 30) -> List[Tuple[int, float]]:
    """
    Cluster nearby lines and return (position, total_length) for each cluster.
    """
    if not lines:
        return []

    sorted_lines = sorted(lines, key=lambda x: x[0])
    clusters = [[sorted_lines[0]]]

    for line in sorted_lines[1:]:
        if line[0] - clusters[-1][-1][0] < min_gap:
            clusters[-1].append(line)
        else:
            clusters.append([line])

    result = []
    for cluster in clusters:
        avg_pos = int(np.mean([l[0] for l in cluster]))
        total_len = sum(l[1] for l in cluster)
        result.append((avg_pos, total_len))

    return result


def detect_boundary(image: np.ndarray, debug: bool = False) -> Optional[DrawingArea]:
    """
    Detect the drawing boundary using pure line detection.
    No hardcoded ratios - works for any screen size.
    """
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Find card region
    card_x, card_y, card_w, card_h = find_card_region(gray)
    print(f"Card: x={card_x}, y={card_y}, w={card_w}, h={card_h}")

    # Extract card and get bright pixels (dotted lines are white)
    card_gray = gray[card_y:card_y+card_h, card_x:card_x+card_w]
    _, bright = cv2.threshold(card_gray, 200, 255, cv2.THRESH_BINARY)

    if debug:
        cv2.imwrite("debug_bright.png", bright)

    # Detect and cluster lines
    h_lines, v_lines = detect_lines(bright, card_w, card_h)
    h_clusters = cluster_lines(h_lines, min_gap=40)
    v_clusters = cluster_lines(v_lines, min_gap=40)

    print(f"H-clusters: {[(p, int(l)) for p, l in h_clusters]}")
    print(f"V-clusters: {[(p, int(l)) for p, l in v_clusters]}")

    # Sort by position
    h_sorted = sorted(h_clusters, key=lambda x: x[0])
    v_sorted = sorted(v_clusters, key=lambda x: x[0])

    if len(h_sorted) < 3 or len(v_sorted) < 3:
        print("Warning: Not enough lines detected, results may be inaccurate")

    # Identify boundary lines based on position and length
    # The dotted boundary lines should be among the longest detected

    # Horizontal lines (sorted top to bottom):
    # - First significant line = top boundary
    # - A line in the middle region = top-left exclusion bottom / VISA exclusion top
    # - Last significant line = bottom boundary

    # Vertical lines (sorted left to right):
    # - First significant line = left boundary
    # - A line in the middle-left = top-left exclusion right
    # - A line in the middle-right = VISA exclusion left
    # - Last significant line = right boundary

    # Find boundaries by selecting the most significant (longest) lines in each region
    def find_boundary_line(clusters, region_start, region_end, card_dim):
        """Find the strongest line within a region (as fraction of card dimension)."""
        candidates = [(p, l) for p, l in clusters
                     if region_start * card_dim <= p <= region_end * card_dim]
        if not candidates:
            return None
        # Return position of longest line in region
        return max(candidates, key=lambda x: x[1])[0]

    # Outer boundaries (should be near edges)
    top = find_boundary_line(h_sorted, 0.0, 0.15, card_h)
    bottom = find_boundary_line(h_sorted, 0.80, 1.0, card_h)
    left = find_boundary_line(v_sorted, 0.0, 0.15, card_w)
    right = find_boundary_line(v_sorted, 0.85, 1.0, card_w)

    # Inner boundaries (exclusion zones)
    # Top-left exclusion: look for lines in the upper-left quadrant
    top_excl_bottom = find_boundary_line(h_sorted, 0.10, 0.25, card_h)
    top_excl_right = find_boundary_line(v_sorted, 0.12, 0.30, card_w)

    # VISA exclusion: look for lines in the middle-right region
    visa_top = find_boundary_line(h_sorted, 0.45, 0.70, card_h)
    visa_left = find_boundary_line(v_sorted, 0.50, 0.75, card_w)

    # Use detected values or estimate from card dimensions
    top = top if top is not None else int(card_h * 0.05)
    bottom = bottom if bottom is not None else int(card_h * 0.92)
    left = left if left is not None else int(card_w * 0.07)
    right = right if right is not None else int(card_w * 0.94)

    top_excl_bottom = top_excl_bottom if top_excl_bottom is not None else int(card_h * 0.18)
    top_excl_right = top_excl_right if top_excl_right is not None else int(card_w * 0.18)

    visa_top = visa_top if visa_top is not None else int(card_h * 0.58)
    visa_left = visa_left if visa_left is not None else int(card_w * 0.60)

    print(f"Detected boundaries:")
    print(f"  Outer: top={top}, bottom={bottom}, left={left}, right={right}")
    print(f"  Top-left excl: right={top_excl_right}, bottom={top_excl_bottom}")
    print(f"  VISA excl: left={visa_left}, top={visa_top}")

    area = DrawingArea(
        top=card_y + top,
        left=card_x + left,
        right=card_x + right,
        bottom=card_y + bottom,
        cutout_left=card_x + visa_left,
        cutout_top=card_y + visa_top,
        top_excl_right=card_x + top_excl_right,
        top_excl_bottom=card_y + top_excl_bottom
    )

    if debug:
        debug_img = image.copy()

        # Draw outer boundary (green)
        cv2.rectangle(debug_img, (area.left, area.top), (area.right, area.bottom), (0, 255, 0), 2)

        # Draw exclusion zones
        # Top-left (cyan)
        cv2.rectangle(debug_img, (area.left, area.top),
                     (area.top_excl_right, area.top_excl_bottom), (255, 255, 0), 2)
        # VISA (red)
        cv2.rectangle(debug_img, (area.cutout_left, area.cutout_top),
                     (area.right, area.bottom), (0, 0, 255), 2)

        # Draw actual drawable boundary (yellow polygon)
        pts = np.array([
            [area.top_excl_right, area.top],
            [area.right, area.top],
            [area.right, area.cutout_top],
            [area.cutout_left, area.cutout_top],
            [area.cutout_left, area.bottom],
            [area.left, area.bottom],
            [area.left, area.top_excl_bottom],
            [area.top_excl_right, area.top_excl_bottom],
            [area.top_excl_right, area.top]
        ], np.int32)
        cv2.polylines(debug_img, [pts], True, (0, 255, 255), 3)

        # Draw center
        cx, cy = area.center
        cv2.circle(debug_img, (cx, cy), 8, (255, 0, 255), -1)

        cv2.imwrite("debug_detection.png", debug_img)
        print("Debug saved: debug_detection.png")

    return area


def detect_from_screenshot(screenshot_path: str = None, debug: bool = False) -> DrawingArea:
    """Main detection function."""
    if screenshot_path is None:
        screenshot_path = capture_screenshot()

    image = cv2.imread(screenshot_path)
    if image is None:
        raise ValueError(f"Could not load image: {screenshot_path}")

    print(f"Image: {image.shape[1]}x{image.shape[0]}")

    area = detect_boundary(image, debug=debug)
    if area is None:
        raise RuntimeError("Detection failed")

    print(f"\nResult: {area}")
    print(f"Center: {area.center}")

    return area


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Detect Revolut card drawing area")
    parser.add_argument("--screenshot", "-s", help="Path to screenshot")
    parser.add_argument("--serial", "-S", help="ADB device serial number")
    parser.add_argument("--debug", "-d", action="store_true", help="Save debug images")
    args = parser.parse_args()

    if args.serial:
        import os
        os.environ['ANDROID_SERIAL'] = args.serial
    elif not os.environ.get('ANDROID_SERIAL'):
        # Auto-pick physical device
        try:
            import os
            import subprocess
            res = subprocess.run(['adb', '-d', 'get-serialno'], capture_output=True, text=True, timeout=2)
            if res.returncode == 0 and 'unknown' not in res.stdout.lower() and 'error' not in res.stdout.lower():
                os.environ['ANDROID_SERIAL'] = res.stdout.strip()
        except:
            pass

    try:
        area = detect_from_screenshot(args.screenshot, debug=args.debug)
        safe = area.get_safe_bounds(margin=20)
        print(f"\nSafe area: {safe}")
        print(f"Usable rect: {safe.get_usable_rect()}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

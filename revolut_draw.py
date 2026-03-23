#!/usr/bin/env python3
"""
RevoDraw - Shape & Text Drawing CLI

Draw shapes and text on Revolut card customization screen via ADB.
Automatically detects the drawing area from the dotted line boundary.
"""

import subprocess
import time
import math
import sys
from typing import List, Tuple
from detect_drawing_area import detect_from_screenshot, DrawingArea


class ADBDrawer:
    """Draw on Android via ADB input commands."""

    FONT = {
        'A': [[(0, 14), (5, 0), (10, 14)], [(2, 9), (8, 9)]],
        'B': [[(0, 0), (0, 14), (7, 14), (10, 11), (10, 9), (7, 7), (0, 7), (7, 7), (10, 5), (10, 2), (7, 0), (0, 0)]],
        'C': [[(10, 2), (7, 0), (3, 0), (0, 3), (0, 11), (3, 14), (7, 14), (10, 12)]],
        'D': [[(0, 0), (0, 14), (6, 14), (10, 11), (10, 3), (6, 0), (0, 0)]],
        'E': [[(10, 0), (0, 0), (0, 14), (10, 14)], [(0, 7), (7, 7)]],
        'F': [[(10, 0), (0, 0), (0, 14)], [(0, 7), (7, 7)]],
        'G': [[(10, 2), (7, 0), (3, 0), (0, 3), (0, 11), (3, 14), (7, 14), (10, 11), (10, 7), (5, 7)]],
        'H': [[(0, 0), (0, 14)], [(10, 0), (10, 14)], [(0, 7), (10, 7)]],
        'I': [[(2, 0), (8, 0)], [(5, 0), (5, 14)], [(2, 14), (8, 14)]],
        'J': [[(10, 0), (10, 11), (7, 14), (3, 14), (0, 11)]],
        'K': [[(0, 0), (0, 14)], [(10, 0), (0, 7), (10, 14)]],
        'L': [[(0, 0), (0, 14), (10, 14)]],
        'M': [[(0, 14), (0, 0), (5, 7), (10, 0), (10, 14)]],
        'N': [[(0, 14), (0, 0), (10, 14), (10, 0)]],
        'O': [[(3, 0), (7, 0), (10, 3), (10, 11), (7, 14), (3, 14), (0, 11), (0, 3), (3, 0)]],
        'P': [[(0, 14), (0, 0), (7, 0), (10, 2), (10, 5), (7, 7), (0, 7)]],
        'Q': [[(3, 0), (7, 0), (10, 3), (10, 11), (7, 14), (3, 14), (0, 11), (0, 3), (3, 0)], [(6, 10), (10, 14)]],
        'R': [[(0, 14), (0, 0), (7, 0), (10, 2), (10, 5), (7, 7), (0, 7)], [(5, 7), (10, 14)]],
        'S': [[(10, 2), (7, 0), (3, 0), (0, 2), (0, 5), (3, 7), (7, 7), (10, 9), (10, 12), (7, 14), (3, 14), (0, 12)]],
        'T': [[(0, 0), (10, 0)], [(5, 0), (5, 14)]],
        'U': [[(0, 0), (0, 11), (3, 14), (7, 14), (10, 11), (10, 0)]],
        'V': [[(0, 0), (5, 14), (10, 0)]],
        'W': [[(0, 0), (2, 14), (5, 7), (8, 14), (10, 0)]],
        'X': [[(0, 0), (10, 14)], [(10, 0), (0, 14)]],
        'Y': [[(0, 0), (5, 7), (10, 0)], [(5, 7), (5, 14)]],
        'Z': [[(0, 0), (10, 0), (0, 14), (10, 14)]],
        ' ': [],
        '0': [[(3, 0), (7, 0), (10, 3), (10, 11), (7, 14), (3, 14), (0, 11), (0, 3), (3, 0)]],
        '1': [[(3, 3), (5, 0), (5, 14)]],
        '2': [[(0, 3), (3, 0), (7, 0), (10, 3), (10, 5), (0, 14), (10, 14)]],
        '3': [[(0, 2), (3, 0), (7, 0), (10, 3), (7, 7), (10, 11), (7, 14), (3, 14), (0, 12)]],
        '4': [[(8, 14), (8, 0), (0, 10), (10, 10)]],
        '5': [[(10, 0), (0, 0), (0, 6), (7, 6), (10, 9), (10, 12), (7, 14), (3, 14), (0, 12)]],
        '6': [[(7, 0), (3, 0), (0, 3), (0, 11), (3, 14), (7, 14), (10, 11), (10, 9), (7, 6), (0, 6)]],
        '7': [[(0, 0), (10, 0), (4, 14)]],
        '8': [[(3, 7), (0, 5), (0, 2), (3, 0), (7, 0), (10, 2), (10, 5), (7, 7), (3, 7), (0, 9), (0, 12), (3, 14), (7, 14), (10, 12), (10, 9), (7, 7)]],
        '9': [[(10, 6), (3, 6), (0, 3), (0, 2), (3, 0), (7, 0), (10, 3), (10, 11), (7, 14), (3, 14)]],
        '!': [[(5, 0), (5, 10)], [(5, 13), (5, 14)]],
        '?': [[(0, 3), (3, 0), (7, 0), (10, 3), (10, 5), (5, 8), (5, 10)], [(5, 13), (5, 14)]],
        '.': [[(5, 13), (5, 14)]],
        '-': [[(2, 7), (8, 7)]],
        '+': [[(5, 3), (5, 11)], [(1, 7), (9, 7)]],
        '*': [[(5, 2), (5, 12)], [(1, 4), (9, 10)], [(9, 4), (1, 10)]],
        '/': [[(10, 0), (0, 14)]],
        ':': [[(5, 4), (5, 5)], [(5, 9), (5, 10)]],
        '<': [[(8, 2), (2, 7), (8, 12)]],
        '>': [[(2, 2), (8, 7), (2, 12)]],
    }

    def __init__(self, stroke_duration: int = 80):
        self.stroke_duration = stroke_duration
        self._verify_adb()

    def _verify_adb(self):
        result = subprocess.run(['adb', 'devices'], capture_output=True, text=True)
        if 'device' not in result.stdout.split('\n')[1]:
            raise RuntimeError("No ADB device connected")

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration: int = None):
        duration = duration or self.stroke_duration
        subprocess.run(['adb', 'shell', 'input', 'swipe',
                       str(int(x1)), str(int(y1)), str(int(x2)), str(int(y2)), str(duration)],
                      capture_output=True)

    def draw_path(self, points: List[Tuple[int, int]], delay: float = 0.02):
        if len(points) < 2:
            return
        for i in range(len(points) - 1):
            self.swipe(points[i][0], points[i][1], points[i+1][0], points[i+1][1])
            time.sleep(delay)

    def draw_circle(self, cx: int, cy: int, radius: int, segments: int = 36):
        points = []
        for i in range(segments + 1):
            angle = 2 * math.pi * i / segments
            x = int(cx + radius * math.cos(angle))
            y = int(cy + radius * math.sin(angle))
            points.append((x, y))
        self.draw_path(points)

    def draw_heart(self, cx: int, cy: int, size: int):
        points = []
        for i in range(50):
            t = i * 2 * math.pi / 50
            x = 16 * math.sin(t) ** 3
            y = -(13 * math.cos(t) - 5 * math.cos(2*t) - 2 * math.cos(3*t) - math.cos(4*t))
            x = int(cx + x * size / 16)
            y = int(cy + y * size / 16)
            points.append((x, y))
        points.append(points[0])
        self.draw_path(points)

    def draw_star(self, cx: int, cy: int, outer_r: int, inner_r: int = None, num_points: int = 5):
        inner_r = inner_r or outer_r // 2
        points = []
        for i in range(num_points * 2 + 1):
            angle = math.pi * i / num_points - math.pi / 2
            r = outer_r if i % 2 == 0 else inner_r
            x = int(cx + r * math.cos(angle))
            y = int(cy + r * math.sin(angle))
            points.append((x, y))
        self.draw_path(points)

    def draw_spiral(self, cx: int, cy: int, max_radius: int, turns: float = 3):
        points = []
        steps = int(turns * 40)
        for i in range(steps):
            t = i / steps
            angle = turns * 2 * math.pi * t
            radius = max_radius * t
            x = int(cx + radius * math.cos(angle))
            y = int(cy + radius * math.sin(angle))
            points.append((x, y))
        self.draw_path(points)

    def draw_char(self, char: str, x: int, y: int, width: int = 25, height: int = 35):
        char = char.upper()
        if char not in self.FONT:
            return
        scale_x = width / 10
        scale_y = height / 14
        for stroke in self.FONT[char]:
            points = [(int(x + px * scale_x), int(y + py * scale_y)) for px, py in stroke]
            if len(points) >= 2:
                self.draw_path(points)
                time.sleep(0.03)

    def draw_text(self, text: str, x: int, y: int, char_width: int = 25, char_height: int = 35, spacing: int = 6):
        current_x = x
        for char in text:
            self.draw_char(char, current_x, y, char_width, char_height)
            current_x += char_width + spacing
            time.sleep(0.03)

    def get_text_width(self, text: str, char_width: int = 25, spacing: int = 6) -> int:
        return len(text) * (char_width + spacing) - spacing


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Draw on Revolut card customization",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python revolut_draw.py --heart
  python revolut_draw.py --text "HELLO"
  python revolut_draw.py --demo
  python revolut_draw.py --interactive
  python revolut_draw.py --heart --x 300 --y 800  # Manual coordinates
        """
    )

    parser.add_argument("--demo", action="store_true", help="Draw demo shapes")
    parser.add_argument("--text", "-t", help="Text to draw")
    parser.add_argument("--heart", action="store_true", help="Draw a heart")
    parser.add_argument("--star", action="store_true", help="Draw a star")
    parser.add_argument("--circle", action="store_true", help="Draw a circle")
    parser.add_argument("--spiral", action="store_true", help="Draw a spiral")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    parser.add_argument("--x", type=int, help="X coordinate (auto-detected if not set)")
    parser.add_argument("--y", type=int, help="Y coordinate (auto-detected if not set)")
    parser.add_argument("--size", type=int, default=60, help="Shape size")
    parser.add_argument("--no-detect", action="store_true", help="Skip auto-detection, use manual coords")
    parser.add_argument("--serial", "-s", help="ADB device serial number")
    parser.add_argument("--debug", "-d", action="store_true", help="Save debug images during detection")

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

    if not any([args.demo, args.text, args.heart, args.star, args.circle, args.spiral, args.interactive]):
        parser.print_help()
        return

    # Get drawing coordinates
    if args.x is not None and args.y is not None:
        cx, cy = args.x, args.y
        print(f"Using manual coordinates: ({cx}, {cy})")
    elif args.no_detect:
        cx, cy = 350, 850  # Fallback default
        print(f"Using default coordinates: ({cx}, {cy})")
    else:
        print("Detecting drawing area...")
        try:
            area = detect_from_screenshot(debug=args.debug)
            safe = area.get_safe_bounds(margin=30)
            cx, cy = safe.center
            print(f"Detected center: ({cx}, {cy})")
            print(f"Safe bounds: {safe.left},{safe.top} to {safe.right},{safe.bottom}")
        except Exception as e:
            print(f"Detection failed: {e}")
            print("Using fallback coordinates")
            cx, cy = 350, 850

    drawer = ADBDrawer()

    if args.demo:
        print("Drawing demo shapes...")
        drawer.draw_heart(cx - 80, cy - 60, args.size)
        time.sleep(0.3)
        drawer.draw_star(cx + 80, cy - 60, args.size)
        time.sleep(0.3)
        drawer.draw_spiral(cx, cy + 80, args.size // 2, turns=2)
        print("Done!")

    if args.heart:
        print(f"Drawing heart at ({cx}, {cy})...")
        drawer.draw_heart(cx, cy, args.size)
        print("Done!")

    if args.star:
        print(f"Drawing star at ({cx}, {cy})...")
        drawer.draw_star(cx, cy, args.size)
        print("Done!")

    if args.circle:
        print(f"Drawing circle at ({cx}, {cy})...")
        drawer.draw_circle(cx, cy, args.size)
        print("Done!")

    if args.spiral:
        print(f"Drawing spiral at ({cx}, {cy})...")
        drawer.draw_spiral(cx, cy, args.size, turns=3)
        print("Done!")

    if args.text:
        print(f"Drawing text: {args.text}")
        char_width = min(25, 400 // max(len(args.text), 1))
        total_width = drawer.get_text_width(args.text, char_width)
        start_x = cx - total_width // 2
        start_y = cy - 17
        drawer.draw_text(args.text, start_x, start_y, char_width)
        print("Done!")

    if args.interactive:
        print(f"\n=== Interactive Mode ===")
        print(f"Center: ({cx}, {cy}), Size: {args.size}")
        print("Commands: heart, star, circle, spiral, text <msg>, demo, quit\n")

        while True:
            try:
                cmd = input("draw> ").strip()
            except (EOFError, KeyboardInterrupt):
                break

            if not cmd:
                continue

            parts = cmd.split(maxsplit=1)
            action = parts[0].lower()

            if action in ('quit', 'exit', 'q'):
                break
            elif action == 'heart':
                drawer.draw_heart(cx, cy, args.size)
            elif action == 'star':
                drawer.draw_star(cx, cy, args.size)
            elif action == 'circle':
                drawer.draw_circle(cx, cy, args.size)
            elif action == 'spiral':
                drawer.draw_spiral(cx, cy, args.size)
            elif action == 'demo':
                drawer.draw_heart(cx - 80, cy - 60, args.size)
                time.sleep(0.3)
                drawer.draw_star(cx + 80, cy - 60, args.size)
            elif action == 'text' and len(parts) > 1:
                text = parts[1]
                char_width = min(25, 350 // max(len(text), 1))
                total_width = drawer.get_text_width(text, char_width)
                drawer.draw_text(text, cx - total_width // 2, cy - 17, char_width)
            else:
                print(f"Unknown: {action}")

        print("Bye!")


if __name__ == "__main__":
    main()

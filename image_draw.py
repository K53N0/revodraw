#!/usr/bin/env python3
"""
RevoDraw - Image Drawing CLI

Draw an image within the Revolut card's dotted line boundary.

Pipeline:
1. Detect the drawing area from screenshot
2. Load and process the input image
3. Extract drawable paths (edges/contours)
4. Scale and map paths to fit within the detected area
5. Draw via ADB
"""

import cv2
import numpy as np
import subprocess
import time
import math
import sys
from pathlib import Path
from typing import List, Tuple, Optional
from dataclasses import dataclass

from detect_drawing_area import detect_from_screenshot, DrawingArea


@dataclass
class ImagePaths:
    """Extracted paths from an image."""
    paths: List[List[Tuple[int, int]]]
    width: int
    height: int


def load_image(image_path: str, max_size: int = 500) -> np.ndarray:
    """Load and resize image."""
    img = cv2.imread(image_path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        raise ValueError(f"Could not load image: {image_path}")

    h, w = img.shape
    if max(h, w) > max_size:
        scale = max_size / max(h, w)
        img = cv2.resize(img, (int(w * scale), int(h * scale)))

    return img


def extract_paths_edges(img: np.ndarray, simplify: float = 2.0) -> ImagePaths:
    """
    Extract paths using Canny edge detection.
    Good for photos and complex images.
    """
    # Apply blur to reduce noise
    blurred = cv2.GaussianBlur(img, (5, 5), 0)

    # Auto threshold using Otsu's method
    high_thresh, _ = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    low_thresh = high_thresh * 0.5

    # Detect edges
    edges = cv2.Canny(blurred, low_thresh, high_thresh)

    # Find contours
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    paths = []
    for contour in contours:
        if len(contour) < 5:
            continue

        # Simplify contour
        if simplify > 0:
            epsilon = simplify
            contour = cv2.approxPolyDP(contour, epsilon, False)

        path = [(int(p[0][0]), int(p[0][1])) for p in contour]
        if len(path) >= 2:
            paths.append(path)

    return ImagePaths(paths=paths, width=img.shape[1], height=img.shape[0])


def extract_paths_contours(img: np.ndarray, threshold: int = 127,
                           simplify: float = 2.0, invert: bool = False) -> ImagePaths:
    """
    Extract paths using threshold and contour detection.
    Good for logos, drawings, and high-contrast images.
    """
    # Threshold
    if invert:
        _, binary = cv2.threshold(img, threshold, 255, cv2.THRESH_BINARY_INV)
    else:
        _, binary = cv2.threshold(img, threshold, 255, cv2.THRESH_BINARY)

    # Find contours
    contours, _ = cv2.findContours(binary, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    paths = []
    for contour in contours:
        area = cv2.contourArea(contour)
        if area < 20:  # Skip tiny contours
            continue

        # Simplify
        if simplify > 0:
            epsilon = simplify
            contour = cv2.approxPolyDP(contour, epsilon, True)

        path = [(int(p[0][0]), int(p[0][1])) for p in contour]
        if len(path) >= 3:
            path.append(path[0])  # Close the contour
            paths.append(path)

    return ImagePaths(paths=paths, width=img.shape[1], height=img.shape[0])


def extract_paths_adaptive(img: np.ndarray, simplify: float = 2.0) -> ImagePaths:
    """
    Extract paths using adaptive thresholding.
    Good for images with varying lighting.
    """
    # Adaptive threshold
    binary = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                    cv2.THRESH_BINARY_INV, 11, 2)

    # Morphological cleanup
    kernel = np.ones((2, 2), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel)

    # Find contours
    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    paths = []
    for contour in contours:
        if cv2.contourArea(contour) < 30:
            continue

        if simplify > 0:
            contour = cv2.approxPolyDP(contour, simplify, True)

        path = [(int(p[0][0]), int(p[0][1])) for p in contour]
        if len(path) >= 3:
            path.append(path[0])
            paths.append(path)

    return ImagePaths(paths=paths, width=img.shape[1], height=img.shape[0])


def scale_paths_to_area(image_paths: ImagePaths, area: DrawingArea,
                        margin: int = 20, maintain_aspect: bool = True,
                        use_full_area: bool = False) -> List[List[Tuple[int, int]]]:
    """
    Scale and translate paths to fit within the drawing area.

    If use_full_area is True, uses the entire L-shape (may clip some content in cutout).
    If False, uses only the left portion (safe, no clipping).
    """
    if not image_paths.paths:
        return []

    if use_full_area:
        # Use the full L-shape bounding box
        # Content in the cutout area will be clipped
        available_width = area.right - area.left - 2 * margin
        available_height = area.bottom - area.top - 2 * margin
    else:
        # Use only the main left portion (safe for images)
        available_width = area.cutout_left - area.left - 2 * margin
        available_height = area.bottom - area.top - 2 * margin

    src_width = image_paths.width
    src_height = image_paths.height

    if maintain_aspect:
        scale = min(available_width / src_width, available_height / src_height)
        scale_x = scale_y = scale
    else:
        scale_x = available_width / src_width
        scale_y = available_height / src_height

    # Calculate offset to center the image
    scaled_width = src_width * scale_x
    scaled_height = src_height * scale_y
    offset_x = area.left + margin + (available_width - scaled_width) / 2
    offset_y = area.top + margin + (available_height - scaled_height) / 2

    # Scale all paths
    scaled_paths = []
    for path in image_paths.paths:
        scaled_path = []
        for x, y in path:
            new_x = int(offset_x + x * scale_x)
            new_y = int(offset_y + y * scale_y)
            # Check if point is inside the L-shaped drawing area
            if area.is_inside(new_x, new_y):
                scaled_path.append((new_x, new_y))

        if len(scaled_path) >= 2:
            scaled_paths.append(scaled_path)

    return scaled_paths


def draw_paths_adb(paths: List[List[Tuple[int, int]]],
                   stroke_duration: int = 60, delay: float = 0.015):
    """Draw paths using ADB input commands."""
    total_paths = len(paths)

    for i, path in enumerate(paths):
        if len(path) < 2:
            continue

        print(f"  Drawing path {i+1}/{total_paths} ({len(path)} points)", end='\r')

        for j in range(len(path) - 1):
            x1, y1 = path[j]
            x2, y2 = path[j + 1]
            subprocess.run(
                ['adb', 'shell', 'input', 'swipe',
                 str(x1), str(y1), str(x2), str(y2), str(stroke_duration)],
                capture_output=True
            )
            time.sleep(delay)

    print()  # New line after progress


def preview_paths(paths: List[List[Tuple[int, int]]], area: DrawingArea,
                  output_path: str = "preview.png"):
    """Generate a preview image of what will be drawn."""
    # Create canvas matching the screen area
    width = area.right + 100
    height = area.bottom + 100
    canvas = np.zeros((height, width, 3), dtype=np.uint8)

    # Draw the drawing area boundary
    cv2.rectangle(canvas, (area.left, area.top), (area.right, area.bottom), (50, 50, 50), 2)
    cv2.rectangle(canvas, (area.cutout_left, area.cutout_top),
                  (area.right, area.bottom), (30, 30, 50), 2)

    # Draw paths
    colors = [(0, 255, 0), (0, 255, 255), (255, 255, 0), (255, 0, 255)]
    for i, path in enumerate(paths):
        color = colors[i % len(colors)]
        for j in range(len(path) - 1):
            pt1 = path[j]
            pt2 = path[j + 1]
            cv2.line(canvas, pt1, pt2, color, 1)

    cv2.imwrite(output_path, canvas)
    print(f"Preview saved to {output_path}")


def process_and_draw(image_path: str, method: str = 'auto',
                     threshold: int = 127, simplify: float = 2.0,
                     preview_only: bool = False, full_area: bool = False,
                     debug: bool = False):
    """
    Main function to process an image and draw it.
    """
    print(f"Loading image: {image_path}")
    img = load_image(image_path)
    print(f"Image size: {img.shape[1]}x{img.shape[0]}")

    # Auto-detect best method based on image characteristics
    if method == 'auto':
        # Check if image is high contrast (likely a logo/drawing)
        std_dev = np.std(img)
        if std_dev > 70:
            method = 'contours'
        else:
            method = 'edges'
        print(f"Auto-selected method: {method}")

    # Extract paths
    print(f"Extracting paths using {method} method...")
    if method == 'edges':
        image_paths = extract_paths_edges(img, simplify)
    elif method == 'contours':
        image_paths = extract_paths_contours(img, threshold, simplify)
    elif method == 'contours_inv':
        image_paths = extract_paths_contours(img, threshold, simplify, invert=True)
    elif method == 'adaptive':
        image_paths = extract_paths_adaptive(img, simplify)
    else:
        raise ValueError(f"Unknown method: {method}")

    print(f"Extracted {len(image_paths.paths)} paths")

    if not image_paths.paths:
        print("No paths extracted! Try adjusting threshold or method.")
        return

    # Detect drawing area
    print("\nDetecting drawing area...")
    area = detect_from_screenshot(debug=debug)
    safe_area = area.get_safe_bounds(margin=25)
    print(f"Drawing area: {safe_area.left},{safe_area.top} to {safe_area.right},{safe_area.bottom}")

    # Scale paths to fit area
    print(f"Scaling paths to fit area (full_area={full_area})...")
    scaled_paths = scale_paths_to_area(image_paths, safe_area, margin=10, use_full_area=full_area)
    print(f"Scaled to {len(scaled_paths)} drawable paths")

    if not scaled_paths:
        print("No paths fit within the drawing area!")
        return

    # Generate preview
    preview_paths(scaled_paths, safe_area, "draw_preview.png")

    if preview_only:
        print("Preview only mode - not drawing")
        return

    # Draw!
    total_points = sum(len(p) for p in scaled_paths)
    print(f"\nDrawing {len(scaled_paths)} paths ({total_points} total points)...")
    print("This may take a while...")

    draw_paths_adb(scaled_paths)
    print("Done!")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Draw an image on Revolut card customization screen",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Methods:
  auto          - Automatically choose best method
  edges         - Canny edge detection (good for photos)
  contours      - Threshold + contours (good for logos, dark on light)
  contours_inv  - Inverted contours (good for light on dark)
  adaptive      - Adaptive threshold (good for varying lighting)

Examples:
  python image_draw.py logo.png
  python image_draw.py photo.jpg --method edges
  python image_draw.py drawing.png --method contours --threshold 100
  python image_draw.py logo.png --preview  # Preview without drawing
        """
    )

    parser.add_argument("image", help="Path to image file")
    parser.add_argument("--method", "-m", default="auto",
                       choices=['auto', 'edges', 'contours', 'contours_inv', 'adaptive'],
                       help="Path extraction method")
    parser.add_argument("--threshold", "-t", type=int, default=127,
                       help="Threshold for contour methods (0-255)")
    parser.add_argument("--simplify", "-s", type=float, default=2.0,
                       help="Path simplification factor (higher = simpler)")
    parser.add_argument("--preview", "-p", action="store_true",
                       help="Preview only, don't draw")
    parser.add_argument("--full-area", "-f", action="store_true",
                       help="Use full L-shaped area (content in VISA zone will be clipped)")
    parser.add_argument("--serial", "-S", help="ADB device serial number")
    parser.add_argument("--debug", "-d", action="store_true",
                       help="Save debug images")

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

    if not Path(args.image).exists():
        print(f"Error: Image not found: {args.image}")
        sys.exit(1)

    try:
        process_and_draw(
            args.image,
            method=args.method,
            threshold=args.threshold,
            simplify=args.simplify,
            preview_only=args.preview,
            full_area=args.full_area,
            debug=args.debug
        )
    except KeyboardInterrupt:
        print("\nInterrupted")
    except Exception as e:
        print(f"Error: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()

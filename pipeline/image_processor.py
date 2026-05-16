"""
FieldForge — Image Processor
==============================
Preprocesses phone photos of hand-drawn circuit schematics for Gemma 4.
Handles: low-light, blur, tilt, shadows, crumpled paper.
"""
from __future__ import annotations

import base64
import io
import logging
import math
from pathlib import Path
from typing import Union

import cv2
import numpy as np
from PIL import Image

from config import IMAGE_MAX_DIMENSION

logger = logging.getLogger(__name__)


class ImageProcessor:
    """
    Preprocessing pipeline for hand-drawn circuit schematic photos.

    Pipeline: load → resize → grayscale → CLAHE → bilateral filter →
              adaptive threshold → deskew → encode → detect components.
    """

    def __init__(self, max_dimension: int = None):
        self.max_dimension = max_dimension or IMAGE_MAX_DIMENSION

    def load_image(self, path: str) -> np.ndarray:
        """
        Load image from file path or base64 string.

        Args:
            path: File path to image, or base64-encoded string.

        Returns:
            Image as numpy array (BGR colorspace).

        Raises:
            FileNotFoundError: If file path doesn't exist.
            ValueError: If image cannot be decoded.
        """
        if Path(path).exists():
            image = cv2.imread(str(path))
            if image is None:
                raise ValueError(f"Cannot decode image: {path}")
            logger.info(f"Loaded image: {path} ({image.shape[1]}x{image.shape[0]})")
            return image

        # Try base64 decode
        try:
            img_bytes = base64.b64decode(path)
            nparr = np.frombuffer(img_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            if image is None:
                raise ValueError("Cannot decode base64 image data")
            return image
        except Exception:
            raise FileNotFoundError(f"Image not found and not valid base64: {path}")

    def preprocess(self, image: np.ndarray) -> np.ndarray:
        """
        Full preprocessing pipeline for schematic photos.

        Steps:
        1. Resize to max dimension (preserve aspect ratio)
        2. Convert to grayscale
        3. CLAHE (adaptive histogram equalization)
        4. Bilateral filter (preserve edges, remove noise)
        5. Adaptive threshold (Otsu)
        6. Deskew via Hough line detection

        Args:
            image: Input image (BGR).

        Returns:
            Cleaned, binary image suitable for AI analysis.
        """
        # 1. Resize
        h, w = image.shape[:2]
        if max(h, w) > self.max_dimension:
            scale = self.max_dimension / max(h, w)
            new_w, new_h = int(w * scale), int(h * scale)
            image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_AREA)
            logger.debug(f"Resized: {w}x{h} → {new_w}x{new_h}")

        # 2. Grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        # 3. CLAHE — adaptive contrast enhancement
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # 4. Bilateral filter — smooth noise, keep edges
        filtered = cv2.bilateralFilter(enhanced, d=9, sigmaColor=75, sigmaSpace=75)

        # 5. Otsu threshold — binary image
        _, binary = cv2.threshold(filtered, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # 6. Deskew
        deskewed = self._deskew(binary)

        logger.info(f"Preprocessing complete: {deskewed.shape[1]}x{deskewed.shape[0]}")
        return deskewed

    def _deskew(self, image: np.ndarray) -> np.ndarray:
        """Detect and correct rotation using Hough line transform."""
        edges = cv2.Canny(image, 50, 150, apertureSize=3)
        lines = cv2.HoughLines(edges, 1, np.pi / 180, threshold=100)

        if lines is None:
            return image

        angles = []
        for line in lines:
            rho, theta = line[0]
            angle = math.degrees(theta) - 90
            if abs(angle) < 45:  # Only consider near-horizontal lines
                angles.append(angle)

        if not angles:
            return image

        median_angle = np.median(angles)
        if abs(median_angle) < 0.5:  # Skip tiny corrections
            return image

        logger.debug(f"Deskew angle: {median_angle:.1f}°")

        h, w = image.shape[:2]
        center = (w // 2, h // 2)
        matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)
        rotated = cv2.warpAffine(
            image, matrix, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
        return rotated

    def encode_base64(self, image: np.ndarray) -> str:
        """
        Encode a processed image to base64 PNG string.

        Args:
            image: Image as numpy array (grayscale or BGR).

        Returns:
            Base64-encoded PNG string.
        """
        success, buffer = cv2.imencode(".png", image)
        if not success:
            raise ValueError("Failed to encode image to PNG")
        return base64.b64encode(buffer).decode("utf-8")

    def detect_components(self, image: np.ndarray) -> dict:
        """
        Detect distinct component regions using contour analysis.

        Args:
            image: Preprocessed binary image.

        Returns:
            Dict with component_count, bounding_boxes, and estimated_complexity.
        """
        # Invert if needed (components should be white on black)
        if np.mean(image) > 127:
            work = cv2.bitwise_not(image)
        else:
            work = image.copy()

        # Morphological operations to connect nearby components
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        dilated = cv2.dilate(work, kernel, iterations=2)

        contours, _ = cv2.findContours(
            dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )

        # Filter by area (ignore tiny noise and huge background)
        h, w = image.shape[:2]
        min_area = (h * w) * 0.001   # 0.1% of image
        max_area = (h * w) * 0.5     # 50% of image

        bounding_boxes = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if min_area < area < max_area:
                x, y, bw, bh = cv2.boundingRect(contour)
                bounding_boxes.append({
                    "x": int(x), "y": int(y),
                    "width": int(bw), "height": int(bh),
                    "area": int(area),
                })

        count = len(bounding_boxes)
        if count <= 3:
            complexity = "simple"
        elif count <= 8:
            complexity = "moderate"
        else:
            complexity = "complex"

        logger.info(f"Detected {count} components → complexity: {complexity}")

        return {
            "component_count": count,
            "bounding_boxes": bounding_boxes,
            "estimated_complexity": complexity,
        }

    def prepare_for_gemma(self, path: str) -> dict:
        """
        Full pipeline: load → preprocess → encode → detect.

        Args:
            path: Path to the schematic image.

        Returns:
            Dict with base64_image, complexity, dimensions, component_count.
        """
        raw = self.load_image(path)
        processed = self.preprocess(raw)
        encoded = self.encode_base64(processed)
        components = self.detect_components(processed)

        h, w = processed.shape[:2]

        return {
            "base64_image": encoded,
            "complexity": components["estimated_complexity"],
            "width": w,
            "height": h,
            "component_count": components["component_count"],
            "bounding_boxes": components["bounding_boxes"],
        }

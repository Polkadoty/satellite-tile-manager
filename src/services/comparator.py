"""Tile comparison service."""

from pathlib import Path
from typing import Optional

# Optional dependencies for serverless compatibility
try:
    import numpy as np
    from PIL import Image
    HAS_IMAGE_DEPS = True
except ImportError:
    HAS_IMAGE_DEPS = False
    np = None  # type: ignore
    Image = None  # type: ignore


class TileComparator:
    """Compare tiles from different providers."""

    def compare(self, path_a: str, path_b: str) -> dict:
        """Compare two tile images.

        Args:
            path_a: Path to first tile image
            path_b: Path to second tile image

        Returns:
            Dictionary with comparison metrics
        """
        if not HAS_IMAGE_DEPS:
            return {"error": "Image comparison not available (numpy/PIL not installed)"}

        try:
            img_a = self._load_image(path_a)
            img_b = self._load_image(path_b)
        except Exception as e:
            return {"error": str(e)}

        # Resize to match if needed
        if img_a.shape != img_b.shape:
            # Resize to smaller dimensions
            h = min(img_a.shape[0], img_b.shape[0])
            w = min(img_a.shape[1], img_b.shape[1])
            img_a = self._resize(img_a, (h, w))
            img_b = self._resize(img_b, (h, w))

        result = {
            "mse": self._mse(img_a, img_b),
            "psnr": self._psnr(img_a, img_b),
            "ssim": self._ssim(img_a, img_b),
            "histogram_correlation": self._histogram_correlation(img_a, img_b),
        }

        return result

    def _load_image(self, path: str) -> np.ndarray:
        """Load image as numpy array."""
        path = Path(path)
        if not path.exists():
            raise FileNotFoundError(f"Image not found: {path}")

        img = Image.open(path)

        # Convert to RGB if needed
        if img.mode != "RGB":
            img = img.convert("RGB")

        return np.array(img, dtype=np.float64)

    def _resize(self, img: np.ndarray, size: tuple[int, int]) -> np.ndarray:
        """Resize image to target size."""
        pil_img = Image.fromarray(img.astype(np.uint8))
        pil_img = pil_img.resize((size[1], size[0]), Image.Resampling.LANCZOS)
        return np.array(pil_img, dtype=np.float64)

    def _mse(self, img_a: np.ndarray, img_b: np.ndarray) -> float:
        """Calculate Mean Squared Error."""
        return float(np.mean((img_a - img_b) ** 2))

    def _psnr(self, img_a: np.ndarray, img_b: np.ndarray) -> float:
        """Calculate Peak Signal-to-Noise Ratio."""
        mse = self._mse(img_a, img_b)
        if mse == 0:
            return float("inf")
        max_pixel = 255.0
        return float(20 * np.log10(max_pixel / np.sqrt(mse)))

    def _ssim(
        self,
        img_a: np.ndarray,
        img_b: np.ndarray,
        k1: float = 0.01,
        k2: float = 0.03,
    ) -> float:
        """Calculate Structural Similarity Index (simplified version).

        This is a simplified SSIM calculation. For production use,
        consider using skimage.metrics.structural_similarity.
        """
        c1 = (k1 * 255) ** 2
        c2 = (k2 * 255) ** 2

        # Convert to grayscale for SSIM
        if len(img_a.shape) == 3:
            img_a = np.mean(img_a, axis=2)
        if len(img_b.shape) == 3:
            img_b = np.mean(img_b, axis=2)

        mu_a = np.mean(img_a)
        mu_b = np.mean(img_b)
        sigma_a = np.std(img_a)
        sigma_b = np.std(img_b)
        sigma_ab = np.mean((img_a - mu_a) * (img_b - mu_b))

        ssim = ((2 * mu_a * mu_b + c1) * (2 * sigma_ab + c2)) / (
            (mu_a**2 + mu_b**2 + c1) * (sigma_a**2 + sigma_b**2 + c2)
        )

        return float(ssim)

    def _histogram_correlation(self, img_a: np.ndarray, img_b: np.ndarray) -> float:
        """Calculate histogram correlation between images."""
        # Convert to grayscale
        if len(img_a.shape) == 3:
            gray_a = np.mean(img_a, axis=2)
        else:
            gray_a = img_a

        if len(img_b.shape) == 3:
            gray_b = np.mean(img_b, axis=2)
        else:
            gray_b = img_b

        # Calculate histograms
        hist_a, _ = np.histogram(gray_a.flatten(), bins=256, range=(0, 256))
        hist_b, _ = np.histogram(gray_b.flatten(), bins=256, range=(0, 256))

        # Normalize histograms
        hist_a = hist_a.astype(np.float64) / hist_a.sum()
        hist_b = hist_b.astype(np.float64) / hist_b.sum()

        # Calculate correlation
        mean_a = np.mean(hist_a)
        mean_b = np.mean(hist_b)

        numerator = np.sum((hist_a - mean_a) * (hist_b - mean_b))
        denominator = np.sqrt(
            np.sum((hist_a - mean_a) ** 2) * np.sum((hist_b - mean_b) ** 2)
        )

        if denominator == 0:
            return 0.0

        return float(numerator / denominator)

    def find_best_match(
        self,
        reference_path: str,
        candidate_paths: list[str],
    ) -> tuple[Optional[str], float]:
        """Find the best matching tile from candidates.

        Args:
            reference_path: Path to reference tile
            candidate_paths: List of paths to candidate tiles

        Returns:
            Tuple of (best_match_path, ssim_score)
        """
        best_match = None
        best_score = -1.0

        for path in candidate_paths:
            result = self.compare(reference_path, path)
            if "ssim" in result and result["ssim"] > best_score:
                best_score = result["ssim"]
                best_match = path

        return (best_match, best_score)

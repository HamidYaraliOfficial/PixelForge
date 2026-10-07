# PixelForge - Compression Decision Engine

This document explains exactly how PixelForge decides what to do with a given
image, so the "why did it pick this?" question always has a concrete answer.

## 1. Feature extraction (`analysis/features.py`)

Every image is decoded once and measured for:

- **Container facts**: resolution, aspect ratio, file size, format, MIME type.
- **Colour facts**: mode (RGB/RGBA/CMYK/Grayscale/Palette), alpha presence,
  bit depth, approximate unique colour count (sampled + capped for speed).
- **Texture/statistical signals**: Shannon entropy, contrast (luminance
  std-dev), dynamic range (1st-99th percentile luminance spread), edge
  density (fraction of strong-edge pixels from a Sobel-like filter),
  sharpness (variance of the edge response), noise level (residual between
  the image and a Gaussian-blurred copy of itself), and flat-region ratio
  (fraction of 8x8 blocks with low internal variance).
- **Heuristic content-type scores** (each 0.0-1.0): `photo_score`,
  `illustration_score`, `screenshot_score`, `text_density`, `line_art_score`.
  These are explicitly documented as heuristics, not a trained classifier -
  they are weighted evidence, not ground truth, and the engine treats them
  that way.

## 2. Candidate generation (`optimizer/decision.py`)

Given the features and the user's goal (Max Compression / Balanced / Max
Quality / Target Size / Target Percentage / Web Optimized), the engine walks
a decision tree and returns:

1. A **skip_reencode** flag - if the source is already a JPEG and the goal is
   Balanced/Web-Optimized, PixelForge does not re-encode the DCT data (which
   would add generational loss); instead it performs a lossless Huffman
   re-optimisation and metadata cleanup.
2. Otherwise, an ordered list of **candidates** (format + parameters), chosen
   by content type:
   - **Has alpha** -> JPEG excluded; AVIF/JPEG XL/WebP/PNG considered, in that
     preference order where each codec is actually available on the machine.
   - **Screenshot/text-heavy** (`screenshot_score` or `text_density` high) ->
     lossless/near-lossless path (PNG or lossless/near-lossless WebP),
     because lossy DCT-based codecs blur small text unacceptably.
   - **Illustration/limited palette** (`illustration_score` high or few
     unique colours) -> palette PNG or lossless WebP.
   - **Line art / black & white** -> palette-optimised PNG.
   - **General photograph** -> AVIF first (when available), then JPEG with a
     goal-appropriate chroma-subsampling and quality, then WebP; JPEG XL at a
     low "distance" is added for the Max Quality goal.
3. Every branch appends a **plain-language reason** describing why that
   choice was made - this is exactly what Automatic Mode shows the user.

Codec availability (`imgcodecs.available_codecs()`) is checked live, so a
machine without the JPEG XL or AVIF plugin installed simply never gets those
candidates offered.

## 3. Benchmarking candidates (`compression/candidates.py`)

Rather than trusting the decision engine's first guess blindly, PixelForge
actually **encodes** the top N candidates (N depends on Fast/Balanced/Deep
Auto mode) and measures, for each:

- Real output file size
- Real encode time
- Real SSIM, a lightweight multi-scale SSIM, and PSNR against the original
  (via `quality/metrics.py`, built on scikit-image)

These are blended into a single `estimated_quality` (0-100) score and then
combined into a **multi-criteria objective**:

```
score = size_weight * (1 - normalized_size)
      + quality_weight * (estimated_quality / 100)
      + time_weight * (1 - normalized_encode_time)
```

The weights themselves depend on the user's goal - Max Compression weighs
size heavily, Max Quality weighs the quality term heavily, Balanced splits
the difference. The candidate with the highest score is selected; for Target
Size / Target Percentage goals, PixelForge instead binary-searches the
quality parameter of a quality-controllable codec (JPEG/WebP/AVIF) to
converge on the requested size (`compression/target_size.py`).

## 4. Quality Guardian (`quality/metrics.py`)

After a winner is chosen, `QualityGuardian.evaluate()` re-computes SSIM and
the blended quality score against the *original* file. If either falls below
the configured thresholds (defaults: SSIM ≥ 0.90, quality ≥ 65), PixelForge
automatically retries with the next-safest already-benchmarked candidate
(up to two retries) rather than silently shipping a degraded result.

## 5. Why this is transparent, not a black box

Every `DecisionResult` carries its `reasons: list[str]`, and every completed
job's `CompressionReport` carries both those reasons and the full list of
benchmarked candidates with their scores. The GUI's Automatic Mode view and
the CLI's `--json` output both expose this, so a user (or an automated CI
pipeline) can always see exactly which alternatives were considered and why
one was preferred.

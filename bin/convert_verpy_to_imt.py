#!/usr/bin/env python3
"""
Convert VerPy output to ImageMetaTag database format.
Supports both layouts:
1) Flat: <job_folder>/*.png
2) Nested: <job_folder>/<subjob_folder>/*.png

Job folder examples:
- 20260304T0000Z_L06_Europe_GPM_6hr
- 20260601T0300Z_L06_UK_ANALYSIS_6hr_ukv
- 20260325T0000Z_L96_UK_ANALYSIS_24hr_gm_agg6d
"""
import os
import re
from pathlib import Path

import ImageMetaTag as imt

# Configuration
VERPY_OUTPUT_DIR = Path("/data/scratch/sebastian.cole/GM_precip_testing/verpy_plots")
WEB_DIR = Path(os.getenv("HOME")) / "public_html" / "precip_verpy_viewer"
DATABASE_FILE = WEB_DIR / "precip_verpy.db"

# Create output directory
WEB_DIR.mkdir(parents=True, exist_ok=True)

# Clear existing database and symlinks
if DATABASE_FILE.exists():
    DATABASE_FILE.unlink()
for f in WEB_DIR.glob("*.png"):
    f.unlink()

FOLDER_PATTERN = re.compile(
    r'^(?P<valid_date>\d{8}T\d{4}Z)_L(?P<lead_time>\d+)_'
    r'(?P<area>[A-Za-z0-9]+)_(?P<truth>[A-Za-z0-9]+)_(?P<accumulation>\d+)hr'
    r'(?:_(?P<model>[A-Za-z0-9]+))?'
    r'(?:_agg(?P<agg_days>\d+)d)?$'
)


def parse_job_from_path(png_path):
    """Find and parse the nearest parent folder that matches VerPy job naming."""
    for parent in png_path.parents:
        if parent == VERPY_OUTPUT_DIR:
            break
        match = FOLDER_PATTERN.match(parent.name)
        if match:
            return parent, match.groupdict()
    return None, None


def derive_stat_type(stat_name):
    """Map VerPy image names to viewer-friendly stat labels."""
    if '_Mean_Anl_' in stat_name or stat_name.endswith('_Mean_Anl'):
        return 'Mean (Truth)'
    if '_Mean_Fc_' in stat_name or stat_name.endswith('_Mean_Fc'):
        return 'Mean (Forecast)'
    if 'Mean_Absolute_Error' in stat_name:
        return 'Mean Absolute Error'
    if 'RMSE' in stat_name:
        return 'RMSE'
    if 'Frequency_Bias' in stat_name:
        return 'Frequency Bias'
    if 'Equitable_Threat_Score' in stat_name:
        return 'Equitable Threat Score'
    if 'Bias' in stat_name or 'ME_' in stat_name:
        return 'Bias'
    return 'Other'


image_count = 0
skipped_no_job = 0

# Scan all PNG files recursively to support flat and nested output layouts.
for png_file in sorted(VERPY_OUTPUT_DIR.rglob("*.png")):
    # Skip IMT-generated thumbnails if present.
    if png_file.name.endswith('_thumb.png'):
        continue

    job_folder, meta = parse_job_from_path(png_file)
    if meta is None:
        skipped_no_job += 1
        continue

    valid_date = meta['valid_date']
    lead_time = meta['lead_time']
    area = meta['area']
    truth = meta['truth']
    accumulation = meta['accumulation']
    model = (meta.get('model') or '').lower()
    agg_days = meta.get('agg_days')

    rel_parent = png_file.parent.relative_to(job_folder)
    subjob = rel_parent.parts[0] if rel_parent.parts else 'root'

    stat_name = png_file.stem
    stat_base = stat_name
    if stat_base.endswith('_GPM'):
        stat_base = stat_base[:-4]
    elif stat_base.endswith('_Anl'):
        stat_base = stat_base[:-4]

    stat_type = derive_stat_type(stat_name)
    thresh_match = re.search(r'_(gt|lt)[0-9.]+mm$', stat_name)
    threshold = thresh_match.group(0).lstrip('_') if thresh_match else ''

    rel_parent_tag = str(rel_parent).replace(os.sep, '__') if rel_parent.parts else 'root'
    symlink_name = f"{job_folder.name}__{rel_parent_tag}__{png_file.name}"
    symlink_path = WEB_DIR / symlink_name

    try:
        if symlink_path.exists() or symlink_path.is_symlink():
            symlink_path.unlink()
        os.symlink(png_file, symlink_path)
    except Exception as e:
        print(f"Could not link {png_file}: {e}")
        continue

    img_tags = {
        "model": model or 'unknown',
        "valid_date": valid_date,
        "lead_time": f"T+{int(lead_time):03d}",
        "area": area,
        "truth": truth,
        "accumulation": f"{accumulation}hr",
        "aggregation": f"agg{agg_days}d" if agg_days else 'none',
        "subjob": subjob,
        "stat_type": stat_type,
        "stat": stat_name,
        "stat_base": stat_base,
        "threshold": threshold,
        "target": str(png_file),
    }

    imt.db.write_img_to_dbfile(DATABASE_FILE, symlink_name, img_tags)
    image_count += 1

print(f"\nConverted {image_count} images to ImageMetaTag database")
print(f"Skipped {skipped_no_job} images (no matching job folder)")
print(f"Database: {DATABASE_FILE}")
print(f"Web dir:  {WEB_DIR}")
print(f"\nNow you can use jp_metatagging2.ipynb with:")
print(f'  image_dir = Path("{VERPY_OUTPUT_DIR}")')
print(f'  web_dir = Path("{WEB_DIR}")')
print(f'  database_file_path = Path("{DATABASE_FILE}")')

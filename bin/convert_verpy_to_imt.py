#!/usr/bin/env python3
"""
Convert VerPy output to ImageMetaTag database format.
Supports both layouts:
1) Flat: <job_folder>/*.png
2) Nested: <job_folder>/<subjob_folder>/*.png

Job folder examples:
- 20260304T0000Z_L06_Europe_GPM_6hr_global
- 20260601T0300Z_L06_UK_ANALYSIS_6hr_ukv
- 20260325T0000Z_L96_UK_ANALYSIS_24hr_global_agg7d
- 20260325T0000Z_L96_UK_MODEL_24hr_psuite47_agg7d
"""
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

import ImageMetaTag as imt

# Configuration
# run_verpy_plotting_agg (the 24hr/aggregated plotting task) shares this same
# output tree with run_verpy_plotting - the "_agg7d" suffix added to the job
# folder name by --aggregated already distinguishes aggregated output from
# per-cycle output (see FOLDER_PATTERN/jid in verpy_plotting_precip_monitoring_agg.py).
VERPY_OUTPUT_DIR = Path("/data/scratch/sebastian.cole/GM_precip_testing/verpy_plots")
WEB_DIR = Path(os.getenv("HOME")) / "public_html" / "psuite48_precip_viewer"
DATABASE_FILE = WEB_DIR / "psuite48_verpy.db"
# Database is rebuilt into this temp file and only swapped into place with an
# atomic os.replace() once fully written - see the end of this script. That
# way a page load/refresh that happens mid-run always sees either the
# complete old database or the complete new one, never a missing/partial one.
TMP_DATABASE_FILE = DATABASE_FILE.with_suffix(DATABASE_FILE.suffix + ".tmp")

# housekeep deliberately keeps every plot ever generated (see the housekeep
# app's rose-app.conf / flow.cylc comment) for archival purposes, so
# VERPY_OUTPUT_DIR only ever grows. Without a cutoff here, the live webpage's
# selector tree (and its per-chunk JSON files) grows unboundedly along with
# it - it reached ~150k images/~7GB of JSON before the browser simply
# couldn't load it any more. This only limits what the *live* viewer shows;
# older plots are untouched on disk and can still be browsed by pointing the
# jp_metatagging2.ipynb notebook (see the printed instructions below) at
# VERPY_OUTPUT_DIR directly.
#
# The cutoff is anchored to the most recent valid_date actually found in
# VERPY_OUTPUT_DIR (computed below, once job folders have been enumerated),
# not to wall-clock "now" - the workflow can be paused or fall behind, and if
# that happens a wall-clock cutoff would make the viewer show nothing at all
# instead of its most recent available data.
RETENTION_DAYS = 4

# Create output directory
WEB_DIR.mkdir(parents=True, exist_ok=True)

# Clean up a stray temp database left behind by a previously interrupted run.
if TMP_DATABASE_FILE.exists():
    TMP_DATABASE_FILE.unlink()

# "model" is a single flat identifier ("ukv", "global" or "psuite47") set by
# model_id in verpy_plotting_precip_monitoring_agg.py - a psuite trial
# replaces "global" entirely rather than being a separate tag, since psuite
# comparisons are only ever run against the global model, never ukv.
FOLDER_PATTERN = re.compile(
    r'^(?P<valid_date>\d{8}T\d{4}Z)_L(?P<lead_time>\d+)_'
    r'(?P<area>[A-Za-z0-9]+)_(?P<truth>[A-Za-z0-9]+)_(?P<accumulation>\d+)hr'
    r'_(?P<model>[A-Za-z0-9]+)'
    r'(?:_agg(?P<agg_days>\d+)d)?$'
)

# A subjob folder is now named purely from the worded score by score_jobid()
# in verpy_plotting_precip_monitoring_agg.py (e.g. "mean_forecast"), so the
# folder name itself is the authoritative score identifier - no need to guess
# it from the rendered plot filename text.

# Viewer-friendly labels for each VerPy score slug used by the plotting
# script. "Mean (Truth)" must stay exactly this string - create_imt_webpage.py
# matches on it to decide which image goes on the right of a side-by-side
# comparison.
STAT_LABELS = {
    'mean_forecast': 'Mean (Forecast)',
    'mean_analysis': 'Mean (Truth)',
    'mean_error_forecast_analysis': 'Bias',
    'mean_absolute_error_forecast_analysis': 'Mean Absolute Error',
    'equitable_threat_score': 'Equitable Threat Score',
    'frequency_bias_category_1': 'Frequency Bias',
    'frequency_of_observations_category_1': 'Frequency of Observations'
}

# Viewer-friendly labels for the "model" tag shown in the Model dropdown.
# This only affects what's displayed/selected on the webpage - the
# underlying value (used for symlink names, FOLDER_PATTERN parsing, MOOSE
# paths/model_id in verpy_plotting_precip_monitoring_agg.py, etc.) stays as
# the raw "psuite48" everywhere else.
MODEL_LABELS = {
    'psuite48': 'global psuite48',
}


def iter_candidate_job_folders(root):
    """Yield (job_folder, meta_dict) for every job folder in root, without
    doing a full recursive walk to find them. Yields (None, None) once for
    each top-level entry that can't be resolved to any job folder, so callers
    can tally unrecognized folders.

    VERPY_OUTPUT_DIR can contain tens of thousands of historical job folders
    (housekeep deliberately never prunes plots - see RETENTION_DAYS comment
    above), so finding job folders this way - rather than rglob-ing every PNG
    under the whole tree and walking back up from each one - matters both for
    keeping the live viewer bounded and for finishing within
    update_imt_viewer's execution time limit.

    Supports: job folders directly under root (legacy), job folders nested
    one level down under a <source> subdirectory (e.g. opfc/, psuite48/), and
    (skipped) even older job folders that predate the "model" field in
    FOLDER_PATTERN and so don't match at all - a top-level entry is only
    treated as a <source> subdirectory worth descending into if at least one
    of its own children looks like a job folder; otherwise it's left alone
    entirely rather than mistaking its internal subjob folders (e.g.
    "thumbnail", "ctc_6901") for job folders one level down.
    """
    for entry in sorted(root.iterdir()):
        if not entry.is_dir():
            continue
        match = FOLDER_PATTERN.match(entry.name)
        if match:
            yield entry, match.groupdict()
            continue
        children = [c for c in sorted(entry.iterdir()) if c.is_dir()]
        if not any(FOLDER_PATTERN.match(c.name) for c in children):
            yield None, None
            continue
        for sub_entry in children:
            sub_match = FOLDER_PATTERN.match(sub_entry.name)
            if sub_match:
                yield sub_entry, sub_match.groupdict()
            else:
                yield None, None


def derive_stat_type(subjob):
    """Map a VerPy subjob/jobid (e.g. 'mean_forecast') to a viewer-friendly
    stat label."""
    return STAT_LABELS.get(subjob, 'Other')


image_count = 0
skipped_no_job = 0
skipped_old = 0
links_created = 0
links_unchanged = 0
desired_symlinks = set()

# First pass (cheap - directory names only, no PNG scanning) to find every
# job folder and the most recent valid_date actually present.
all_entries = list(iter_candidate_job_folders(VERPY_OUTPUT_DIR))
job_entries = [(f, m) for f, m in all_entries if f is not None]
skipped_no_job = len(all_entries) - len(job_entries)

parsed_dates = {
    f: datetime.strptime(m['valid_date'], '%Y%m%dT%H%MZ').replace(tzinfo=timezone.utc)
    for f, m in job_entries
}
latest_valid_date = max(parsed_dates.values()) if parsed_dates else datetime.now(timezone.utc)
RETENTION_CUTOFF = latest_valid_date - timedelta(days=RETENTION_DAYS)

# write_img_to_dbfile() opens a brand new sqlite connection and commits+closes
# it on every single call - fine occasionally, but with tens of thousands of
# images that overhead alone was measured at ~15ms/call (e.g. ~18 minutes for
# ~71k images - comfortably over update_imt_viewer's own execution time
# limit). Opening the connection once via open_or_create_db_file(), writing
# every row through the same open cursor with write_img_to_open_db(), and
# committing only once at the end avoids that overhead entirely (the same
# 71k writes measured well under a few seconds this way).
_DB_SCHEMA_SAMPLE = {
    "model": "", "valid_date": "", "lead_time": "", "area": "", "truth": "",
    "accumulation": "", "aggregation": "", "subjob": "", "stat_type": "",
    "stat": "", "stat_base": "", "threshold": "", "target": "",
}
db_conn, db_cursor = imt.db.open_or_create_db_file(TMP_DATABASE_FILE, _DB_SCHEMA_SAMPLE, restart_db=True)

for job_folder, meta in job_entries:
    valid_date = meta['valid_date']
    lead_time = meta['lead_time']
    area = meta['area']
    truth = meta['truth']
    accumulation = meta['accumulation']
    # "model" is now a single flat value: "ukv", "global", or "psuite47"
    # (psuite trials replace "global" entirely - see FOLDER_PATTERN comment).
    model = (meta.get('model') or 'unknown').lower()
    agg_days = meta.get('agg_days')

    # Exclude anything older than RETENTION_CUTOFF from the live viewer (see
    # the comment on RETENTION_DAYS above) - the underlying plots are left
    # alone on disk either way. Checked once per job folder (not per image)
    # so out-of-window folders are never even rglob-ed.
    if parsed_dates[job_folder] < RETENTION_CUTOFF:
        skipped_old += 1
        continue

    # Scan all PNGs under this job folder to support both flat
    # (<job_folder>/*.png) and nested (<job_folder>/<subjob_folder>/*.png)
    # layouts.
    for png_file in sorted(job_folder.rglob("*.png")):
        # Skip IMT-generated thumbnails if present.
        if png_file.name.endswith('_thumb.png'):
            continue

        rel_parent = png_file.parent.relative_to(job_folder)
        subjob = rel_parent.parts[0] if rel_parent.parts else 'root'

        stat_name = png_file.stem
        stat_base = stat_name
        if stat_base.endswith('_GPM'):
            stat_base = stat_base[:-4]
        elif stat_base.endswith('_Anl'):
            stat_base = stat_base[:-4]

        stat_type = derive_stat_type(subjob)
        thresh_match = re.search(r'_(gt|lt)[0-9.]+mm$', stat_name)
        threshold = thresh_match.group(0).lstrip('_') if thresh_match else ''

        rel_parent_tag = str(rel_parent).replace(os.sep, '__') if rel_parent.parts else 'root'
        symlink_name = f"{model}__{job_folder.name}__{rel_parent_tag}__{png_file.name}"
        symlink_path = WEB_DIR / symlink_name
        desired_symlinks.add(symlink_name)

        try:
            # Symlink names are deterministic from the job folder/stat, so an
            # existing link pointing at the right target is already correct
            # and left untouched - only create/replace it if missing or
            # stale. This means pages already loaded in a browser keep
            # working against the same images throughout this run, instead
            # of seeing them vanish and reappear.
            if symlink_path.is_symlink() and os.readlink(symlink_path) == str(png_file):
                links_unchanged += 1
            else:
                if symlink_path.exists() or symlink_path.is_symlink():
                    symlink_path.unlink()
                os.symlink(png_file, symlink_path)
                links_created += 1
        except Exception as e:
            print(f"Could not link {png_file}: {e}")
            continue

        img_tags = {
            "model": MODEL_LABELS.get(model, model),
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

        imt.db.write_img_to_open_db(db_cursor, symlink_name, img_tags)
        image_count += 1

# Commit all writes and close the connection before the atomic swap below.
db_conn.commit()
db_conn.close()

# Atomically swap the freshly built database into place. os.replace() is
# atomic on the same filesystem, so a concurrent read of DATABASE_FILE always
# sees either the complete old database or the complete new one.
os.replace(TMP_DATABASE_FILE, DATABASE_FILE)

# Only now remove symlinks that are no longer wanted (e.g. their source job
# folder has been housekept away) - doing this last means no valid image
# a visitor might currently be viewing is ever removed before its (identical)
# replacement is already in place.
stale_links = 0
for f in WEB_DIR.glob("*.png"):
    if f.name not in desired_symlinks:
        f.unlink()
        stale_links += 1

print(f"\nConverted {image_count} images to ImageMetaTag database")
print(f"Latest valid_date found: {latest_valid_date.isoformat()} (retention cutoff: {RETENTION_CUTOFF.isoformat()})")
print(f"Skipped {skipped_no_job} unrecognized folders, {skipped_old} job folders older than {RETENTION_DAYS} days")
print(f"Symlinks: {links_created} created/updated, {links_unchanged} unchanged, {stale_links} stale removed")
print(f"Database: {DATABASE_FILE}")
print(f"Web dir:  {WEB_DIR}")
print(f"\nNow you can use jp_metatagging2.ipynb with:")
print(f'  image_dir = Path("{VERPY_OUTPUT_DIR}")')
print(f'  web_dir = Path("{WEB_DIR}")')
print(f'  database_file_path = Path("{DATABASE_FILE}")')

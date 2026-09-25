#!/usr/bin/env python3
"""
Create ImageMetaTag webpage from VerPy output.

Prerequisites:
- Run convert_verpy_to_imt.py first to create the database and symlinks
- module load scitools

Usage:
    python create_imt_webpage.py
"""
import os
import datetime
from pathlib import Path

import ImageMetaTag as imt

# Configuration
WEB_DIR = Path(os.getenv("HOME")) / "public_html" / "precip_verpy_viewer"
DATABASE_FILE = WEB_DIR / "precip_verpy.db"
PROJECT_NAME = "precip_verpy_viewer"

# Define selectors matching the database keys from convert_verpy_to_imt.py
# For multi-image: stat_type on left (selectable), Mean Truth always on right
SELECTORS = {
    "model": "Model",
    "aggregation": "Aggregation",
    "valid_date": "Valid Date",
    "lead_time": "Lead Time",
    "area": "Area",
    "truth": "Truth",
    "accumulation": "Accumulation",
    "subjob": "Plot Group",
    "threshold": "Threshold",
    "stat_type": "Statistic",  # Left panel selector (Mean Forecast, MAE, etc.)
}


def build_image_dict(img_tags_dict, selectors, selector_animated, animation_direction=+1):
    """Build an ImageDict from the database tags."""
    selector_keys = list(selectors.keys())
    selector_level_names = list(selectors.values())
    
    print(f"Selector column names: {selector_keys}")
    print(f"Animated selector: {selector_keys[selector_animated]}")

    img_dict = None
    for img_file, img_info in img_tags_dict.items():
        tmp_dict = imt.dict_heirachy_from_list(img_info, img_file, selector_keys)
        if not img_dict:
            img_dict = imt.ImageDict(
                tmp_dict,
                selector_animated=selector_animated,
                animation_direction=animation_direction,
                level_names=selector_level_names,
            )
        else:
            img_dict.append(imt.ImageDict(tmp_dict))
    return img_dict


def build_multi_image_dict(img_dict, db_img_tags, selectors):
    """
    Build multi-image ImageDict for side-by-side comparison.
    Left: Selected stat (Mean Forecast, MAE, etc.)
    Right: Mean Truth (always)
    """
    tagorder = list(selectors.keys())
    stat_type_idx = tagorder.index('stat_type')
    
    # Create new ImageDict for multi images
    img_dict_multi = img_dict.copy_except_dict_and_keys()
    img_dict_multi.dict = {}
    
    pair_count = 0

    # Find all non-Mean-Truth images and pair with corresponding Mean Truth
    for img_file, img_info in db_img_tags.items():
        stat_type = img_info.get('stat_type', '')
        
        # Skip Mean Truth images - they go on the right
        if stat_type == 'Mean (Truth)':
            continue
        
        # Build lookup keys for left (this stat) and right (Mean Truth)
        key_lookup_left = [img_info.get(x, '') for x in tagorder]
        key_lookup_right = key_lookup_left.copy()
        key_lookup_right[stat_type_idx] = 'Mean (Truth)'
        
        left_img = img_dict.return_from_list(key_lookup_left)
        right_img = img_dict.return_from_list(key_lookup_right)
        
        # Only add if both images exist
        if left_img is not None and right_img is not None:
            images = [left_img, right_img]
            tmp_dict = imt.dict_heirachy_from_list(img_info, images, tagorder)
            img_dict_multi.append(imt.ImageDict(tmp_dict))
            pair_count += 1

    print(f"Built {pair_count} side-by-side pairs")
    
    return img_dict_multi


def get_html_header_and_footer():
    """Generate header and footer HTML for the webpage."""
    time_now = datetime.datetime.now()

    webpage_header = '''
    <div style="
        width: 100%;
        background: #111;
        color: #fff;
        font-weight: bold;
        font-size: 2.0em;
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding:16px 24px;
        box-sizing: border-box;
        min-height: 48px;
        margin-bottom: 20px
    ">
        <span>Precipitation Verification Viewer</span>
        <img src='https://www.metoffice.gov.uk//webfiles/1755514254711/images/logos/mo-green-white.svg' alt='Met Office Logo' style="height:32px; margin-left:24px;">
    </div>
    '''

    webpage_footer = f'''
    <div id='postamble' style='margin: 20px 5px'>
        <p>Webpage generated at: {time_now.strftime('%Y-%m-%d %H:%M:%S')} by Image-Meta-Tag</p>
    </div>
    '''

    return webpage_header, webpage_footer


def main():
    # Check database exists
    if not DATABASE_FILE.exists():
        print(f"ERROR: Database not found at {DATABASE_FILE}")
        print("Run convert_verpy_to_imt.py first to create the database")
        return 1

    print(f"Using database: {DATABASE_FILE}")
    print(f"Web directory: {WEB_DIR}")

    # Read the database
    imt_db = imt.db.read(DATABASE_FILE)
    img_file_paths = imt_db[0]
    img_tags_dict = imt_db[1]

    if img_file_paths is not None:
        print(f"Database loaded with {len(img_file_paths)} images.")
    else:
        print("ERROR: Database loaded with 0 images")
        return 1

    # Build single ImageDict first (needed for lookups)
    selector_animated = list(SELECTORS.keys()).index("lead_time")
    img_dict = build_image_dict(img_tags_dict, SELECTORS, selector_animated)
    
    # Build multi-image dict: Left = stat, Right = Mean Truth
    img_dict_multi = build_multi_image_dict(img_dict, img_tags_dict, SELECTORS)
    n_multi = len(img_dict_multi.dict)
    print(f"Created {n_multi} multi-image comparison groups")

    # Fallback to single-image mode when there are no valid side-by-side pairs.
    if n_multi == 0:
        print("No Mean (Truth) pairs found; using single-image viewer mode.")
        img_dict_multi = img_dict

    # Generate webpage
    out_page = WEB_DIR / f"{PROJECT_NAME}.html"
    webpage_header, webpage_footer = get_html_header_and_footer()

    imt.webpage.write_full_page(
        img_dict_multi,
        out_page,
        PROJECT_NAME,
        preamble=webpage_header,
        postamble=webpage_footer,
        last_img_in_list_is_slider=False,  # No slider
        last_img_still_show=True,          # Show right image
        postamble_no_imt_link=True,
        show_selector_names=True,
        verbose=False,
        only_show_rel_url=True,
        write_intmed_tmpfile=True,
        show_singleton_selectors=True,
    )

    print(f"\nWebpage created: {out_page}")
    print(f"View at: https://wwwspice/~{os.getenv('USER')}/precip_verpy_viewer/{PROJECT_NAME}.html")
    return 0


if __name__ == "__main__":
    exit(main())

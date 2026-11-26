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
import re
from pathlib import Path

import ImageMetaTag as imt

# Configuration
WEB_DIR = Path(os.getenv("HOME")) / "public_html" / "psuite48_precip_viewer"
DATABASE_FILE = WEB_DIR / "psuite48_verpy.db"
PROJECT_NAME = "psuite48_precip_viewer"

# Define selectors matching the database keys from convert_verpy_to_imt.py
# For multi-image: stat_type on left (selectable), Mean Truth always on right
SELECTORS = {
    "model": "Model",  # "ukv", "global", "global psuite48", etc. - see MODEL_LABELS in convert_verpy_to_imt.py
    "aggregation": "Aggregation",
    "valid_date": "Valid Date",
    "lead_time": "Lead Time",
    "area": "Area",
    "truth": "Truth",
    "accumulation": "Accumulation",
    "threshold": "Threshold",
    "stat_type": "Statistic",  # Left panel selector (Mean Forecast, MAE, etc.)
}


def _insert_path(root, path_dict):
    """Cheaply merge a single-leaf nested dict (as returned by
    imt.dict_heirachy_from_list) into root in place.

    ImageDict.append() does a full recursive merge of the *entire* existing
    tree on every call (plus a full key re-list), so calling it once per
    image in a loop of tens of thousands of images is O(n^2) and can take
    hours. This only walks the single path being inserted - O(depth) per
    call - so building up the whole structure this way and constructing one
    ImageDict at the end is O(n) overall instead.
    """
    key, value = next(iter(path_dict.items()))
    if isinstance(value, dict):
        _insert_path(root.setdefault(key, {}), value)
    else:
        root[key] = value


def build_image_dict(img_tags_dict, selectors, selector_animated, animation_direction=+1):
    """Build an ImageDict from the database tags."""
    selector_keys = list(selectors.keys())
    selector_level_names = list(selectors.values())
    
    print(f"Selector column names: {selector_keys}")
    print(f"Animated selector: {selector_keys[selector_animated]}")

    merged = {}
    for img_file, img_info in img_tags_dict.items():
        tmp_dict = imt.dict_heirachy_from_list(img_info, img_file, selector_keys)
        if tmp_dict:
            _insert_path(merged, tmp_dict)

    return imt.ImageDict(
        merged,
        selector_animated=selector_animated,
        animation_direction=animation_direction,
        level_names=selector_level_names,
    )


def build_multi_image_dict(img_dict, db_img_tags, selectors):
    """
    Build multi-image ImageDict for side-by-side comparison.
    Left: Selected stat (Mean Forecast, MAE, etc.)
    Right: Mean Truth (always)
    """
    tagorder = list(selectors.keys())
    stat_type_idx = tagorder.index('stat_type')
    threshold_idx = tagorder.index('threshold')
    
    pair_count = 0
    merged = {}

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
        # Mean (Truth) images never have a threshold, even when pairing
        # against a threshold-based stat (e.g. CTC scores like Equitable
        # Threat Score/Frequency Bias) - without resetting this, the lookup
        # would only ever match a Mean (Truth) image at that same threshold,
        # which doesn't exist, so these stats would never find a pair.
        key_lookup_right[threshold_idx] = ''
        
        left_img = img_dict.return_from_list(key_lookup_left)
        right_img = img_dict.return_from_list(key_lookup_right)
        
        # Only add if both images exist
        if left_img is not None and right_img is not None:
            images = [left_img, right_img]
            tmp_dict = imt.dict_heirachy_from_list(img_info, images, tagorder)
            if tmp_dict:
                _insert_path(merged, tmp_dict)
                pair_count += 1

    print(f"Built {pair_count} side-by-side pairs")

    img_dict_multi = img_dict.copy_except_dict_and_keys()
    img_dict_multi.dict = merged
    img_dict_multi.list_keys_by_depth()
    
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


def add_animation_keep_depth(html_content, keep_depth):
    """Make animation retain the selectors through keep_depth."""
    html_content = re.sub(
        r"(?m)^[ \t]*// when animating, keep selectors through the configured depth.*\n",
        "",
        html_content,
    )
    html_content = re.sub(
        r"(?m)^[ \t]*var anim_keep_depth = [^;\n]+;\n?",
        "",
        html_content,
    )
    animation_direction = re.compile(
        r"(?m)^(?P<indent>[ \t]*)var anim_dir = (?P<direction>[^;\n]+);"
    )
    match = animation_direction.search(html_content)
    if match is None:
        raise RuntimeError("Could not find anim_dir in the generated ImageMetaTag page")

    insertion = (
        f"{match.group(0)}\n"
        f"{match.group('indent')}// when animating, keep selectors through the configured depth if possible:\n"
        f"{match.group('indent')}var anim_keep_depth = {keep_depth};"
    )
    return html_content[:match.start()] + insertion + html_content[match.end():]


def _javascript_function_end(source, signature):
    """Return the end offset of a JavaScript function with the given signature."""
    start = source.find(signature)
    if start < 0:
        raise RuntimeError(f"Could not find {signature!r} in generated ImageMetaTag JavaScript")

    opening_brace = source.find("{", start)
    if opening_brace < 0:
        raise RuntimeError(f"Could not find the opening brace for {signature!r}")

    depth = 0
    for index in range(opening_brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return start, index + 1

    raise RuntimeError(f"Could not find the closing brace for {signature!r}")


def add_animation_keep_behaviour(javascript):
    """Patch the ImageMetaTag animator to skip values that reset retained selectors."""
    helper_signature = "function anim_option_keeps_selection(anim_id, keep_depth)"
    if helper_signature in javascript:
        start, end = _javascript_function_end(javascript, helper_signature)
        javascript = javascript[:start].rstrip() + "\n" + javascript[end:].lstrip()

    step_signature = "function step_selected_id(incr)"
    start, end = _javascript_function_end(javascript, step_signature)
    replacement = """function step_selected_id(incr){
    // function to step through to the next selected_id
    var current_ind = anim_options.indexOf(selected_id[anim_sel]);
    var new_ind = current_ind + incr;
    if (new_ind < 0){
        new_ind = anim_options.length -1;
    } else if (new_ind >= anim_options.length){
        new_ind = 0;
    }
    // Prefer the nearest option that does not reset selectors below the animator.
    if (typeof anim_keep_depth !== 'undefined' && anim_keep_depth > anim_sel){
        for (var i_ind = current_ind + incr; i_ind >= 0 && i_ind < anim_options.length; i_ind += incr){
            if (anim_option_keeps_selection(anim_options[i_ind], anim_keep_depth)){
                new_ind = i_ind;
                break;
            }
        }
    }
    selected_id[anim_sel] = anim_options[new_ind];
}
function anim_option_keeps_selection(anim_id, keep_depth){
    // Is the current selection valid through keep_depth for this animator value?
    var imt_subset = imt;
    for (var i_d=0; i_d <= keep_depth && i_d < n_deep; i_d++){
        var key = key_lists[i_d][(i_d == anim_sel) ? anim_id : selected_id[i_d]];
        if (typeof imt_subset !== 'object' || !Object.prototype.hasOwnProperty.call(imt_subset, key)){
            return false;
        }
        imt_subset = imt_subset[key];
    }
    return true;
}"""
    return javascript[:start] + replacement + javascript[end:]


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

    # Generate webpage to a temp file first, then atomically swap it into
    # place. write_full_page() can take a little while for a large image
    # dict, and writing straight to the live filename would leave anyone
    # loading the page mid-write with a truncated/invalid page; os.replace()
    # is atomic on the same filesystem, so visitors always see either the
    # old complete page or the new complete page, never a partial one.
    out_page = WEB_DIR / f"{PROJECT_NAME}.html"
    tmp_page = out_page.with_suffix(out_page.suffix + ".tmp")
    # Clean up a stray temp page left behind by a previously interrupted run,
    # so it can't be mistaken for a fresh in-progress write.
    if tmp_page.exists():
        tmp_page.unlink()
    webpage_header, webpage_footer = get_html_header_and_footer()

    imt.webpage.write_full_page(
        img_dict_multi,
        tmp_page,
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
    animation_keep_depth = list(SELECTORS).index("accumulation")
    html_content = add_animation_keep_depth(tmp_page.read_text(), animation_keep_depth)

    dropdown_file = WEB_DIR / "imt_dropdown.js"
    dropdown_content = add_animation_keep_behaviour(dropdown_file.read_text())

    # write_full_page() embeds the literal filename it was given (tmp_page's
    # name, including ".tmp") into the page's own "link to this page"
    # permalink text, since it doesn't know we're about to rename the file.
    # Patch that one reference back to the real filename before the swap, so
    # the permalink it shows visitors is actually valid afterwards.
    html_content = html_content.replace(tmp_page.name, out_page.name)
    tmp_page.write_text(html_content)

    tmp_dropdown_file = dropdown_file.with_suffix(dropdown_file.suffix + ".tmp")
    if tmp_dropdown_file.exists():
        tmp_dropdown_file.unlink()
    tmp_dropdown_file.write_text(dropdown_content)
    os.replace(tmp_dropdown_file, dropdown_file)
    os.replace(tmp_page, out_page)

    print(f"\nWebpage created: {out_page}")
    print(f"View at: https://wwwspice/~{os.getenv('USER')}/{WEB_DIR.name}/{PROJECT_NAME}.html")
    return 0


if __name__ == "__main__":
    exit(main())

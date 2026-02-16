import sys
sys.path.append('/home/users/clare.bysouth/frcb/VERSUS/r4416_749_METNetCDF')
import cartopy.crs as ccrs
import VerPy
from VerPy.datafiles import metmaps
from VerPy.html import create_simple_subjob_viewer
from VerPy import parameter
from VerPy import errormap
from VerPy import stats
import os
import argparse
import numpy as np 

metmaps.MET_TRUTHS['ANALYSIS'] = 'Analysis'
metmaps.MET_TRUTHS['OBS'] = 'Analysis'
metmaps.MET_TRUTHS['GPM'] = 'Analysis'

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--vdate', required=True, help='Valid date in format YYYYMMDDTHHMM (e.g., 20250123T0000Z)')
    parser.add_argument('--met-source', required=True, help='Path to MET source directory')
    parser.add_argument('--outdir', required=True, help='Output directory for plots')
    parser.add_argument('--fcrs', required=True, help='Forecast lead times as start,stop,step (e.g., 6,60,6)')  # Changed to single string
    parser.add_argument('--truth-type', required=True, help='Type of truth data to use (e.g., gpm)')
    parser.add_argument('--accumulation', required=True, help='Accumulation period for precipitation (eg 24)')
    args = parser.parse_args()
    return args

stats.derived.EVENT_THRESHOLD = 1

args = parse_args()
vdate = args.vdate
met_source = args.met_source
lead_seq = args.fcrs  # This is now a string like "6,60,6"
outdir = args.outdir
truth_type = args.truth_type.upper()  # Convert to uppercase
accumulation = args.accumulation

# Create output directory if it doesn't exist
os.makedirs(outdir, exist_ok=True)
print(f'Output directory: {outdir}')

start, stop, step = map(int, lead_seq.split(','))
fcrs = [str(x).zfill(2) for x in range(start, stop + step, step)]  # Format with leading zeros

sources = [os.path.join(met_source, vdate, f'SERIES_ANALYSIS_OUTPUT_AGAINST_{truth_type}_{accumulation}hr_V{vdate}_L{x}.nc') for x in fcrs]
print(f'this is sources {sources}')

stats_to_plot = ['053']

## Create stat codes depending on truth type
if truth_type == 'GPM':
    verpy_class='6'
    truth_key=0
elif truth_type == 'ANALYSIS':
    verpy_class='6'
    truth_key=0

stats = [int(verpy_class + stat) for stat in stats_to_plot]
# Add additional stats that are always included
# stats.extend([1051, 2051])
# print(f'this is stats {stats}')

for s in sources:
    if not os.path.exists(s):
        print(f"WARNING: File not found, skipping: {s}")
        continue  # Skip to next file instead of raising error

    for area in ['global']:
        # Extract the forecast lead time from the filename (e.g., 'L48' -> '48')
        fcr = os.path.basename(s).split('_L')[-1].replace('.nc', '')
        # Structure jobid so VerPy can extract metadata
        jid = f'{vdate}_L{fcr}_{area}_{truth_type}_{accumulation}hr'
        options = {
            'jobid': str(jid),
            'metadata': 'example_viewer',
            'param':(77, 129, int(accumulation)),
            'type': 'sl1l2',
            'stats': stats,
            'source': s,
            'system': 'MET',
            'names': truth_type,
            'truth': truth_key,
            'output': 'errormap',
            'vrange': [0, 0.5, 1, 2, 5, 10, 15],
            'mapopts': [area]}  #
        VerPy.job.run(outdir, options, verbose=False)

# Create viewer after ALL plots are generated
print(f"Creating viewer in {outdir}")
unwanted_menus = ['plot type']
create_simple_subjob_viewer(outdir, 'example_viewer', remove_keys=unwanted_menus)

### for ctc metrics add for t in thresh: and thresh as t, {t.replace(">", "gt") to jid 
#    
# for t in thresh:
#     varying_options = [{
#         'thresh': t,
#         'title': '%p, %h, %s, %d Threshold: ' + str(t),}]
#     for opts in varying_options:
#         opts.update(common_options)
#     VerPy.job.run('.', opts)


# options = {
#         'jobid': 'PS47_plots/mibg'+trial_id+'/non_event_fbias' + str(fname),
#         'type': 'ctc',
#         'thresh': '>0',
#         'stats': 7905,
#         'source': [metfile],
#         'expid': ['UKV'],
#         'system': 'MET',
#         'output': 'errormap',
#         'names': ['UKV'],
#         'mapopts': ['!autoscale',
#                     [48, -11, 60, 3, ccrs.AzimuthalEquidistant(central_longitude=-2.5, central_latitude=54.9)]],
#         #'plotopts': ['landscape', '2x1'],
#         'vrange': [0, 0.25, 0.75, 1.25, 2, 5],
#         'plottheme': 'viridis:5',
#         'title': '%p, %h, %s, %d' + ' ' + str(fname)}
#     #     'compare_in_fig': 'cases'}
# VerPy.job.run('.', options),


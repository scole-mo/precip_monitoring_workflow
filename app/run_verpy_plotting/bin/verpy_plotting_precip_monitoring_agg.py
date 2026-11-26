import sys
#sys.path.append('/home/users/clare.bysouth/frcb/VERSUS/r4416_749_METNetCDF')
sys.path.append('~clare.bysouth/VERSUS/Seb/verpy')
import cartopy.crs as ccrs
import VerPy
from VerPy.datafiles import metmaps
from VerPy.html import create_simple_subjob_viewer
from VerPy import parameter
from VerPy import errormap
from VerPy import stats
from VerPy.parameter import get_parameter
import matplotlib
import os
import re
import argparse
import numpy as np
import glob
from matplotlib.colors import ListedColormap, to_hex
from VerPy import plottheme
import datetime

### Mapping of MET truth types to VerPy truth keys ###
metmaps.MET_TRUTHS['ANALYSIS'] = 'Analysis'
metmaps.MET_TRUTHS['OBS'] = 'Analysis'
metmaps.MET_TRUTHS['GPM'] = 'Analysis'
metmaps.MET_TRUTHS['MVM'] = 'Analysis'
metmaps.MET_TRUTHS['MO_GLOBAL_OPFC'] = 'Analysis'

### Mapping of area names to VerPy map options ###
MAPOPTS_AREAS = {
'Global': 'global',
'Europe': 'eu',
'UK': 'uk'
}

### Mapping MET stat codes to VerPy parameter short names ###
ppn = get_parameter(codes = (77, 129, 6.))
ppn['short'].append('precipitation')

### Create a factory function to generate area callbacks for VerPy jobs ###
def make_add_area(area_name):
    '''Factory function that returns a callback with the area name bound'''
    def add_area(case, case_num):
        case.data.expand_dims('areas', area_name)
    return add_area

### Build a stable, filesystem/IMT-safe job id for a single VerPy stat code ###
def score_jobid(stat_code):
    '''Uses VerPy's own stat registry (the same source it uses for titles)
    so each score gets its own unambiguous output folder, instead of relying
    on downstream tools to guess the score from rendered plot filenames.'''
    name = stats.get_statistic(stat_code).full
    # Replace any run of non-alphanumeric characters (spaces, parentheses,
    # hyphens, etc.) with a single underscore, e.g. "Mean (Forecast)" ->
    # "mean_forecast", so the name is safe to use as a directory name.
    return re.sub(r'[^A-Za-z0-9]+', '_', name).strip('_').lower()

### Funtion to parse command line arguments ###
def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument('--vdate', required=True, help='Valid date in format YYYYMMDDTHHMM (e.g., 20250123T0000Z)')
    parser.add_argument('--met-source', required=True, help='Path to MET source directory')
    parser.add_argument('--outdir', required=True, help='Output directory for plots')
    parser.add_argument('--fcrs', required=True, help='Forecast lead times as start,stop,step (e.g., 6,60,6)')
    parser.add_argument('--truth-type', required=True, help='Type of truth data to use (e.g., gpm)')
    parser.add_argument('--accumulation', required=True, help='Accumulation period for precipitation (eg 24)')
    parser.add_argument('--aggregated', action='store_true', help='Use aggregated file naming convention')
    parser.add_argument('--start-vdate', required=False, help='Start valid date for aggregation period (e.g., 20260319T0000Z)')
    parser.add_argument('--model', required=False, default='', help='Model name (e.g., ukv). If ukv, only UK area is plotted.')
    parser.add_argument('--psuite-id', required=False, default='', help='Parallel suite identifier (e.g. psuite47), if plotting psuite output')
    args = parser.parse_args()
    return args

### RRead in arguments and set up variables ###
args = parse_args()
vdate = args.vdate
met_source = args.met_source
lead_seq = args.fcrs  # This is now a string like "6,60,6"
outdir = args.outdir
truth_type = args.truth_type.upper()  # Convert to uppercase
accumulation = args.accumulation
aggregated = args.aggregated
start_vdate = args.start_vdate
model = args.model.lower() if args.model else ''
psuite_id = args.psuite_id
if psuite_id == 'opfc':  # sentinel <source> value for normal ops (no psuite/trial)
    psuite_id = ''

# Single flat "model" identifier used for plot folder naming and the
# webpage's Model selector (e.g. "ukv", "global", "psuite47"). psuite_id is
# checked first since "model" is always explicitly set to "global" or "ukv"
# by every runtime block (never blank), so it would otherwise always win and
# psuite_id would never be used. A psuite trial replaces "global" entirely
# rather than being a separate axis, since psuite comparisons are only ever
# run against the global model, never ukv.
model_id = psuite_id or model or 'global'

# For plot folder naming only (not the actual truth-data lookup, which still
# uses the real truth_type below): mvm compares a psuite's own forecast
# against the opfc baseline model, rather than against a real observed/
# analysed truth, so label it "MODEL" instead of "MVM" to make clear the
# "truth" here is itself another model's forecast.
jid_truth = 'MODEL' if truth_type == 'MVM' else truth_type

# mvm (model-vs-model) compares a psuite against the opfc baseline - comparing
# opfc to itself is meaningless, and there is no MET output to plot for it
# (see run_code.sh), so skip immediately.
if truth_type == 'MVM' and not psuite_id:
    print('Skipping mvm plotting: source is opfc, nothing to compare it to.')
    sys.exit(0)

# Use a looser threshold for single-time runs to avoid all-NaN CTC maps.
stats.derived.EVENT_THRESHOLD = 1 if aggregated else 0
print(f'Using EVENT_THRESHOLD={stats.derived.EVENT_THRESHOLD} (aggregated={aggregated})')

# Create output directory if it doesn't exist
os.makedirs(outdir, exist_ok=True)
print(f'Output directory: {outdir}')

# Clean up any corrupted subjobinfo files from previous failed runs
for corrupt_file in glob.glob(os.path.join(outdir, '**', '.subjobinfo'), recursive=True):
    try:
        with open(corrupt_file, 'r') as f:
            import ast
            ast.literal_eval(f.read())
    except (SyntaxError, ValueError):
        print(f"Removing corrupted file: {corrupt_file}")
        os.remove(corrupt_file)

start, stop, step = map(int, lead_seq.split(','))
fcrs = [str(x).zfill(2) for x in range(start, stop + step, step)]  # Format with leading zeros

if aggregated:
    if not start_vdate:
        sys.exit('ERROR: --start-vdate is required when using --aggregated')
    sources = [os.path.join(met_source, vdate, f'SERIES_ANALYSIS_OUTPUT_AGAINST_{truth_type}_{accumulation}hr_AGGREGATED_V{start_vdate}_V{vdate}_L{x}.nc') for x in fcrs]
else:
    sources = [os.path.join(met_source, vdate, f'SERIES_ANALYSIS_OUTPUT_AGAINST_{truth_type}_{accumulation}hr_V{vdate}_L{x}.nc') for x in fcrs]
print(f'this is sources {sources}')

# stats_to_plot = ['053']

# Create stat codes depending on truth type
if truth_type == 'GPM':
    verpy_class='6'
    truth_key=0
elif truth_type == 'ANALYSIS':
    verpy_class='6'
    truth_key=0
elif truth_type == 'MVM':
    verpy_class='6'
    truth_key=0

# if accumulation == '6':
#     accum_period=0.
# elif accumulation == '24':
#     accum_period=24.

# stats = [int(verpy_class + stat) for stat in stats_to_plot]
# ###Add additional stats that are always included
# stats.extend([1051, 2051])
# print(f'this is stats {stats}')

######## Create radar colour theme for 1051/2051 (9 bins) ######
colors_1051_2051 = ['#FFFFFF', '#79b2e9', '#5193d4', '#2868bd', '#1fc91b', '#fff03a', '#ff9b00', '#ec321b', '#ff5dfb', '#7b0acc']
bounds_1051_2051 = [0.0, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 32, 64]
radar_cmap_1051_2051 = ListedColormap(colors_1051_2051, N=len(colors_1051_2051))
radar_theme = plottheme.get_theme('default')
radar_theme['palette']['mapstyle']['cmap'] = radar_cmap_1051_2051

######## Create radar colour theme for 6053 (7 bins) ######
# colors_6053 = [ '#FFFFFF', '#79b2e9', '#2868bd', '#1fc91b', '#fff03a', '#ff9b00', '#ec321b']
bounds_6053 = [0, 0.5, 1, 2, 5, 10, 20, 50]

# radar_cmap_6053 = make_step_cmap('radar_6053', colors_6053)

# radar_theme_6053 = plottheme.PlotThemeDict(
#     name='radar_precip_6053',
#     palette=plottheme.get_palette('default'),
#     legend=True,
#     functions=[],
# )

# radar_theme_6053['palette']['mapstyle'] = {
#     'cmap': radar_cmap_6053,
#     'centre': False
# }

bounds_6905 = [0, 0.1, 0.25, 0.75, 1.25, 1.75, 2, 5]
bounds_6051 = [-10, -5, -2, -1, 0, 1, 2, 5, 10]
bounds_6901 = [-0.34, -0.1, 0, 0.2, 0.4, 0.6, 0.8, 1.0]
bounds_6933 = list(np.arange(0, 1.1, 0.1))

######## Create diffmap colour theme with a white band around zero ######
diffmap = plottheme.get_theme('diffmap')
diff_n_bins = len(bounds_6051) - 1
diff_base_cmap = matplotlib.colormaps['bwr']
diff_colours = [to_hex(diff_base_cmap(i / (diff_n_bins - 1))) for i in range(diff_n_bins)]
# Whiten the bins either side of zero so small/no bias shows as a clear white band
zero_idx = bounds_6051.index(0)
diff_colours[zero_idx - 1] = '#FFFFFF'
diff_colours[zero_idx] = '#FFFFFF'
diffmap['palette']['mapstyle']['cmap'] = ListedColormap(diff_colours, N=len(diff_colours))

######### Creating 1D score plot theme ############

# Generate colours from a matplotlib colormap (7 colours for 7 bins)
cmap = matplotlib.colormaps['copper']
mae_colours = [to_hex(cmap(i / 6)) for i in range(7)]

mae_theme = plottheme.PlotThemeDict(
    name='mae_1d',
    palette=plottheme.get_palette('default'),
    legend=True,
    functions=[],
)

mae_theme['palette'].update({
    'colours': mae_colours,
    'markers': ['o'] * len(mae_colours),
    'linestyles': ['-'] * len(mae_colours),
    'linewidths': [2.0] * len(mae_colours),
    'markersize': [4] * len(mae_colours),
})

if aggregated:
    dt_start = datetime.datetime.strptime(start_vdate, '%Y%m%dT%H%MZ')
    dt_end = datetime.datetime.strptime(vdate, '%Y%m%dT%H%MZ')
    # VALID_START is set (in flow.cylc) to DAYS_OF_AGG - 1 days before the
    # cycle point, so that the window inclusively covers DAYS_OF_AGG
    # calendar days (e.g. 6 days back + today = 7 days of data for a 7-day
    # aggregation). (dt_end - dt_start).days is therefore DAYS_OF_AGG - 1,
    # not DAYS_OF_AGG itself - add 1 so the label matches the actual number
    # of days of data included, rather than the raw timestamp delta.
    agg_suffix = f'_agg{(dt_end - dt_start).days + 1}d'
else:
    agg_suffix = ''

acc_for_ukv_rot_pol = ['!autoscale',
                    [48, -11, 60, 3, ccrs.AzimuthalEquidistant(central_longitude=-2.5, central_latitude=54.9)]]

areas = ['UK'] if model == 'ukv' else ['Global', 'Europe', 'UK']

job_args = [
    (s, area)
    for s in sources if os.path.exists(s)
    for area in areas
]
for s in sources:
    if not os.path.exists(s):
        print(f'WARNING: File not found, skipping: {s}')

print(f'Running {len(job_args)} VerPy jobs sequentially')
for s, area in job_args:
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print("{} Start of job...".format(now))
    fcr = os.path.basename(s).split('_L')[-1].replace('.nc', '')
    area_safe = str(area).replace(' ', '_')
    jid = f'{vdate}_L{fcr}_{area_safe}_{jid_truth}_{accumulation}hr_{model_id}{agg_suffix}'
    area_callback = make_add_area(area)
    common_options = {
        'jobid': jid,
        'param': ppn,
        # 'start': start_vdate if aggregated else vdate,
        # 'end': vdate,
        'source': s,
        'system': 'MET',
        'names': truth_type,
        'truth': truth_key,
        'output': 'errormap',
    }
    if model == 'ukv':
        common_options['mapopts'] = acc_for_ukv_rot_pol
    elif area:
        common_options['mapopts'] = [MAPOPTS_AREAS[area]]
    varying_options = [
        {#Forecast Mean,
         'stats':[1051],
         'type': 'sl1l2',
         'title': '%p %s %f' + f' Mode:{model}',
         'vrange': bounds_1051_2051,
         'plottheme': radar_theme,
        },
        {#Analysis Means,
         'stats':[2051],
         'type': 'sl1l2',
         'title': '%p %s %f' + f' Truth Type:{truth_type}',
         'vrange': bounds_1051_2051,
         'plottheme': radar_theme,
        },
        {#'Mean Absolute Error (MAE)',
         'stats':[6053],  
         'type': 'sl1l2',
         'vrange': bounds_6053,
         'plottheme': 'RdPu',
         'title': '%p %s %f %e'},
        # {#'RMSE',
        #  'stats':[6752],
        #  'type': 'cnt',
        #  'vrange': bounds_6053,
        #  'plottheme': 'RdPu',
        #  'title': '%p %s %f %e'},
        ]
    if truth_type != 'MVM':
        # MET series_analysis only produces CTC (contingency table) stats
        # against a real truth (gpm/analysis) - mvm output only has SL1L2
        # partial sums, so these would always fail with "No stats found
        # for stat type ctc" if run against an mvm comparison.
        varying_options.extend([
            {## Frequency Bias
             'stats':[6904],
             'type': 'ctc',
             'thresh': ['>0.1', '>1', '>4', '>8', '>16', '>30', '>50', '>75', '>100'],
             'vrange': bounds_6905,
             'title': '%p %s %f %e %h'
            # 'plottheme': mae_theme,
            },
            {# BASER - Frequency of observations 
             'stats':[6933],
             'type': 'ctc',
             'thresh': ['>0.1', '>1', '>4', '>8', '>16', '>30', '>50', '>75', '>100'],
             'title': '%p %s %f %e %h',
             'vrange': bounds_6933,
             'plottheme': 'Blues',
            },
             {# Gilbert Skill Score/ Equitable Threat Score,
             'stats':[6901],
             'type': 'ctc',
             'thresh': ['>0.1', '>1', '>4', '>8', '>16', '>30', '>50', '>75', '>100'],
             'vrange': bounds_6901,
             'title': '%p %s %f %e %h'
            # 'plottheme': mae_theme,
            },
        ])
    if truth_type == 'MVM':
        varying_options.append(
            {# Mean error for model vs model differences only
             'stats':[6051],
             'type': 'sl1l2',
             'vrange': bounds_6051,
             'plottheme': diffmap,
             'title': '%p %w %f' + f' {psuite_id} - {model}',
            }
        )
    else:
        varying_options.append(
            {# Mean error 
             'stats':[6051],
             'type': 'sl1l2',
             'vrange': bounds_6051,
             'plottheme': diffmap,
             'title': '%p %w %f %e',
            }
        )

    print(f'Running job: {jid}')
    run_dir = os.path.join(outdir, jid)
    print(f'Creating run directory: {run_dir}')
    os.makedirs(run_dir, exist_ok=True)
    for opts in varying_options:
        # Run one VerPy job per individual score, so each gets its own jobid
        # (output folder) that unambiguously identifies that score, instead of
        # bundling multiple scores (e.g. 1051 & 2051) under a single jobid.
        # Folders are named purely from the worded score (e.g. "mean_forecast"),
        # relying on VerPy's stat names being distinct from one another.
        for stat_code in opts['stats']:
            single_opts = {**opts, 'stats': [stat_code]}
            jobid = score_jobid(stat_code)
            run_opts = {**common_options, **single_opts, 'jobid': jobid}
            VerPy.job.run(run_dir, run_opts, verbose=False, load_callback=area_callback, create_viewer=False)
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print("{} After VerPy.job.run...".format(now))

def change_stat_name(stat):
    if stat == 'Mean (Analysis)':
        return 'Mean (Truth)'
    return stat

#print(f"Creating viewer in {outdir}")
#unwanted_menus = ['plot type', 'truth']
#reformat = {'stats' : lambda x: change_stat_name(x)}
#create_simple_subjob_viewer(outdir, 'example_viewer', remove_keys=unwanted_menus, reformat=reformat)

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


#!/bin/bash -l
set -x; module load scitools

periods='6 24'

for pe in $periods
do 
python calc_gpm_accumulation.py --datadir $GPM_DATA_DIR  --obs $GPM_OBS_TYPE --accum_period $pe --start_date $START_CYCLE_POINT --end_date $END_CYCLE_POINT

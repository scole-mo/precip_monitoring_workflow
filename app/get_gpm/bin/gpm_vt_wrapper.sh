#!/bin/bash -l

set -x
module load scitools/production-os47-2

export PYTHONPATH=${PYTHONPATH}:${CYLC_SUITE_DEF_PATH}/app/${ROSE_TASK_APP}/bin
echo $PYTHONPATH
echo $ROSE_TASK_APP
echo $CYLC_TASK_NAME

# CYLC_TASK_CYCLE_POINT is the model run (initialisation date/time)
echo $CYLC_TASK_CYCLE_POINT
echo $OUTPUT_DATA
GPM_DATA_DIR="/data/users/gpm_imerg"
GPM_OBS_TYPE="GPM_NRTlate"

# 6-hour accumulation: from (cycle point - 6h) to cycle point
START_ACCUM_PERIOD=$(isodatetime -u $CYLC_TASK_CYCLE_POINT --offset -PT6H --print-format=%Y%m%d%H)
echo $START_ACCUM_PERIOD
END_ACCUM_PERIOD=$CYLC_TASK_CYCLE_POINT

echo "6-hour accumulation: $START_ACCUM_PERIOD to $END_ACCUM_PERIOD"
python ${CYLC_SUITE_DEF_PATH}/app/${ROSE_TASK_APP}/bin/og_calc_gpm_accumulation.py \
    --outdir $OUTPUT_DATA \
    --datadir $GPM_DATA_DIR \
    --obs $GPM_OBS_TYPE \
    --accum_period 6 \
    --start_date $START_ACCUM_PERIOD \
    --end_date $END_ACCUM_PERIOD \
    --cycle_point $CYLC_TASK_CYCLE_POINT

# 24-hour accumulation: from (cycle point - 24h) to cycle point
START_ACCUM_PERIOD=$(isodatetime -u $CYLC_TASK_CYCLE_POINT --offset -PT24H --print-format=%Y%m%d%H)
END_ACCUM_PERIOD=$CYLC_TASK_CYCLE_POINT

echo "24-hour accumulation: $START_ACCUM_PERIOD to $END_ACCUM_PERIOD"
python ${CYLC_SUITE_DEF_PATH}/app/${ROSE_TASK_APP}/bin/og_calc_gpm_accumulation.py \
    --outdir $OUTPUT_DATA \
    --datadir $GPM_DATA_DIR \
    --obs $GPM_OBS_TYPE \
    --accum_period 24 \
    --start_date $START_ACCUM_PERIOD \
    --end_date $END_ACCUM_PERIOD \
    --cycle_point $CYLC_TASK_CYCLE_POINT



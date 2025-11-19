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

# Define maximum lead times (in hours)
lead_6h=72
lead_24h=144

# First run the GPM script for 6-hourly data
echo "Running 6-hourly GPM accumulation..."
END_ACCUM_DATE=$(isodatetime -u $CYLC_TASK_CYCLE_POINT --offset PT${lead_6h}H --print-format +%Y%m%d%H)
START_ACCUM_DATE=$(isodatetime -u $CYLC_TASK_CYCLE_POINT --print-format=%Y%m%d%H)
echo $END_ACCUM_DATE

# Loop over all 6-hourly periods within the current forecast window
i=$START_ACCUM_DATE
echo $i

if [ ! -d "${OUTPUT_DATA}/6_hour_gpm" ] ; then
  echo "${OUTPUT_DATA}/6_hour_gpm doesn't currently exist. Making..."
  mkdir -p ${OUTPUT_DATA}/6_hour_gpm
fi

while test "$i" -le $END_ACCUM_DATE ; do
    echo "Processing date: $i ..."
    START_ACCUM_PERIOD=$i
    END_ACCUM_PERIOD=$(isodatetime -u $i --offset PT6H --parse-format=%Y%m%d%H --print-format=%Y%m%d%H)
    echo "$START_ACCUM_PERIOD to $END_ACCUM_PERIOD ..."
    echo ">>> python calc_gpm_accumulation.py --outdir $OUTPUT_DATA/6_hour_gpm --datadir $GPM_DATA_DIR  --obs $GPM_OBS_TYPE --accum_period 6 --start_date $START_ACCUM_PERIOD --end_date $END_ACCUM_PERIOD ..."
    python ${CYLC_SUITE_DEF_PATH}/app/${ROSE_TASK_APP}/bin/calc_gpm_accumulation.py --outdir $OUTPUT_DATA/6_hour_gpm --datadir $GPM_DATA_DIR  --obs $GPM_OBS_TYPE --accum_period 6 --start_date $START_ACCUM_PERIOD --end_date $END_ACCUM_PERIOD
    i=$(isodatetime -u $i --offset PT6H --parse-format=%Y%m%d%H --print-format=%Y%m%d%H)
done


# Now run the GPM script for 24-hourly data
echo "Creating 24-hour GPM accumulations for this model cycle..."
i=$START_ACCUM_DATE
END_ACCUM_DATE=$(isodatetime -u $CYLC_TASK_CYCLE_POINT --offset PT${lead_24h}H --print-format=%Y%m%d%H)

if [ ! -d "${OUTPUT_DATA}/24_hour_gpm" ] ; then
  echo "${OUTPUT_DATA}/24_hour_gpm doesn't currently exist. Making..."
  mkdir -p ${OUTPUT_DATA}/24_hour_gpm
fi

while test "$i" -le $END_ACCUM_DATE ; do
    echo "Processing date: $i"
    START_ACCUM_PERIOD=$i
    END_ACCUM_PERIOD=$(isodatetime -u $i --offset PT24H --parse-format=%Y%m%d%H --print-format=%Y%m%d%H)
    echo "$START_ACCUM_PERIOD to $END_ACCUM_PERIOD ..."
    echo "python calc_gpm_accumulation.py ---outdir $OUTPUT_DATA/24_hour_gpm --datadir $GPM_DATA_DIR  --obs $GPM_OBS_TYPE --accum_period 24 --start_date $START_ACCUM_PERIOD --end_date $END_ACCUM_PERIOD ..."
    python ${CYLC_SUITE_DEF_PATH}/app/${ROSE_TASK_APP}/bin/calc_gpm_accumulation.py --outdir $OUTPUT_DATA/24_hour_gpm --datadir $GPM_DATA_DIR  --obs $GPM_OBS_TYPE --accum_period 24 --start_date $START_ACCUM_PERIOD --end_date $END_ACCUM_PERIOD
    i=$(isodatetime -u $i --offset PT24H --parse-format=%Y%m%d%H --print-format=%Y%m%d%H)
done



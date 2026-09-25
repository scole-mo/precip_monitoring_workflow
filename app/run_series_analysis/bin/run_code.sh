#!/bin/bash -l
#SBATCH --mem=25G
#SBATCH --ntasks=2
#SBATCH --time=280
#SBATCH --export=NONE
set -x
module load scitools
module use /data/users/cfver/METBuild/modules
module load MET_Stable

CONFIG=${CYLC_SUITE_DEF_PATH}/app/${ROSE_TASK_APP}/bin/SeriesAnalysisMETplus_precip_${TRUTH}_valid.ltg

IFS=',' read -r SEQ_START SEQ_END SEQ_STEP <<< "$LEAD_SEQ"
export OMP_NUM_THREADS=1

for ((lead=SEQ_START; lead<=SEQ_END; lead+=SEQ_STEP)); do
    echo "Running SeriesAnalysis for lead $lead"
    LEAD_SEQ="${lead}" OUTPUT_BASE="${OUTPUT_BASE}/valid_${FINAL_CYLCE_POINT}lead_${lead}" run_metplus.py "$CONFIG" &
done
wait
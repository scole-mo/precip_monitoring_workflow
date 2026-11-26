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

# Suite tag mirrors process_analysis.py / process_accumulations.py: "opfc" is the
# sentinel for normal ops (no tag), anything else (e.g. psuite47) gets tagged so
# input filenames match what process_periods/process_analysis produced for that source.
if [[ "$PSUITE_ID" == "opfc" || -z "$PSUITE_ID" ]]; then
    export SUITE_TAG=""
else
    export SUITE_TAG="_${PSUITE_ID}"
fi

# mvm (model-vs-model) compares a psuite against the opfc baseline - comparing
# opfc to itself is meaningless, so skip it immediately.
if [[ "$TRUTH" == "mvm" && -z "$SUITE_TAG" ]]; then
    echo "Skipping mvm comparison: source is opfc, nothing to compare it to."
    exit 0
fi

IFS=',' read -r SEQ_START SEQ_END SEQ_STEP <<< "$LEAD_SEQ"
export OMP_NUM_THREADS=1

for ((lead=SEQ_START; lead<=SEQ_END; lead+=SEQ_STEP)); do
    echo "Running SeriesAnalysis for lead $lead"
    LEAD_SEQ="${lead}" OUTPUT_BASE="${OUTPUT_BASE}/valid_${CYLC_TASK_CYCLE_POINT}${SUITE_TAG}_lead_${lead}" run_metplus.py "$CONFIG" &
done
wait
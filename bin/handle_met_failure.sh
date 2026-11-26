#!/bin/bash
# Handler script for MET task failures
# Parses job stderr/log to find failed init times and triggers upstream tasks
#
# Usage: handle_met_failure.sh WORKFLOW CYCLE_POINT TASK_NAME SUBMIT_NUM
#
# Called by Cylc via:
#   failed handlers = handle_met_failure.sh %(workflow)s %(point)s %(name)s %(submit_num)s

set -x  # Debug: show all commands
exec 2>&1  # Redirect stderr to stdout for logging

WORKFLOW=$1
CYCLE_POINT=$2
TASK_NAME=$3
SUBMIT_NUM=$4

# Log to a fixed location for debugging
DEBUG_LOG="${HOME}/cylc-run/${WORKFLOW}/handler_debug.log"
echo "$(date): Handler started with args: $@" >> "$DEBUG_LOG"

# Construct job log directory path
JOB_LOG_DIR="${HOME}/cylc-run/${WORKFLOW}/log/job/${CYCLE_POINT}/${TASK_NAME}/${SUBMIT_NUM}"

# Extract period from task name (e.g., run_series_analysis_periods24_truthsgpm -> 24)
# Use sed instead of grep -P for better compatibility
PERIOD=$(echo "$TASK_NAME" | sed -n 's/.*periods\([0-9]*\).*/\1/p')

# Log file in job directory
LOG_FILE="${JOB_LOG_DIR}/handler.log"
echo "$(date): Handler triggered for ${TASK_NAME} at ${CYCLE_POINT}" >> "$LOG_FILE" 2>/dev/null
echo "$(date): PERIOD extracted: ${PERIOD}" >> "$DEBUG_LOG"
echo "$(date): JOB_LOG_DIR: ${JOB_LOG_DIR}" >> "$DEBUG_LOG"

# Check job.err for specific failure patterns
JOB_ERR="${JOB_LOG_DIR}/job.err"
JOB_OUT="${JOB_LOG_DIR}/job.out"

echo "$(date): Checking ${JOB_ERR}" >> "$DEBUG_LOG"

# Wait for log files to be retrieved from remote platform (SPICE)
# Log retrieval is async, so we need to wait
MAX_WAIT=60
WAIT_COUNT=0
while [[ ! -f "$JOB_ERR" && $WAIT_COUNT -lt $MAX_WAIT ]]; do
    echo "$(date): Waiting for job.err (attempt $WAIT_COUNT)..." >> "$DEBUG_LOG"
    sleep 5
    WAIT_COUNT=$((WAIT_COUNT + 5))
done

if [[ -f "$JOB_ERR" ]]; then
    echo "$(date): job.err exists" >> "$DEBUG_LOG"
    
    # Check for library/environment errors - don't retry, just log
    if grep -q "cannot open shared object file\|ImportError\|ModuleNotFoundError" "$JOB_ERR"; then
        echo "$(date): Environment/library error detected - not triggering retry" >> "$LOG_FILE" 2>/dev/null
        echo "$(date): Environment error - exiting" >> "$DEBUG_LOG"
        exit 0
    fi
    
    # Check for missing input data errors - parse the I (init) time from filenames
    # Pattern: WARNING: Could not find FCST_INPUT file ...VT...Z_I20260316T0000Z_...
    FAILED_INITS=$(grep -o '_I[0-9]\{8\}T[0-9]\{4\}Z' "$JOB_ERR" 2>/dev/null | sed 's/_I//' | sort -u)
    
    echo "$(date): FAILED_INITS found: ${FAILED_INITS}" >> "$DEBUG_LOG"
    
    if [[ -n "$FAILED_INITS" ]]; then
        echo "$(date): Missing input data - found failed init times" >> "$LOG_FILE" 2>/dev/null
        
        while IFS= read -r init_time; do
            [[ -z "$init_time" ]] && continue
            # init_time is already in format 20260316T0000Z
            echo "$(date): Triggering get_data and process_periods for ${init_time}" >> "$LOG_FILE" 2>/dev/null
            echo "$(date): Running: cylc trigger ${WORKFLOW}//${init_time}/get_data_periods${PERIOD}" >> "$DEBUG_LOG"
            
            cylc trigger "${WORKFLOW}//${init_time}/get_data_periods${PERIOD}" >> "$DEBUG_LOG" 2>&1
            cylc trigger "${WORKFLOW}//${init_time}/process_periods_periods${PERIOD}" >> "$DEBUG_LOG" 2>&1
        done <<< "$FAILED_INITS"
        
        # Re-trigger the failed task itself
        sleep 5
        echo "$(date): Re-triggering ${TASK_NAME}" >> "$DEBUG_LOG"
        cylc trigger "${WORKFLOW}//${CYCLE_POINT}/${TASK_NAME}" >> "$DEBUG_LOG" 2>&1
        exit 0
    fi
else
    echo "$(date): job.err not found at ${JOB_ERR}" >> "$DEBUG_LOG"
fi

# Default: just log the failure
echo "$(date): No recoverable errors found - check logs manually" >> "$DEBUG_LOG"
echo "$(date): No recoverable errors found - check logs manually" >> "$LOG_FILE"
echo "Job stderr: ${JOB_ERR}" >> "$LOG_FILE"

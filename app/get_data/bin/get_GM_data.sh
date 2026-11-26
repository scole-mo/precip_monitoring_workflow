#!/usr/bin/bash -l

fcst_date=$1
datadir=$2
max_lead=$3
accum_period=$4
model=${MODEL:-global}  # Default to global if not set
trial_id=${TRIAL_ID:-}
psuite_id=${PSUITE_ID:-}
# "opfc" is the sentinel <source> value for normal ops (no psuite/trial)
if [[ "$psuite_id" == "opfc" ]]; then
    psuite_id=""
fi

# Remove T and Z if present to normalize date format
fcst_date=${fcst_date//T/}
fcst_date=${fcst_date//Z/}

year=${fcst_date:0:4}
date=${fcst_date:0:8}
hour=${fcst_date:8:2}

# Create formatted version with T and Z for output filenames
save_current_date=${date}T${hour}00Z

echo "year: $year"
echo "date: $date"
echo "hour: $hour"
echo "save_current_date: $save_current_date"
echo "model: $model"
echo "trial_id: $trial_id"
echo "psuite_id: $psuite_id"

# Set model-specific paths and filenames
# If a trial_id/psuite_id is set (via env var), pull from the devfc trial /
# parallel suite archive instead of the normal operational (ops) archive.
if [[ -n "$trial_id" ]]; then
    if [[ "$model" != "global" ]]; then
        echo "ERROR: devfc retrieval currently supports MODEL=global only"
        exit 1
    fi
    mass_path="moose:/devfc/${trial_id}/field.pp/"
    filename_pattern="prods_op_mogreps-g_${date}_${hour}_00_*.pp"
    output_prefix="mogreps-g_${trial_id}"
elif [[ -n "$psuite_id" ]]; then
    if [[ "$model" != "global" ]]; then
        echo "ERROR: psuite retrieval currently supports MODEL=global only"
        exit 1
    fi
    mass_path="moose:/opfc/atm/mogreps-g/prods/${psuite_id}.pp/"
    filename_pattern="prods_op_mogreps-g_${date}_${hour}_00_*.pp"
    output_prefix="mogreps-g_${psuite_id}"
elif [[ "$model" == "ukv" ]]; then
    mass_path="moose:/opfc/atm/ukv/prods/${year}.pp/"
    filename_pattern="prods_op_ukv_${date}_${hour}_*.pp"
    output_prefix="ukv"
else
    # Default to global model
    mass_path="moose:/opfc/atm/global/prods/${year}.pp/"
    filename_pattern="prods_op_gl-mn_${date}_${hour}_*.pp"
    output_prefix="gl-mn"
fi

# Ensure base data directory and output directories exist before any moo select writes.
mkdir -p "${datadir}"
mkdir -p "${datadir}/${accum_period}_hour"
if [[ "$model" == "global" && -z "$trial_id" && -z "$psuite_id" ]]; then
  mkdir -p "${datadir}/6_hour"
fi

### Determine lead times based on forecast hour ###

if [[ "$hour" == "00" || "$hour" == "12" ]]; then
    leads_end=$max_lead
else
    leads_end=$max_lead
fi

## Define times for global update analysis - only 000 and 006 available ##
analysis_runs=("000" "006")

### Get leads ###
# Special case: if hour is 12 and accum_period is 24, use 12, 36, 60... instead of 0, 24, 48...
if [[ "$hour" == "12" && "$accum_period" == "24" ]]; then
    leads_h=""
    for ((i=12; i<=leads_end; i+=accum_period)); do
        leads_h="${leads_h}${i} "
    done
else
    leads_h=""
    for ((i=0; i<=leads_end; i+=accum_period)); do
        leads_h="${leads_h}${i} "
    done
fi
leads_h=$(echo $leads_h)  # Remove trailing space if needed

#################### UPDATE ANALYSES (Global model only) ##########################
## 0 & 6 used here as update analyses are only available at 000 and 006 ##
if [[ "$model" == "global" && -z "$trial_id" && -z "$psuite_id" ]]; then
    mass-pull-analysis () {
      local analysis=$1 
      touch query
      cat >query <<EOF
begin
 filename="prods_op_gl-up_${date}_${hour}_${analysis}.pp"
 stash=(5201,5202,4201,4202)
end
EOF

      /usr/bin/moo select -I query moose:/opfc/atm/global/prods/${year}.pp/ ${datadir}/6_hour/${save_current_date}_gl-up_${analysis}.pp
      rm query
    }

    for analysis in "${analysis_runs[@]}"; do
      mass-pull-analysis "$analysis"
    done
fi

#################### PER ACCUM PERIOD ###########################

mass-pull () {
local outfile="${datadir}/${accum_period}_hour/${save_current_date}_${output_prefix}_T${this_lead}.pp"
local query_filename

# Remove existing file to avoid ERROR_CLIENT_PATH_ALREADY_EXISTS
if [[ -f "$outfile" ]]; then
    echo "Removing existing file: $outfile"
    rm -f "$outfile"
fi

touch query
if [[ "$model" == "ukv" ]]; then
  # UKV archive filenames already encode lead time (e.g. ..._006.pp),
  # so query by filename and stash only - no lbft filter needed.
  query_filename="prods_op_ukv_${date}_${hour}*"
  cat >query <<EOF
  begin
    filename="${query_filename}"
    stash=(4201,4202)
    lbft=${this_lead}
    mind=0
  end
EOF
else
  query_filename="${filename_pattern}"
  cat >query <<EOF
  begin
    filename="${query_filename}"
    stash=(5201,5202,4201,4202)
    lbft=${lead}
  end
EOF
fi

 /usr/bin/moo select -f -I query ${mass_path} ${outfile}

}

# Pull from MASS archive
list_of_files=''

for lead in $leads_h
do
  this_lead=$(printf "%03d" ${lead})
  echo "Processing lead time: ${this_lead}"
  file_to_cat="${datadir}/${accum_period}_hour/${save_current_date}_${output_prefix}_T${this_lead}.pp"
  list_of_files=$(echo ${list_of_files} "${file_to_cat} ")
  mass-pull
  rm query
done


accum=$(printf "%03d" $accum_period)
echo "cat $list_of_files > ${datadir}/${accum_period}_hour/${save_current_date}_${output_prefix}_${accum}.pp"
cat $list_of_files > ${datadir}/${accum_period}_hour/${save_current_date}_${output_prefix}_${accum}.pp


############################## FOR TRIALS #########################################
# trial_name1=$2
# trial_name2=$3
# shortened_trial_name1=$(echo ${trial_name1} | tr -d '-')
# shortened_trial_name2=$(echo ${trial_name2} | tr -d '-')
# /usr/bin/moo select query moose:/devfc/${trial_name1}/field.pp/ ${datadir}/${fcst_date}_${shortened_trial_name1}.pp
# /usr/bin/moo select query moose:/devfc/${trial_name2}/field.pp/ ${datadir}/${fcst_date}_${shortened_trial_name2}.pp

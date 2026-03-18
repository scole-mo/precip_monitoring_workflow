#!/usr/bin/bash -l

input_date=$1
datadir=$2
max_lead=$3
accum_period=$4

x=60

# Adjust accum_period if it's 24
if [[ "$accum_period" == "24" ]]; then
   x=144
fi

# This is offsetting BACKWARD from input_date, then FORWARD by accum_period
# For 6hr at 20250126T0600Z:
#   fcst_date = 20250126T0600Z - 60H = 20250123T1800Z (WRONG!)
#   input_date = 20250126T0600Z + 6H = 20250126T1200Z
# This doesn't make sense for your use case

# BETTER APPROACH: Don't offset input_date forward
fcst_date=$(isodatetime -u $input_date --offset -PT${max_lead}H --print-format=%Y%m%d%H%M)
# Keep input_date as-is (it's already the valid time you want)
# input_date stays as input_date

# Loop from fcst_date to input_date at intervals of accum_period
current_date=$fcst_date
echo "Getting GM data from ${fcst_date} to ${input_date} at ${accum_period}-hour intervals."

while [[ $current_date -le $input_date ]]; do

    year=${current_date:0:4}
    date=${current_date:0:8}
    hour=${current_date:8:2}

    echo "hour: $hour"

    echo isodatetime -u $current_date

    save_current_date=${date}T${hour}00Z
    echo "Save current date is: ${save_current_date}"

    ### Determine lead times based on forecast hour ###

    if [[ "$hour" == "00" || "$hour" == "12" ]]; then
        leads_end=$max_lead
    else
        leads_end=$max_lead
    fi

    ## Define times for global update analysis - only 000 and 006 available ##
    analysis_runs=("000" "006")

    i=0

    if [[ "$accum_period" == "24" && "$hour" == "12" ]]; then
        echo "Accumulation period is 24 and hour is 12, starting leads at 12"
        i=$hour
    fi
    ### Get leads based on accum_period ###
    leads=""
    for ((; i<=leads_end; i+=accum_period)); do
        leads="${leads}${i} "
    done
    leads=$(echo $leads)  # Remove trailing space if needed


    #################### UPDATE ANALYSES ##########################

    mass-pull () {
      local analysis=$1 
      touch query
      cat >query <<EOF
    begin
      filename="prods_op_gl-up_${date}_${hour}_${analysis}.pp"
      stash=(5201,5202,4201,4202)
    end
EOF

      moo select -I query moose:/opfc/atm/global/prods/${year}.pp/ ${datadir}/${accum_period}_hour/${save_current_date}_gl-up_${analysis}.pp
      rm query
    }

    for analysis in "${analysis_runs[@]}"; do
      mass-pull "$analysis"
    done

    #################### Accumulation period ###########################

    mass-pull-accum () {
    touch query
    cat >query <<EOF
      begin
        filename="prods_op_gl-mn_${date}_${hour}_*.pp"
        stash=(5201,5202,4201,4202)
        lbft=${lead}
      end
EOF

    moo select -I query moose:/opfc/atm/global/prods/${year}.pp/ ${datadir}/${accum_period}_hour/${save_current_date}_gl-mn_T${this_lead}.pp
    rm query
    }


    # Pull data from MASS archive
    list_of_files=''

    if [ ! -d "${datadir}/${accum_period}_hour" ] ; then
      echo "${datadir}/${accum_period}_hour doesn't currently exist. Making..."
      mkdir -p ${datadir}/${accum_period}_hour
    fi

    for lead in $leads
    do
      this_lead=$(printf "%03d" ${lead})
      echo "Processing lead time: ${this_lead}"
      file_to_cat="${datadir}/${accum_period}_hour/${save_current_date}_gl-mn_T${this_lead}.pp"
      list_of_files="${list_of_files} ${file_to_cat}"
      mass-pull-accum
    done

    accum=$(printf "%03d" $accum_period)
    echo "Concatenating files: $list_of_files"
    echo "cat $list_of_files > ${datadir}/${accum_period}_hour/${save_current_date}_gl-mn_${accum}.pp"
    cat $list_of_files > ${datadir}/${accum_period}_hour/${save_current_date}_gl-mn_${accum}.pp
    
    if [ $? -ne 0 ]; then
        echo "ERROR: cat command failed"
        echo "Files to concatenate:"
        for f in $list_of_files; do
            if [ -f "$f" ]; then
                echo "  EXISTS: $f ($(stat -c%s $f) bytes)"
            else
                echo "  MISSING: $f"
            fi
        done
        exit 1
    fi

    # Move to next time step
    echo current_date=${current_date}
    current_date=$(isodatetime -u $current_date --parse-format=%Y%m%d%H%M --offset PT${accum_period}H --print-format=%Y%m%d%H%M)
    echo "Next time step: ${current_date}"
    
done


############################## FOR TRIALS #########################################
# trial_name1=$2
# trial_name2=$3
# shortened_trial_name1=$(echo ${trial_name1} | tr -d '-')
# shortened_trial_name2=$(echo ${trial_name2} | tr -d '-')
# moo select query moose:/devfc/${trial_name1}/field.pp/ ${datadir}/${fcst_date}_${shortened_trial_name1}.pp
# moo select query moose:/devfc/${trial_name2}/field.pp/ ${datadir}/${fcst_date}_${shortened_trial_name2}.pp

#!/usr/bin/bash -l

input_date=$1
datadir=$2
max_lead=$3
accum_period=$4

fcst_date=$(isodatetime -u $input_date --offset -PT${max_lead}H --print-format=%Y%m%dT%H%MZ)

# Loop from fcst_date to input_date at intervals of accum_period
current_date=$fcst_date
echo "Getting GM data from ${fcst_date} to ${input_date} at ${accum_period}-hour intervals."

while [[ $(isodatetime -u $current_date --as-total=s) -lt $(isodatetime -u $input_date --as-total=s) ]]; do
    
    year=${current_date:0:4}
    date=${current_date:0:8}
    hour=${current_date:9:2}

    
    year=${current_date:0:4}
    date=${current_date:0:8}
    hour=${current_date:9:2}

    ### Determine lead times based on forecast hour ###

    if [[ "$hour" == "00" || "$hour" == "12" ]]; then
        leads_end='6'
    else
        leads_end='6'
    fi

    ## Define times for global update analysis - only 000 and 006 available ##
    analysis_runs=("000" "006")

    ### Get leads based on accum_period ###
    leads=""
    for ((i=0; i<=leads_end; i+=accum_period)); do
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

      moo select -I query moose:/opfc/atm/global/prods/${year}.pp/ ${datadir}/${accum_period}_hour/${current_date}_gl-up_${analysis}.pp
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

    moo select -I query moose:/opfc/atm/global/prods/${year}.pp/ ${datadir}/${accum_period}_hour/${current_date}_gl-mn_T${this_lead}.pp
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
      echo ${this_lead}
      file_to_cat="${datadir}/${accum_period}_hour/${current_date}_gl-mn_T${this_lead}.pp"
      list_of_files=$(echo ${list_of_files} "${file_to_cat} ")
      mass-pull-accum
    done

    accum=$(printf "%03d" $accum_period)
    echo "cat $list_of_files > ${datadir}/${accum_period}_hour/${current_date}_gl-mn_${accum}.pp"
    cat $list_of_files > ${datadir}/${accum_period}_hour/${current_date}_gl-mn_${accum}.pp

    # Move to next time step
    current_date=$(isodatetime -u $current_date --offset PT${accum_period}H --print-format=%Y%m%dT%H%MZ)
    echo "Next time step: ${current_date}"
    
done


############################## FOR TRIALS #########################################
# trial_name1=$2
# trial_name2=$3
# shortened_trial_name1=$(echo ${trial_name1} | tr -d '-')
# shortened_trial_name2=$(echo ${trial_name2} | tr -d '-')
# moo select query moose:/devfc/${trial_name1}/field.pp/ ${datadir}/${fcst_date}_${shortened_trial_name1}.pp
# moo select query moose:/devfc/${trial_name2}/field.pp/ ${datadir}/${fcst_date}_${shortened_trial_name2}.pp

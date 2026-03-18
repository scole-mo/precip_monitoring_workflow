#!/usr/bin/bash -l

fcst_date=$1
datadir=$2
max_lead=$3
accum_period=$4

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

#################### UPDATE ANALYSES ##########################
## 0 & 6 used here as update analyses are only available at 000 and 006 ##
mass-pull () {
  local analysis=$1 
  touch query
  cat >query <<EOF
begin
 filename="prods_op_gl-up_${date}_${hour}_${analysis}.pp"
 stash=(5201,5202,4201,4202)
end
EOF

  moo select -I query moose:/opfc/atm/global/prods/${year}.pp/ ${datadir}/6_hour/${save_current_date}_gl-up_${analysis}.pp
  rm query
}

for analysis in "${analysis_runs[@]}"; do
  mass-pull "$analysis"
done

#################### PER ACCUM PERIOD ###########################

mass-pull () {
touch query
cat >query <<EOF
  begin
    filename="prods_op_gl-mn_${date}_${hour}_*.pp"
    stash=(5201,5202,4201,4202)
    lbft=${lead}
  end
EOF

moo select -I query moose:/opfc/atm/global/prods/${year}.pp/ ${datadir}/${accum_period}_hour/${save_current_date}_gl-mn_T${this_lead}.pp

}


# Pull from MASS archive
list_of_files=''

if [ ! -d "${datadir}/${accum_period}_hour" ] ; then
  echo "${datadir}/${accum_period}_hour doesn't currently exist. Making..."
  mkdir -p ${datadir}/${accum_period}_hour
fi

for lead in $leads_h
do
  this_lead=$(printf "%03d" ${lead})
  echo "Processing lead time: ${this_lead}"
  file_to_cat="${datadir}/${accum_period}_hour/${save_current_date}_gl-mn_T${this_lead}.pp"
  list_of_files=$(echo ${list_of_files} "${file_to_cat} ")
  mass-pull
  rm query
done


accum=$(printf "%03d" $accum_period)
echo "cat $list_of_files > ${datadir}/${accum_period}_hour/${save_current_date}_gl-mn_${accum}.pp"
cat $list_of_files > ${datadir}/${accum_period}_hour/${save_current_date}_gl-mn_${accum}.pp


############################## FOR TRIALS #########################################
# trial_name1=$2
# trial_name2=$3
# shortened_trial_name1=$(echo ${trial_name1} | tr -d '-')
# shortened_trial_name2=$(echo ${trial_name2} | tr -d '-')
# moo select query moose:/devfc/${trial_name1}/field.pp/ ${datadir}/${fcst_date}_${shortened_trial_name1}.pp
# moo select query moose:/devfc/${trial_name2}/field.pp/ ${datadir}/${fcst_date}_${shortened_trial_name2}.pp

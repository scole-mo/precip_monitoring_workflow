#!/usr/bin/bash -l

input_date=$1
datadir=$2
max_lead=$3
accum_period=$4

##create fcst_date based on max_lead##
fcst_date=$(isodatetime -u $input_date --offset -PT${max_lead}H --print-format=%Y%m%dT%H%MZ)

year=${fcst_date:0:4}
date=${fcst_date:0:8}
hour=${fcst_date:9:2}

## Define times for global update analysis - only 000 and 006 available ##
analysis_runs=("000" "006")

### Get analysis leads ###
leads= accum_period

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

  moo select -I query moose:/opfc/atm/global/prods/${year}.pp/ ${datadir}/6_hour/${fcst_date}_gl-up_${analysis}.pp
  rm query
}

for analysis in "${analysis_runs[@]}"; do
  mass-pull "$analysis"
done

#################### ${accum_period}_hrly ###########################

mass-pull () {
touch query
cat >query <<EOF
  begin
    filename="prods_op_gl-mn_${date}_${hour}_*.pp"
    stash=(5201,5202,4201,4202)
    lbft=${lead}
  end
EOF

moo select -I query moose:/opfc/atm/global/prods/${year}.pp/ ${datadir}/6_hour/${fcst_date}_gl-mn_T${this_lead}.pp

}


# Pull from MASS archive
list_of_files=''

if [ ! -d "${datadir}/${accum_period}_hour" ] ; then
  echo "${datadir}/${accum_period}_hour doesn't currently exist. Making..."
  mkdir -p ${datadir}/${accum_period}_hour
fi

for lead in $leads
do
  this_lead=$(printf "%03d" ${lead})
  echo ${this_lead}
  file_to_cat="${datadir}/${accum_period}_hour/${fcst_date}_gl-mn_T${this_lead}.pp"
  list_of_files=$(echo ${list_of_files} "${file_to_cat} ")
  mass-pull
  rm query
done


accum=$(printf "%03d" $accum_period)
echo "cat $list_of_files > ${datadir}/${accum_period}_hour/${fcst_date}_gl-mn_${accum}.pp"
cat $list_of_files > ${datadir}/${accum_period}_hour/${fcst_date}_gl-mn_${accum}.pp


############################## FOR TRIALS #########################################
# trial_name1=$2
# trial_name2=$3
# shortened_trial_name1=$(echo ${trial_name1} | tr -d '-')
# shortened_trial_name2=$(echo ${trial_name2} | tr -d '-')
# moo select query moose:/devfc/${trial_name1}/field.pp/ ${datadir}/${fcst_date}_${shortened_trial_name1}.pp
# moo select query moose:/devfc/${trial_name2}/field.pp/ ${datadir}/${fcst_date}_${shortened_trial_name2}.pp

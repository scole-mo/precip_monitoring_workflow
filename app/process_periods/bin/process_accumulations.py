#!/usr/bin/env python3

import iris
import logging
import oemplotlib
from oemplotlib.cube_utils import running_accum_to_period, fix_running_cube_time, separate_realization_time
import argparse
from datetime import datetime, timedelta
#iris.FUTURE.save_split_attrs = True

logging.basicConfig()
LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--datetime", required=True)
    parser.add_argument("--datadir", required=True)
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--prep_hours", type=int)
    parser.add_argument("--trial1")
    parser.add_argument("--trial2")
    parser.add_argument("--accum_period", type=int, required=True)
    parser.add_argument("--model", default="global", help="Model type: global or ukv")
    parser.add_argument("--trial_id", default="", help="devfc trial identifier (e.g. mi-bg180), if processing trial output")
    parser.add_argument("--psuite_id", default="", help="Parallel suite identifier (e.g. psuite47), if processing psuite output")
    args = parser.parse_args()
    return args


class Precip_accumulations_large_scale:
    # class level variable
    # large scale rain stash, large scale snow stash
    rainfall_stash = ["m01s04i201", "m01s04i202"]

    def __init__(self, filepath):
        self.filepath = filepath

    def get_cube_accumulations(self, period_hrs):
        cubes = iris.load(self.filepath)

        def _loader(cubelist, stash_constraint):
            try:
                constraint = iris.Constraint(cube_func=lambda cube: cube.cell_methods)
                outcube = cubelist.extract_cube(
                    iris.AttributeConstraint(STASH=stash_constraint) & constraint,
                )
            except iris.exceptions.ConstraintMismatchError as err:
                outcube = cubelist.extract_cube(
                    iris.AttributeConstraint(STASH=stash_constraint)
                )
                msg = ""
                for cube in outcube:
                    msg += f"{cube}\n"
                LOGGER.exception(
                    "error loading for stash %s, found cubes:\n%s",
                    stash_constraint,
                    msg,
                )
                raise err
            return outcube.copy()

        stratiform_rain = _loader(cubes, Precip_accumulations_large_scale.rainfall_stash[0])
        try:
            stratiform_snow = _loader(cubes, Precip_accumulations_large_scale.rainfall_stash[1])
            rainsnow = stratiform_rain + stratiform_snow
        except iris.exceptions.ConstraintMismatchError:
            LOGGER.warning(
                "plot_total_precip_rate couldn't load stratiform snow rates, "
                "plotting will resume assuming this is a startiform rain-only model"
            )
            rainsnow = stratiform_rain

        # first handle ensemble possibly having multidimensional time coordinates
        rainsnow_separated = separate_realization_time(rainsnow)

        if isinstance(rainsnow_separated, iris.cube.CubeList):
            LOGGER.info(f"rainsnow_separated is CubeList with {len(rainsnow_separated)} cubes")
            for i, cube in enumerate(rainsnow_separated):
                LOGGER.info(f"  Cube {i} time: {cube.coord('time')}")
        else:
            LOGGER.info(f"rainsnow_separated time: {rainsnow_separated.coord('time')}")

        # only want hourly output so extract times that are on the hour
        rainsnow_filtered = iris.cube.CubeList()
        if isinstance(rainsnow_separated, iris.cube.CubeList):
            for p in rainsnow_separated:
                try:
                    p = oemplotlib.cube_utils.snap_to_time(
                        p,
                        minutes_past_hour=0,
                        max_window_minutes=5,
                    )
                    rainsnow_filtered.append(p)
                except ValueError:
                    # probably a sub-hourly off hour cube
                    pass
        else:
            rainsnow_filtered.append(
                oemplotlib.cube_utils.snap_to_time(
                    rainsnow_separated,
                    minutes_past_hour=0,
                    max_window_minutes=5,
                )
            )
        if len(rainsnow_filtered) < 1:
            raise ValueError("Unable to separate/snap rainsnow cubes")
        elif len(rainsnow_filtered) == 1:
            rainsnow = rainsnow_filtered[0]
        else:
            rainsnow = rainsnow_filtered.merge()

        LOGGER.info(f"rainsnow time coord: {rainsnow.coord('time')}")
        rainsnow = fix_running_cube_time(rainsnow)

        def _add_cell_methods(cube):
            for method in stratiform_rain.cell_methods:
                if not any(m == method for m in cube.cell_methods):
                    cube.add_cell_method(method)


        if isinstance(rainsnow, iris.cube.CubeList):
            [p.attributes.update(stratiform_rain.attributes) for p in rainsnow]
            # kg m-2 is equivalent to mm as density of water is approx 1000 kg m-3
            [p.convert_units("kg m-2") for p in rainsnow]
            [_add_cell_methods(p) for p in rainsnow]
        else:
            rainsnow.attributes.update(stratiform_rain.attributes)
            rainsnow.convert_units("kg m-2")
            _add_cell_methods(rainsnow)


        LOGGER.info(f"RAINSNOW: {rainsnow}")
        LOGGER.info(f"RAINSNOW coord time: {rainsnow.coord('time')}")
        #LOGGER.info(f"RAINSNOW time points: {rainsnow[0].points}")

        try:
            accum_rain = oemplotlib.cube_utils.running_accum_to_period(
                rainsnow,
                period_minutes=period_hrs * 60,
                out_cube_name=f"Rain Accumulation {period_hrs} hrly",
            )
        except Exception:
            LOGGER.exception(
                "plot_rain_amnt: Error accumulating rain for %s period, skipping",
                period_hrs,
            )
            raise

        return accum_rain




class Precip_accumulations_convective:
    # class level variable
    # convective rain stash, convective snow stash
    rainfall_stash = ["m01s05i201", "m01s05i202"]

    def __init__(self, filepath):
        self.filepath = filepath

    def get_cube_accumulations(self, period_hrs):
            cubes = iris.load(self.filepath)

            def _loader(cubelist, stash_constraint):
                try:
                    constraint = iris.Constraint(cube_func=lambda cube: cube.cell_methods)
                    outcube = cubelist.extract_cube(
                        iris.AttributeConstraint(STASH=stash_constraint) & constraint,
                    ) 
                except iris.exceptions.ConstraintMismatchError as err:
                    outcube = cubelist.extract_cube(
                        iris.AttributeConstraint(STASH=stash_constraint)
                    )
                    msg = ""
                    for cube in outcube:
                        msg += f"{cube}\n"
                    LOGGER.exception(
                        "error loading for stash %s, found cubes:\n%s",
                        stash_constraint,
                        msg,
                    )
                    raise err
                return outcube.copy()

            stratiform_rain = _loader(cubes, Precip_accumulations_convective.rainfall_stash[0])
            try:
                stratiform_snow = _loader(cubes, Precip_accumulations_convective.rainfall_stash[1])
                rainsnow = stratiform_rain + stratiform_snow
            except iris.exceptions.ConstraintMismatchError:
                LOGGER.warning(
                    "plot_total_precip_rate couldn't load stratiform snow rates, "
                    "plotting will resume assuming this is a startiform rain-only model"
                )
                rainsnow = stratiform_rain
            # first handle ensemble possibly having multidimensional time coordinates
            rainsnow_separated = oemplotlib.cube_utils.separate_realization_time(rainsnow)
            # only want hourly output so extract times that are on the hour
            rainsnow_filtered = iris.cube.CubeList()
            if isinstance(rainsnow_separated, iris.cube.CubeList):
                for p in rainsnow_separated:
                    try:
                        p = oemplotlib.cube_utils.snap_to_time(
                            p,
                            minutes_past_hour=0,
                            max_window_minutes=5,
                        )
                        rainsnow_filtered.append(p)
                    except ValueError:
                        # probably a sub-hourly off hour cube
                        pass
            else:
                rainsnow_filtered.append(
                    oemplotlib.cube_utils.snap_to_time(
                        rainsnow_separated,
                        minutes_past_hour=0,
                        max_window_minutes=5,
                    )
                )
            if len(rainsnow_filtered) < 1:
                raise ValueError("Unable to separate/snap rainsnow cubes")
            elif len(rainsnow_filtered) == 1:
                rainsnow = rainsnow_filtered[0]
            else:
                rainsnow = rainsnow_filtered.merge()
                
            rainsnow = fix_running_cube_time(rainsnow)
            if isinstance(rainsnow, iris.cube.CubeList):
                [p.attributes.update(stratiform_rain.attributes) for p in rainsnow]
                # kg m-2 is equivalent to mm as density of water is approx 1000 kg m-3
                [p.convert_units("kg m-2") for p in rainsnow]
                for method in stratiform_rain.cell_methods:
                    [p.add_cell_method(method) for p in rainsnow]
            else:
                rainsnow.attributes.update(stratiform_rain.attributes)
                rainsnow.convert_units("kg m-2")
                for method in stratiform_rain.cell_methods:
                    rainsnow.add_cell_method(method)

            try:
                accum_rain = oemplotlib.cube_utils.running_accum_to_period(
                    rainsnow,
                    period_minutes=period_hrs * 60,
                    out_cube_name=f"Rain Accumulation {period_hrs} hrly",
                )
            except Exception:
                LOGGER.exception(
                    "plot_rain_amnt: Error accumulating rain for %s period, skipping",
                    period_hrs,
                )
                raise

            return accum_rain
    
def get_hrly_total_precip_amnt(
    cubes, large_rain_stash, large_snow_stash, conv_rain_stash, conv_snow_stash
):
    def _loader(cubelist, stash_constraint):
        try:
            constraint = iris.Constraint(cube_func=lambda cube: cube.cell_methods)
            outcube = cubelist.extract_cube(
                iris.AttributeConstraint(STASH=stash_constraint) & constraint,
            )
        except iris.exceptions.ConstraintMismatchError as err:
            outcube = cubelist.extract(iris.AttributeConstraint(STASH=stash_constraint))
            msg = ""
            for cube in outcube:
                msg += f"{cube}\n"
            LOGGER.exception(
                "error loading for stash %s, found cubes:\n%s",
                stash_constraint,
                msg,
            )
            raise err
        return outcube.copy()

    large_rain = _loader(cubes, large_rain_stash)
    large_snow = _loader(cubes, large_snow_stash)

    try:
        conv_rain = _loader(cubes, conv_rain_stash)
        conv_snow = _loader(cubes, conv_snow_stash)
        total_rain = large_rain + conv_rain
        total_snow = large_snow + conv_snow
    except iris.exceptions.ConstraintMismatchError:
        LOGGER.warning(
            "plot_total_precip_rate couldn't load convective precip amounts, "
            "plotting will resume assuming this is a convection permitting model"
        )
        total_rain = large_rain
        total_snow = large_snow

    precip = total_rain + total_snow

    # first handle ensemble possibly having multi-dimensional time coordinates
    precip_separated = oemplotlib.cube_utils.separate_realization_time(precip)

    # only want hourly output so extract times that are on the hour
    precip_filtered = iris.cube.CubeList()
    if isinstance(precip_separated, iris.cube.CubeList):
        for p in precip_separated:
            try:
                p = oemplotlib.cube_utils.snap_to_time(
                    p,
                    minutes_past_hour=0,
                    max_window_minutes=5,
                )
                precip_filtered.append(p)
            except ValueError:
                # probably a sub-hourly off hour cube
                pass
    else:
        precip_filtered.append(
            oemplotlib.cube_utils.snap_to_time(
                precip_separated,
                minutes_past_hour=0,
                max_window_minutes=5,
            )
        )
    if len(precip_filtered) < 1:
        raise ValueError("Unable to separate/snap precip cubes")
    elif len(precip_filtered) == 1:
        precip = precip_filtered[0]
    else:
        precip = precip_filtered.merge()

    precip = oemplotlib.cube_utils.fix_running_cube_time(precip)

    if isinstance(precip, iris.cube.CubeList):
        [p.attributes.update(large_rain.attributes) for p in precip]
        # kg m-2 is equivalent to mm as density of water is approx 1000 kg m-3
        [p.convert_units("kg m-2") for p in precip]
        for method in large_rain.cell_methods:
            [p.add_cell_method(method) for p in precip]
    else:
        precip.attributes.update(large_rain.attributes)
        precip.convert_units("kg m-2")
        for method in large_rain.cell_methods:
            precip.add_cell_method(method)

    return precip



def main():
    args = parse_args()
    dt = args.datetime
    datadir = args.datadir
    output_dir = args.outdir
    prep = args.prep_hours
    accum = args.accum_period
    model = args.model
    trial_id = args.trial_id
    psuite_id = args.psuite_id
    if psuite_id == "opfc":  # sentinel <source> value for normal ops (no psuite/trial)
        psuite_id = ""
    
    # Set file prefix based on model / trial / psuite - mirrors output_prefix in get_GM_data_trial.sh
    if trial_id:
        file_prefix = f"mogreps-g_{trial_id}"
    elif psuite_id:
        file_prefix = f"mogreps-g_{psuite_id}"
    elif model == "ukv":
        file_prefix = "ukv"
    else:
        file_prefix = "gl-mn"
    
    # Tag appended to output filenames so trial/psuite runs don't collide with normal output
    suite_tag = f"_{trial_id}" if trial_id else (f"_{psuite_id}" if psuite_id else "")
    
    LOGGER.info(f" DATETIME: {dt}")
    LOGGER.info(f" DATADIR: {datadir}")
    LOGGER.info(f" OUTDIR: {output_dir}")
    LOGGER.info(f" PREP_HOURS: {prep}")
    LOGGER.info(f" ACCUM_PERIOD: {accum}")
    LOGGER.info(f" MODEL: {model}")
    LOGGER.info(f" TRIAL_ID: {trial_id}")
    LOGGER.info(f" PSUITE_ID: {psuite_id}")
    LOGGER.info(f" FILE_PREFIX: {file_prefix}")

    #accum_periods = [accum]

    ##for accum in accum_periods:
    # Determine which datetimes to process
    if prep and prep > 0:
        # Generate list of datetimes from (dt - prep_hours) to dt at intervals
        end_dt = datetime.strptime(dt, "%Y%m%dT%H%MZ")
        start_dt = end_dt - timedelta(hours=(prep))  # start time is prep hours plus accumulation period before the main datetime
        if model == "ukv" and start_dt.hour % 3 != 0:
            start_dt += timedelta(hours=(3 - (start_dt.hour % 3)))
        datetimes_to_process = []
        current_dt = start_dt
        # UKV cycles every 3 hours; global uses accum_period as step
        step_hours = 3 if model == "ukv" else accum
        while current_dt <= end_dt:
            datetimes_to_process.append(current_dt.strftime("%Y%m%dT%H%MZ"))
            current_dt += timedelta(hours=step_hours)
        LOGGER.info(f"Processing datetimes: {datetimes_to_process}")
    else:
        # Just process the single datetime
        datetimes_to_process = [dt]

    for process_dt in datetimes_to_process:
        LOGGER.info(f"Processing datetime: {process_dt}")
        
        init_time = datetime.strptime(process_dt, "%Y%m%dT%H%MZ")

        # UKV: use same approach as process_analysis.py - difference T-files directly
        if model == "ukv":
            max_lead = 54  # UKV max lead time
            for lead in range(accum, max_lead + 1, accum):
                T_start = f"{datadir}/{accum}_hour/{process_dt}_{file_prefix}_T{lead - accum:03d}.pp"
                T_end = f"{datadir}/{accum}_hour/{process_dt}_{file_prefix}_T{lead:03d}.pp"
                
                LOGGER.info(f"UKV lead T+{lead}: {T_end} - {T_start}")
                
                try:
                    # Load large-scale precip from both files
                    lsr_start = iris.load_cube(T_start, iris.AttributeConstraint(STASH='m01s04i201'))
                    lsr_end = iris.load_cube(T_end, iris.AttributeConstraint(STASH='m01s04i201'))
                    snow_start = iris.load_cube(T_start, iris.AttributeConstraint(STASH='m01s04i202'))
                    snow_end = iris.load_cube(T_end, iris.AttributeConstraint(STASH='m01s04i202'))
                except Exception as e:
                    LOGGER.warning(f"Could not load files for lead T+{lead}: {e}")
                    continue
                
                # Sum rain + snow, take first/last slices (same as process_analysis.py)
                total_start = lsr_start + snow_start
                total_end = lsr_end + snow_end
                
                start_slices = iris.cube.CubeList(total_start.slices_over(["time"]))
                end_slices = iris.cube.CubeList(total_end.slices_over(["time"]))
                
                # First slice of start file, last slice of end file
                LOGGER.info(f"Start slice time: {start_slices[0].coord('time').cell(0).point.strftime('%Y%m%dT%H%MZ')}, End slice time: {end_slices[-1].coord('time').cell(0).point.strftime('%Y%m%dT%H%MZ')}")
                accum_cube = end_slices[-1] - start_slices[0]
                accum_cube.long_name = "precipitation_amount"
                
                # Valid time = init + lead
                valid_time = init_time + timedelta(hours=lead)
                VT = valid_time.strftime("%Y%m%dT%H%MZ")
                accum_cube.attributes['valid_time'] = VT
                
                file_to_save = f"{output_dir}/VT{VT}_I{process_dt}_{accum}hr_accums{suite_tag}.nc"
                LOGGER.info(f"Saving: {file_to_save}")
                iris.save(accum_cube, file_to_save)
                print(f"OUTPUT FILE SAVED: {file_to_save}")
            
            continue  # Skip the global model processing below

        #for accum in accum_periods:

        val = accum 
        file = f"{datadir}/{accum}_hour/{process_dt}_{file_prefix}_{accum:03d}.pp"
        #print(f"This is file_to_read: {filepath}")

        #cubes_to_read = iris.load(filepath)
        #for file in cubes_to_read:
        #print(f" This is file being processed: {file}")
        lsr_precip = Precip_accumulations_large_scale(file)
        print(lsr_precip)
        
        LOGGER.info(f"accumulation period: {accum}. Making accumulations..")
        lsr_accumulations = lsr_precip.get_cube_accumulations(accum)
        
        # UKV is convection-permitting, so no separate convective precip
        if model == "ukv":
            LOGGER.info("UKV model detected - using large-scale precipitation only (convection-permitting model)")
            total_accumulations = lsr_accumulations
        else:
            conv_precip = Precip_accumulations_convective(file)
            print(conv_precip)
            conv_accumulations = conv_precip.get_cube_accumulations(accum)
            total_accumulations = lsr_accumulations + conv_accumulations
        
        total_accumulations.long_name = "precipitation_amount"

        init_time = datetime.strptime(process_dt, "%Y%m%dT%H%MZ")  # adjust format as needed
        lead_hours = accum  # or use your lead time variable
        valid_time = init_time + timedelta(hours=accum)
        print(f"init_time: {init_time}, lead_hours: {lead_hours}, valid_time: {valid_time}")

        total_accumulations.attributes['valid_time'] = valid_time.strftime("%Y%m%dT%H%MZ")

        # ADDED: Diagnostic logging to check time coordinates
        time_coord = total_accumulations.coord('time')
        if time_coord:
            LOGGER.info(f"Time coordinate points: {time_coord.points}")
            LOGGER.info(f"Time coordinate bounds: {time_coord.bounds if time_coord.has_bounds() else 'None'}")


        total_accumulations.long_name = "precipitation_amount"

        init_time = datetime.strptime(process_dt, "%Y%m%dT%H%MZ")  # adjust format as needed
        lead_hours = accum  # or use your lead time variable
        valid_time = init_time + timedelta(hours=accum)
        print(f"init_time: {init_time}, lead_hours: {lead_hours}, valid_time: {valid_time}")

        # REMOVED: Don't set valid_time as global attribute here
        # total_accumulations.attributes['valid_time'] = valid_time.strftime("%Y%m%dT%H%MZ")

        # ADDED: Diagnostic logging to check time coordinates
        time_coord = total_accumulations.coord('time')
        print(f"DEBUG: time_coord exists: {time_coord is not None}")
        if time_coord:
            print(f"DEBUG: Time coordinate shape: {time_coord.shape}")
            print(f"DEBUG: Time coordinate shape[0]: {time_coord.shape[0]}")

        # NEW: Split by time and save each valid time separately (like analysis files)
        print(f"DEBUG: Checking if should split: time_coord={time_coord is not None}, shape[0]={time_coord.shape[0] if time_coord else 'N/A'}")
        if time_coord and time_coord.shape[0] > 1:
            print(f"Splitting cube with {time_coord.shape[0]} time steps into separate files")
            
            # Iterate over each time slice
            for time_slice in total_accumulations.slices_over('time'):
                
                # Extract the valid time for this slice
                slice_time_coord = time_slice.coord('time')
                slice_valid_time = slice_time_coord.units.num2date(slice_time_coord.points[0])
                
                # Convert cftime to datetime for lead calculation
                slice_valid_dt = datetime(slice_valid_time.year, slice_valid_time.month, 
                                          slice_valid_time.day, slice_valid_time.hour,
                                          slice_valid_time.minute, slice_valid_time.second)
                
                # Calculate lead time (valid - init) in hours
                lead_hours = (slice_valid_dt - init_time).total_seconds() / 3600
                
                # Only save files at valid times that fall on an accumulation boundary.
                # For 6hr accums, any valid time that is a multiple of the period relative
                # to the init time is valid, e.g. for 6hr accums from 03Z init: T+6 (09Z),
                # T+12 (15Z), T+18 (21Z), etc.
                # For 24hr accums, valid times must be anchored to 00Z regardless of the
                # init hour, since series analysis aggregates 00Z- and 12Z-initialized
                # forecasts together against common 00Z valid times (e.g. a 12Z init at
                # T+36 is valid at 00Z two days later and must not be skipped).
                if accum == 24:
                    on_boundary = slice_valid_time.hour == 0
                else:
                    on_boundary = lead_hours % accum == 0

                if lead_hours < accum or not on_boundary or slice_valid_time.minute != 0:
                    print(f"Skipping {slice_valid_time} (lead={lead_hours}h) - not on {accum}-hourly lead boundary")
                    continue
                
                #print(f'before squeeze time slice valid_time: {sliced_cube.attributes["valid_time"]}')
                # Remove the time dimension to match analysis file structure
                sliced_cube = iris.util.squeeze(time_slice)
                
                # Set the valid_time attribute for this specific slice
                sliced_cube.attributes['valid_time'] = slice_valid_dt.strftime("%Y%m%dT%H%MZ")
                print(f'after squeeze time slice valid_time: {sliced_cube.attributes["valid_time"]}')
                
                # Generate filename with valid time prefix (like analysis files)
                file_to_save = f"{output_dir}/VT{slice_valid_dt.strftime('%Y%m%dT%H%MZ')}_I{process_dt}_{accum}hr_accums{suite_tag}.nc"
                
                print(f"Saving forecast file: {file_to_save}")
                
                iris.save(sliced_cube, file_to_save)
                print(f"OUTPUT FILE SAVED: {file_to_save}")
                
        else:
            # Single time step - remove time dimension
            LOGGER.info("Single time step detected, removing time dimension")
            squeezed_cube = iris.util.squeeze(total_accumulations)
            
            # Set the valid_time attribute
            squeezed_cube.attributes['valid_time'] = valid_time.strftime("%Y%m%dT%H%MZ")
            
            # Generate filename with valid time prefix
            file_to_save = f"{output_dir}/VT{valid_time.strftime('%Y%m%dT%H%MZ')}_I{process_dt}_{accum}hr_accums{suite_tag}.nc"
            
            LOGGER.info(f"Saving {file_to_save}")
            LOGGER.info(f"Cube shape: {squeezed_cube.shape} (should be 2D: lat, lon)")
            
            iris.save(squeezed_cube, file_to_save)
            print(f"OUTPUT FILE SAVED: {file_to_save}")

        # REMOVED: Old single-file save
        # total_path_to_save = f"{output_dir}/{process_dt}_{accum}hr_accums.nc"
        # lsr_path_to_save = f"{output_dir}/{process_dt}_{accum}hr_lsr_accums.nc"
        # conv_path_to_save = f"{output_dir}/{process_dt}_{accum}hr_conv_accums.nc"
        # iris.save(total_accumulations, total_path_to_save)

        print(f"TOTAL PRECIP: {total_accumulations}")

        #total_path_to_save = f"{output_dir}/{process_dt}_{accum}hr_accums.nc"


        #iris.save(total_accumulations, total_path_to_save)

    
    # TRIAL OPTIONS
    # trial_file1 = f"/<path>/PS47/PS47_thresholdplot_data/{cube_dt}_{trial_name1}.pp"
    # trial_file2 = f"/<path>/PS47/PS47_thresholdplot_data/{cube_dt}_{trial_name2}.pp"


if __name__ == "__main__":
    main()
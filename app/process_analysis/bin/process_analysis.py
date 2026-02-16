#!/usr/bin/env python3

import iris
import logging
import argparse
from datetime import datetime, timedelta
iris.FUTURE.save_split_attrs = True

logging.basicConfig()
LOGGER = logging.getLogger(__name__)
LOGGER.setLevel(logging.INFO)

def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--datetime", required=True)
    parser.add_argument("--datadir", required=True)
    parser.add_argument("--outdir", required=True)
    parser.add_argument("--accum_period", type=int, required=True)
    parser.add_argument("--prep_hours", type=int)
    args = parser.parse_args()
    return args

def check_bounds(timeslice, hour):
    # return a True if bounds are correct for given length of time
    bounds = timeslice.coord("time").bounds[0]
    assert bounds[1] - bounds[0] == hour

def create_total_cube(filepath, precip_type):
    # create cube that combines rain and snow stash from filepath
    if precip_type == "convective":
        STASH = ["m01s05i201", "m01s05i202"]
    elif precip_type == "large_scale":
        STASH = ["m01s04i201", "m01s04i202"]
    else:
        raise ValueError(f"Invalid precip_type: {precip_type}")

    rain = iris.load_cube(filepath, iris.AttributeConstraint(STASH=STASH[0]))
    snow = iris.load_cube(filepath, iris.AttributeConstraint(STASH=STASH[1]))

    total_precip = rain + snow
    total_precip.rename(f"total_{precip_type}_precipitation")

    return total_precip



def main():
    args = parse_args()
    dt = args.datetime
    datadir = args.datadir
    output_dir = args.outdir
    accum_period = args.accum_period
    prep = args.prep_hours
    LOGGER.info(f" DATETIME: {dt}")
    LOGGER.info(f" DATADIR: {datadir}")
    LOGGER.info(f" OUTDIR: {output_dir}")
    LOGGER.info(f" ACCUM_PERIOD: {accum_period}")
    LOGGER.info(f" PREP_HOURS: {prep}")

    # Determine which datetimes to process
    if prep and prep > 0:
        # Generate list of datetimes from (dt - prep_hours) to dt at intervals
        end_dt = datetime.strptime(dt, "%Y%m%dT%H%MZ")
        start_dt = end_dt - timedelta(hours=prep)
        datetimes_to_process = []
        current_dt = start_dt
        while current_dt <= end_dt:
            datetimes_to_process.append(current_dt.strftime("%Y%m%dT%H%MZ"))
            current_dt += timedelta(hours=accum_period)
        LOGGER.info(f"Processing datetimes: {datetimes_to_process}")
    else:
        # Just process the single datetime
        print(f"the format of dt is now {dt}")
        dt =datetime.strptime(dt, "%Y%m%dT%H%MZ")
        print(f"the format of dt is now {dt}")
        dt = dt.strftime("%Y%m%dT%H%MZ")
        print(f"the format of dt is now {dt}")
        datetimes_to_process = [dt]

    for process_dt in datetimes_to_process:
        LOGGER.info(f"Processing datetime: {process_dt}")
        print(f"Processing datetime: {process_dt} for accumulation period: {accum_period} hours")


        LOGGER.info(f"Processing datetime: {process_dt}")
        print(f"Processing datetime: {process_dt} for accumulation period: {accum_period} hours")

        for accum in [accum_period]:
            T0 = f"{datadir}/{accum}_hour/{process_dt}_gl-mn_T000.pp"
            Tn = f"{datadir}/{accum}_hour/{process_dt}_gl-mn_T{accum:03d}.pp"

            # CONVECTIVE ANALYSIS
            conv_cube_t0 = create_total_cube(T0, "convective")
            conv_cube_tn = create_total_cube(Tn, "convective")
            conv_t0_time_slices = iris.cube.CubeList(conv_cube_t0.slices_over(["time"]))
            conv_tn_time_slices = iris.cube.CubeList(conv_cube_tn.slices_over(["time"]))

            assert(len(conv_t0_time_slices) == 1)
            conv_t0_analysis = conv_t0_time_slices[0]
            conv_tn_analysis = conv_tn_time_slices[-1]

            check_bounds(conv_t0_analysis, 3.0)
            check_bounds(conv_tn_analysis, float(accum) + 3.0)
            LOGGER.info(f"Bounds are correct, {accum}hr difference")

            conv_analysis_cube = conv_tn_analysis - conv_t0_analysis
            conv_analysis_cube.rename(f"(t+{accum})-(t+0) conv analysis")
            LOGGER.info(f"conv analysis cube: {conv_analysis_cube}")

            # LARGE SCALE ANALYSIS
            lsr_cube_t0 = create_total_cube(T0, "large_scale")
            lsr_cube_tn = create_total_cube(Tn, "large_scale")
            lsr_t0_time_slices = iris.cube.CubeList(lsr_cube_t0.slices_over(["time"]))
            lsr_tn_time_slices = iris.cube.CubeList(lsr_cube_tn.slices_over(["time"]))

            assert(len(lsr_t0_time_slices) == 1)
            lsr_t0_analysis = lsr_t0_time_slices[0]
            lsr_tn_analysis = lsr_tn_time_slices[-1]

            check_bounds(lsr_t0_analysis, 3.0)
            check_bounds(lsr_tn_analysis, float(accum) + 3.0)
            LOGGER.info(f"Bounds are correct, {accum}hr difference")

            lsr_analysis_cube = lsr_tn_analysis - lsr_t0_analysis
            lsr_analysis_cube.rename(f"(t+{accum})-(t+0) large scale analysis")
            LOGGER.info(f"large scale analysis cube: {lsr_analysis_cube}")

            # analysis VT will be DT+accum
            dt_object = datetime.strptime(process_dt, "%Y%m%dT%H%MZ")
            vt_object = dt_object + timedelta(hours=accum)
            VT = vt_object.strftime("%Y%m%dT%H%MZ")

            # Save paths
            # conv_analysis_path_to_save = f"{output_dir}/{process_dt}_VT{VT}_conv_analysis.nc"
            # lsr_analysis_path_to_save = f"{output_dir}/{process_dt}_VT{VT}_lsr_analysis.nc"

            # Total analysis
            total_analysis = lsr_analysis_cube.copy()
            total_analysis.long_name = "precipitation_amount"
            total_data = lsr_analysis_cube.data + conv_analysis_cube.data
            total_analysis.data = total_data

            total_analysis.attributes['valid_time'] = VT
            total_path_to_save = f"{output_dir}/VT{VT}_analysis_{accum}hr.nc"

            iris.save(total_analysis, total_path_to_save)


if __name__ == "__main__":
    main()
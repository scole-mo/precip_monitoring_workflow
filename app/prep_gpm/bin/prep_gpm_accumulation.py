#!/usr/bin/env python3
import argparse
import datetime
import dateutil.rrule
import os
import sys
import numpy as np
import iris
import iris.cube
import cf_units

def parse_args():
    '''
    Processes and returns command line arguments
    '''
    parser = argparse.ArgumentParser(description='Process forecast precipitation data ready for SEEPS calculation')
    name = parser.prog

    # Required arguments
    parser.add_argument("--datadir", metavar='data_directory',
                        help="Directory containing GPM data")
    parser.add_argument("--obs", type=str,
                        help="Observation type (e.g. GPM, GPM_NRTlate")
    parser.add_argument("-o", "--outdir", default=os.getcwd(),
                        help="Directory to save output cubes (default: $PWD)")
    parser.add_argument("--accum_period", type=int,
                        help="Accumulation period to sum precipitation over (in hours)", 
                        dest='accum_period')
    parser.add_argument("--cutout",
                        nargs="*",
                        type=float,
                        default=None,
                        help=("Coordinates of subregion to cut out in the "
                              "form [min lon, max lon, min lat, max lat]."),
                        dest="cutout")                       
    parser.add_argument("-v", "--verbose", default=0,
                        help="Produce verbose output. Values 0-50")
    parser.add_argument("--cycle_point", 
                        help="Cycle point from workflow")
    parser.add_argument("--max_lead", 
                        type=int,
                        help="Maximum lead time")
    parser.add_argument("-p", "--parallel", action="store_true",
                        help="Enable parallelism")
    parser.add_argument("--cycling_on", type=str,
                        help="Flag to indicate running on VT or DT within cylc")

    # Parse the command line.
    args = parser.parse_args()

    if not args.datadir:
        raise argparse.ArgumentTypeError("Must specify a data source directory.")

    if not args.obs:
        raise argparse.ArgumentTypeError("Must specify an observation type.")

    if not args.cycle_point:
        raise argparse.ArgumentTypeError("Must specify a cycle_point.")

    return args

def insert_datetime(filename, date_time):
    '''
    FUNCTION FROM RMED Toolbox
    Inserts a datetime into a file name containing date formatting characters.

    Arguments:

    * **filename** - the name of a file. If this contains any of the special \
                     date formatting characters

      * %Y - 4-digit year
      * %m - 2-digit month
      * %d - 2-digit day
      * %H - 2-digit hour
      * %M - 2-digit minute

      then these are replaced with numeric values derived from the components \
      of the supplied :class:`datetime.datetime` object.
    * **date_time** - a :class:`datetime.datetime` object specifiying the \
                      datetime to insert in the given filename.

    Returns the input filename with date formatting characters replaced by \
    the appropriate components of date_time.
    '''
    filename = filename.replace("%Y", "{0:04d}".format(date_time.year))
    filename = filename.replace("%m", "{0:02d}".format(date_time.month))
    filename = filename.replace("%d", "{0:02d}".format(date_time.day))
    filename = filename.replace("%H", "{0:02d}".format(date_time.hour))
    filename = filename.replace("%M", "{0:02d}".format(date_time.minute))

    return filename

def _increment_dt(start_datetime, end_datetime, interval):
    '''
    Increment datetime by given time interval (limited to integer hours)
    '''
    date_time = start_datetime
    while date_time <= end_datetime:
        yield min(date_time, end_datetime)
        date_time += datetime.timedelta(hours=interval)

def get_data(start_date, end_date, data_dir, gpm_type, accum_period):
    '''
    Retrieve requested GPM data type from internal MO netCDF-stored files.
    '''
    frequency_in_hours = 0.5
    gpm_frames_per_period = int(accum_period / frequency_in_hours)
    print(gpm_frames_per_period)
    num_periods = (end_date - start_date) // datetime.timedelta(hours=accum_period)
    #num_periods = num_periods.seconds//3600
    print(num_periods)

    # get the first end accumulation date/time
    end_date_0 = start_date + datetime.timedelta(hours=accum_period)
    # generate start and end accumulation datetimes
    start_accumulations = (_increment_dt(start_date, end_date, accum_period) for x in range(num_periods))
    end_accumulations = (_increment_dt(end_date_0, end_date, accum_period) for x in range(num_periods))

    print(gpm_type)
    if gpm_type == 'GPM':
        gpm_type = 'production'
        data_dir = os.path.join(data_dir, "production")
        gpm_filename = f"gpm_imerg_production_V???_%Y%m%d.nc"
    elif gpm_type == 'GPM_NRTlate':
        gpm_type = 'NRTlate'
        data_dir = os.path.join(data_dir, 'NRTlate', "V???")
        gpm_filename = f"gpm_imerg_NRTlate_V???_%Y%m%d.nc"
    else:
        raise NotImplementedError("Can't currently process that category of GPM data: {}".format(gpm_type))

    first_day = start_date.replace(hour=0, minute=0, second=0)
    last_day = end_date.replace(hour=23, minute=59, second=59)

    gpm_cubes = iris.cube.CubeList()
    for this_day in dateutil.rrule.rrule(dateutil.rrule.HOURLY,
                                    interval=24,
                                    dtstart=first_day,
                                    until=last_day):
        this_year = this_day.year
        this_gpm_filename = os.path.join(data_dir, str(this_year), gpm_filename)
        this_gpm_file = insert_datetime(this_gpm_filename, this_day)
        print("Loading {}...".format(this_gpm_file))
        try:
            gpm_cube = iris.load_cube(this_gpm_file)
        except OSError:
            continue
        gpm_cubes.append(gpm_cube)

    # now concatenate cubes together (should only be time axis differing at previous step)
    gpm_cube = gpm_cubes.concatenate_cube()
    print("Accumulating precipitation over required interval, {}-hours, "
          "and date ranges {}-{}...".format(accum_period, start_date, end_date))

    # now accumulate data over desired time ranges
    gpm_acc = iris.cube.CubeList()
    for start_dt, end_dt in zip(next(start_accumulations), next(end_accumulations)):
        # TODO: change this to use bounds at some point
        min_daterange = iris.Constraint(time=lambda cell: cell.bound[0] >= start_dt)
        max_daterange = iris.Constraint(time=lambda cell: cell.bound[1] < end_dt)
        time_limited_gpm_cube = gpm_cube.extract(min_daterange & max_daterange)

        # set values less than zero to missing data
        time_limited_gpm_cube.data[(time_limited_gpm_cube.data < 0)] = np.nan

        # GPM fields are in mm/hr units for each half-hourly field
        gpm_sum = time_limited_gpm_cube.collapsed('time', iris.analysis.SUM) / 2.
        gpm_sum.rename('precipitation amount')
        gpm_sum.units = cf_units.Unit('mm')
        print(gpm_sum)
        gpm_acc.append(gpm_sum)

    print(gpm_acc)
    for cube in gpm_acc:
        print(cube)

    gpm_acc = gpm_acc.merge_cube()
    print(gpm_acc)

    return gpm_acc

def main():
    '''
    Create pseudo-accumulations over requested time period and desired
    sub-area, if supplied.
    '''

    #First, deal with arguments
    args = parse_args()
    out_dir = args.outdir
    acc_period = args.accum_period
    ## Create output directory if it doesn't exist
    period_outdir = os.path.join(out_dir, f"{acc_period}_hour_gpm")
    os.makedirs(period_outdir, exist_ok=True)
    cycling_on = args.cycling_on # flag to indicate running on VT or DT within cycl

    if args.cutout:
        cutout = args.cutout
    else:
        cutout = None
    data_dir = args.datadir
    obstype = args.obs
    cycle_point = datetime.datetime.strptime(args.cycle_point, '%Y%m%dT%H%MZ')
    lead = args.max_lead

    print(f"We are cycling on {cycling_on}")

    if cycling_on == 'DT':
        print("hello from DT")
        START_ACCUM_DATE_DT = cycle_point - datetime.timedelta(hours=lead)
        START_ACCUM_DATE_STR = START_ACCUM_DATE_DT.strftime('%Y%m%d%H') 
        print(f"START_ACCUM_DATE: {START_ACCUM_DATE_STR}")
        END_ACCUM_DATE_DT = cycle_point
        END_ACCUM_DATE_STR = END_ACCUM_DATE_DT.strftime('%Y%m%d%H')
        print(f"END_ACCUM_DATE: {END_ACCUM_DATE_STR}")
        i = START_ACCUM_DATE_DT
    elif cycling_on == 'VT':
        END_ACCUM_DATE_DT = cycle_point
        END_ACCUM_DATE_STR = cycle_point.strftime('%Y%m%d%H')
        print(f"END_ACCUM_DATE: {END_ACCUM_DATE_STR}")
        START_ACCUM_DATE_DT = cycle_point - datetime.timedelta(hours=acc_period)
        START_ACCUM_DATE_STR = START_ACCUM_DATE_DT.strftime('%Y%m%d%H')
        print(f"START_ACCUM_DATE: {START_ACCUM_DATE_STR}")
        i = START_ACCUM_DATE_DT
    else:
        print("Error: cycling_on flag must be set to either VT or DT")
        sys.exit(1)

    while i < END_ACCUM_DATE_DT:

        sdate = i
        edate = i + datetime.timedelta(hours=acc_period)
        print(f"sdate, edate: {sdate, edate}")

        # fetch gpm data and sum over required time period
        gpm_cube = get_data(sdate, edate, data_dir, obstype, acc_period)
        print(gpm_cube)
        print("After fetching data...")

        # extract over subregion, if required
        if cutout:
            print("Trimming data to sub-region {}".format(cutout))
            lons = (cutout[0], cutout[1])
            lats = (cutout[2], cutout[3])
            gpm_cube = gpm_cube.intersection(longitude=lons, latitude=lats)
        else:
            print("No cutout requested. Using global data!")

        # now save cube to netCDF
        for this_time in gpm_cube.slices_over('time'):
            time_coord = this_time.coord('time')
            slice_time = time_coord.units.num2date(time_coord.bounds[-1][-1])
            start_acc_time = time_coord.units.num2date(time_coord.bounds[-1][0]).strftime('%Y%m%d%H')
            end_acc_time = (slice_time + datetime.timedelta(seconds=1)).strftime('%Y%m%d%H')
            print(start_acc_time)
            print(end_acc_time)
            outf = os.path.join(period_outdir,'gpm_{}_{}.nc'.format(start_acc_time, end_acc_time))
            print("Saving to {} ...".format(outf))
            iris.save(this_time, outf, fill_value=np.nan)

        # Move on to next 6h period
        i = i + datetime.timedelta(hours=acc_period)
        print(f"onto next i.. {i}")

if __name__ == "__main__":
    #iris.FUTURE.save_split_attrs = True
    main()

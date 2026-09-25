# Precipitation Monitoring Workflow - Applications Guide

## Overview
This workflow orchestrates precipitation data retrieval, processing, verification, and visualization for global precipitation forecasts against GPM satellite observations and analysis fields.

---

## Applications

### 1. `prep_prev_fcsts`
**Purpose:** Prepare historical forecast data for backfilling and initialization

**Location:** `app/prep_prev_fcsts/`

**Key Script:** Shell script to retrieve/link previous forecast runs

**Inputs:**
- `DATADIR`: Source directory for forecast data
- `START_CYCLE_POINT`: Workflow start date
- `ACCUM_PERIOD`: Accumulation period (6 or 24 hours)
- `MAX_LEAD`: Maximum lead time to process (set dynamically: 60hr for 6hr, 144hr for 24hr)

**Outputs:**
- Copies/links forecast PP files to working directory for specified period range

**When it runs:** Once at first 00Z and 12Z cycle (R1/T00, R1/T12)

---

### 2. `prep_gpm` / `get_gpm`
**Purpose:** Retrieve and process GPM satellite precipitation observations

**Location:** `app/prep_gpm/`

**Key Scripts:** Python scripts for GPM data retrieval and NetCDF conversion

**Inputs:**
- `GPM_DATA_DIR`: Source directory for GPM observations
- `GPM_OBS_TYPE`: Type of GPM product
- `OUTPUT_DATA`: Processed output directory
- `ACCUM_PERIOD`: Accumulation period
- `CYCLING_ON`: Mode flag (PREP for initialization, CYCLING_ON for regular runs)

**Outputs:**
- Processed GPM accumulation NetCDF files at specified valid times

**When it runs:** 
- `prep_gpm`: Initial data prep (R1/T00, R1/T12)
- `get_gpm`: Every cycle (PT6H for 6hr, T00/T12 for 24hr)

---

### 3. `get_data`
**Purpose:** Retrieve model forecast data from archive

**Location:** `app/get_data/`

**Key Script:** Shell script with MASS retrieval commands

**Inputs:**
- `DATADIR`: Target directory for forecast data
- `ACCUM_PERIOD`: Accumulation period
- `CYLC_TASK_CYCLE_POINT`: Current cycle point

**Outputs:**
- Forecast PP files (e.g., `YYYYMMDDTHHMM_gl-mn_024.pp`)

**When it runs:** Every cycle (PT6H for 6hr, T00/T12 for 24hr)

---

### 4. `process_analysis`
**Purpose:** Process model analysis fields as verification truth

**Location:** `app/process_analysis/`

**Key Script:** `bin/process_accumulations.py`

**Inputs:**
- `DATADIR`: Source directory with analysis PP files
- `OUTPUT_DIR`: Processed output directory
- `ACCUM_PERIOD`: Accumulation period

**Process:**
1. Loads large-scale and convective precipitation from STASH codes
2. Separates realization/time coordinates for ensembles
3. Snaps to hourly times
4. Converts running accumulations to period accumulations
5. Sums large-scale + convective for total precipitation

**Outputs:**
- NetCDF files: `VT{valid_time}_analysis_{accum}hr.nc`

**When it runs:** Every cycle (PT6H for 6hr, T00 only for 24hr)

---

### 5. `process_periods` / `process_periods_with_prep`
**Purpose:** Process forecast precipitation accumulations

**Location:** `app/process_periods/`

**Key Script:** `bin/process_accumulations.py`

**Inputs:**
- `DATADIR`: Source directory with forecast PP files
- `OUTPUT_DIR`: Processed output directory  
- `ACCUM_PERIOD`: Accumulation period
- `PREP_HOURS`: (with_prep variant) Hours of historical data to process

**Process:**
- Same as `process_analysis` but processes forecast fields
- `with_prep` variant: loops through multiple initialization times when `PREP_HOURS` set
- Handles both large-scale (m01s04i201/202) and convective (m01s05i201/202) precipitation

**Outputs:**
- NetCDF files: `{init_time}_{accum}hr_accums.nc`

**When it runs:** 
- `process_periods`: Every cycle
- `process_periods_with_prep`: R1/T00 and R1/T12 with historical processing

---

### 6. `run_series_analysis`
**Purpose:** Run METplus Series-Analysis for verification statistics

**Location:** `app/run_series_analysis/`

**Key Files:**
- `bin/SeriesAnalysisMETplus_precip_*.ltg`: METplus configuration templates
- `bin/run_metplus_series_analysis.sh`: Wrapper script

**Inputs:**
- `ACCUM_DATA_DIR`: Directory with processed accumulation files
- `MET_OUTPUT_DIR`: Output directory for MET statistics
- `TRUTH`: Verification truth type (gpm or analysis)
- `LEAD_SEQ`: Lead times to process (format: start,stop,step)
- `ACCUM_PERIOD`: Accumulation period

**Process:**
1. Configures METplus Series-Analysis tool
2. Compares forecast vs. observations/analysis
3. Computes continuous statistics (RMSE, MAE, bias, correlation)
4. Aggregates statistics across spatial domains

**Outputs:**
- NetCDF files: `SERIES_ANALYSIS_OUTPUT_AGAINST_{TRUTH}_{accum}hr_V{valid}_L{lead}.nc`

**When it runs:** After `process_periods` completes (every cycle for regular, after prep for R1)

---

### 7. `run_verpy_plotting`
**Purpose:** Generate interactive map-based verification plots

**Location:** `app/run_verpy_plotting/`

**Key Script:** `bin/verpy_plotting_precip_monitoring.py`

**Inputs:**
- `MET_SOURCE`: Directory with MET Series-Analysis output
- `OUTDIR`: Output directory for plots
- `TRUTH`: Verification truth type
- `LEAD_SEQ`: Lead times to plot
- `ACCUM_PERIOD`: Accumulation period

**Process:**
1. Reads MET NetCDF output files
2. Extracts SL1L2 statistics (stat code 6053 = RMSE)
3. Generates error maps for multiple domains (global, Europe, UK)
4. Creates interactive HTML viewer with dropdown menus

**Outputs:**
- PNG plots: `{vdate}_L{lead}_{area}_{truth}_{accum}hr/*.png`
- HTML viewer: `example_viewer.html`

**When it runs:** After `run_series_analysis` completes

---

### 8. `housekeep`
**Purpose:** Clean up old workflow data and manage disk space

**Location:** `app/housekeep/`

**Key Script:** Shell script for file cleanup

**Inputs:**
- Workflow-specific retention policies

**Process:**
- Removes old cycle data beyond retention period
- Archives important results
- Cleans temporary files

**When it runs:** Configurable (typically daily or per cycle)

---

## Data Flow Summary


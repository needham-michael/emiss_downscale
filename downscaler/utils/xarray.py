"""Utility functions for working with xarray data types"""

import lazy_loader as lazy

pd = lazy.load("pandas")


def display_vars(dset, var_dsec="var_desc", str_incl=None, str_excl=None):
    """Displays variables, units, and descriptions of an xarray dataset

    Generates a printout of each variable within dset that includes the
    variable name, the units, and an extended description of the variable (if
    available).

    Parameters
    ----------
    dset : xarray.Dataset
        Target dataset. It is possible to call `display_vars` on an unformatted
        `dset` e.g., display_vars(xr.open_dataset(file)), or on a formatted
        `dset` e.g., display_vars(get_cmaq_metadata(xr.open_dataset(file))).

    var_dsec : string, default='var_desc'
        Name of the attribute for the xarray.DataArray instances within `dset`
        which contains a description of the variable.

    str_incl : string, default=None
        String pattern to use for filtering. Only printout variables which
        include this pattern.

    str_excl : string, default=None
        String pattern to use for filtering. Only printout variables which
        do not include this pattern.

    Returns
    -------
    None

    See Also
    -------
    cmaq.get_cmaq_metadata
    """

    data_vars = [x.strip() for x in dset.data_vars]

    # Perform filtering of data variables
    if str_incl is not None:
        print(f"Including Pattern: {str_incl}")
        data_vars = [x for x in data_vars if str_incl in x]

    if str_excl is not None:
        print(f"Excluding Pattern: {str_excl}")
        data_vars = [x for x in data_vars if str_excl not in x]

    var = "VARNAME"
    units = "UNITS"
    desc = "DESCRIPTION"

    print("-" * 80)
    print(f"| {var:16} | {units:16} | {desc}")
    print("-" * 80)

    ct = 1

    for var in data_vars:
        desc = ""
        units = ""

        try:
            desc = getattr(dset[var], var_dsec)
        except Exception:
            pass

        try:
            units = dset[var].units
        except Exception:
            pass

        print(f"| {var:16} | {units:16} | {desc}")

        if ct % 6 == 0:
            print("-" * 80)

        ct += 1

    return None


def update_datetime_year(ds, updated_year=1901, time_str="time"):
    """Update the year of the time variable of a dataset

    Given an xarray Dataset or xarray DataArray with a datetime dimension,
    change the year of the datetime variable. This allows for easier
    comparisons with other xarray Datasets or DataArrays when the year is
    unimportant

    Parameters
    ----------

    ds : xr.Dataset or xr.DataArray
        xarray object with a valid datetime dimension

    updated_year : int, default=1901
        This year will replace the year in the original `ds` datetime
        coordinate

    time_str : str, default="time"
        String variable name associated with the datetime dimension

    Returns
    -------

    ds_update : same as `ds`
        xarray object with updated year associated with the datetime coordinate
    """

    # Convert to a pandas dataframe so can use the datetime.replace(year=YYYY)
    # method. Save the original year for documentation purposes
    time = pd.DataFrame({time_str: pd.to_datetime(ds[time_str].data)})
    original_year = time.iloc[0, 0].year
    time = time.loc[:, time_str].apply(lambda x: x.replace(year=updated_year))

    # Copy the original xarray object and update the time dimension
    ds_update = ds.copy()
    ds_update = ds_update.assign_coords({time_str: time})

    # Only assign the original year attribute if it has not previously been
    # assigned to avoid overwriting.
    if "ORIGINAL_YEAR" not in ds_update.attrs:
        ds_update = ds_update.assign_attrs({"ORIGINAL_YEAR": original_year})

    return ds_update


def align_coordinates(da, proj_start, proj_final):
    """Align coordinates of a xr.DataArray to a new coordinate system

    Update the x and y coordinates based on the difference in the false easting
    and false northing between the two coordinate systems

    Parameters
    ----------

    da : xr.Dataset or xr.DataArray
        xarray object for which coordinates will be aligned with a new
        coordinate system

    proj_final : cartopy.crs
        Coordinate system associated with `da`

    proj_start : cartopy.crs
        Target coordinate system for the coordinate alignment

    Returns
    -------

    da_aligned : xr.Dataset or xr.DataArray
        The input `da` after coordinate arrays have been updated based on
        parameters of `proj_final`

    Raises
    ------
    Raises an error if `proj_start` and `proj_final` have different parameters
    """

    # -------------------------------------------------------------------------
    # Ensure all parameters of the two map projections are identical with the
    # excpetion of the false easting and false northing
    # -------------------------------------------------------------------------
    bad_vals = {}
    for key in proj_start.proj4_params.keys():
        if key not in ["x_0", "y_0"]:
            val_start = proj_start.proj4_params[key]
            val_final = proj_final.proj4_params[key]
            if val_final != val_start:
                bad_vals[key] = [val_start, val_final]

    if len(bad_vals.keys()) > 0:
        raise ValueError(f"INCOMPATIBLE MAP PROJECTIONS. {bad_vals=}")

    # -------------------------------------------------------------------------
    # Perform the coordinate adjustment
    # -------------------------------------------------------------------------
    false_easting = {
        "start": proj_start.proj4_params["x_0"],
        "final": proj_final.proj4_params["x_0"],
    }

    false_northing = {
        "start": proj_start.proj4_params["y_0"],
        "final": proj_final.proj4_params["y_0"],
    }

    x_final = da["x"] - false_easting["start"] + false_easting["final"]
    y_final = da["y"] - false_northing["start"] + false_northing["final"]

    da_aligned = da.copy(deep=True)
    da_aligned = da_aligned.assign_coords({"x": x_final, "y": y_final})

    return da_aligned

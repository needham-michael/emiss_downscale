"""Utility functions for working with CMAQ output"""

import lazy_loader as lazy

# Lazy imports of large packages
np = lazy.load("numpy")
cartopy = lazy.load("cartopy")


def get_cmaq_xy(dset):
    """Generate x and y coordinate arrays for cmaq-formatted data

    Interpret attributes of the input file to generate x and y
    coordinate arrays based on the number of gridcells in the x- and
    y-directions, and the size of the gridcells in in those directions
    (which will typically be identical, but in general could be
    different).

    Parameters
    ----------
    dset : xarray.Dataset
        result of calling xr.open_dataset() on a netcdf file in cmaq format

    Returns
    -------
    xcoords : numpy.array
        coordinate array for the x dimension

    ycoords : numpy.array
        coordinate array for the y dimension
    """

    xcoords = np.arange(
        0, (dset.attrs["XCELL"] * dset.attrs["NCOLS"]), dset.attrs["XCELL"]
    )

    ycoords = np.arange(
        0, dset.attrs["YCELL"] * dset.attrs["NROWS"], dset.attrs["YCELL"]
    )

    return xcoords, ycoords


def get_cmaq_datetime(dset, is_jday=True):
    """Generate datetime coordinate array for cmaq-formatted data

    Interpret attributes of the input file to generate datetime
    coordinate array based on the number of timesteps, the size of the
    timestep, and the starting date and time

    Parameters
    ----------
    dset : xarray.Dataset
        result of calling xr.open_dataset() on a file in cmaq format

    is_jday : bool, default=True
        flag to indicate if input dates use the Julian (YYYYJJJ) or the
        Gregorian (YYYYMMDD) calendar format. Note that even if
        is_jday=True, the resulting datetime coordinate array will use
        the defauly pandas gregorian calendar. In other words, this
        flag is only used to interpret input dates, not to set output
        dates.

    Returns
    -------
    datetimes : pandas.Series
        datetime coordinate array, parsed to pandas gregorian datetime
        format.
    """
    from pandas import to_datetime

    ntstep = len(dset.TSTEP)

    times = np.arange(
        dset.attrs["STIME"], dset.attrs["TSTEP"] * ntstep, dset.attrs["TSTEP"]
    )

    start_date = dset.attrs["SDATE"]
    date_inc = -1
    datetimes = []

    for time in times % 240000:
        if time == 0:
            date_inc += 1

        datetimes.append(f"{start_date+date_inc}T{time:0>6}")

    if is_jday:
        date_format = "%Y%jT%H%M%S"
    else:
        date_format = "%Y%m%dT%H%M%S"

    datetimes = to_datetime(datetimes, format=date_format)

    return datetimes


def get_cmaq_projection(dset, proj_type="lambert"):
    """Create a cartopy lambert projection object from dataset metadata"""

    if proj_type == "lambert":
        # Generate the projection
        proj = cartopy.crs.LambertConformal(
            central_latitude=dset.attrs["YCENT"],
            central_longitude=dset.attrs["XCENT"],
            standard_parallels=(dset.attrs["P_ALP"], dset.attrs["P_BET"]),
            false_easting=-dset.attrs["XORIG"],
            false_northing=-dset.attrs["YORIG"],
        )

    elif (proj_type == "mercator") or (proj_type == "polar"):
        raise NotImplementedError(f'projection: "{proj_type}" not yet implemented')

    else:
        raise ValueError(
            f"""
        Invalid projection: {proj_type}.
        Choose a valid projection: [\'lambert\', \'mercator\', \'polar\']
        """
        )

    return proj


def get_cmaq_metadata(dset, is_jday=True, return_proj=False):
    """Interpret and add coordinate arrays to cmaq-formatted data

    Interpret attributes of the input file to generate datetime
    coordinate array based on the number of timesteps, the size of the
    timestep, and the starting date and time

    Parameters
    ----------
    dset : xarray.Dataset
        result of calling xr.open_dataset() on a file in cmaq format

    is_jday : bool, default=True
        parameter passed to get_cmaq_datetime()

    Returns
    -------
    dset : xarray.Dataset
        the same input dataset, but with added coordinate arrays

    proj_lamb : cartopy.crs.LambertConformal
        a cartopy Lambert conformal conic projection with parameters
        set by the input dataset attributes, for use in plotting

    See Also
    --------
    drop_cmaq_metadata
    """

    # Get coordinate arrays associated with the x-, y-, and time-dimensions
    xcoords, ycoords = get_cmaq_xy(dset)
    datetimes = get_cmaq_datetime(dset, is_jday=is_jday)

    # Add the coordinate arrays and rename the output
    dset = dset.assign_coords({"COL": xcoords, "ROW": ycoords, "TSTEP": datetimes})
    dset = dset.rename({"ROW": "y", "COL": "x", "TSTEP": "time"})

    if return_proj:

        proj = get_cmaq_projection(dset)

        return dset, proj

    return dset


def drop_cmaq_metadata(dset):
    """Remove metadata and reset to original IOAPI conventions

    Drop all metadata additions made to dataset by get_cmaq_metadata

    Parameters
    ----------
    dset : xarray.Dataset
        result of calling xr.open_dataset() on a file in cmaq format

    Returns
    -------
    dset : xarray.Dataset
        the same input dataset, but coordinate arrays dropped

    See Also
    --------
    get_cmaq_metadata
    """

    # Drop projection-aware x and y coordinates, and datetime-aware time coord
    dset = dset.drop_vars(["x", "y", "time"])

    # Rename back to IOAPI convention
    dset = dset.rename_dims(
        {
            "time": "TSTEP",
            "x": "COL",
            "y": "ROW",
        }
    )

    # Ensure there is a length-1 "LAY" dimension
    if "LAY" not in list(dset.dims):
        dset = dset.expand_dims(dim="LAY", axis=1)

    return dset

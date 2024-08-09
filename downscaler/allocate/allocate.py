"""Module controlling spatially-informed downscaling of emissions"""

import argparse
import logging
import lazy_loader as lazy
from time import perf_counter
from functools import partial
from tqdm import tqdm
from downscaler.utils.cmaq import get_cmaq_metadata, get_cmaq_projection
from downscaler.utils.xarray import align_coordinates, update_datetime_year


# Implement lazy loading of certain large external modules. This is mostly so
# that package imports occur after parsing commnad line input in order to
# serve the --help menu quickly if necessary.
np = lazy.load("numpy")
xr = lazy.load("xarray")


def _fill_perimeter(da):
    """Fill NaNs along array perimeter with nearest value

    Parameters
    ----------
    da : xr.DataArray
        Input DataArray, with coordinate dimensions x and y

    Returns
    -------
    da :
        The same input `da` after NaN perimeter values have been filled
        according to the nearest neighbor

    Notes
    -----
    This internal function is only necessary because the implementation of
    xarray.DataArray.interp_like(...,method='nearest') interprets the perimeter
    values as outside of the domain. In this specific use-case, it is
    understood that these values are not outside of the domain, but should
    instead be filled with neighboring points, because we have downscaled from
    a coarse to a fine grid
    """

    x = da["x"]
    y = da["y"]

    da.loc[dict(x=x[0])] = da.loc[dict(x=x[1])]
    da.loc[dict(x=x[-1])] = da.loc[dict(x=x[-2])]
    da.loc[dict(y=y[0])] = da.loc[dict(y=y[1])]
    da.loc[dict(y=y[-1])] = da.loc[dict(y=y[-2])]

    return da


def coarsen_finescale_emissions(da_fine, grid_factor=3, agg=np.sum):
    """Upscale fine-gridded emissions to a coarser grid

    Parameters
    ----------
    da_fine : xr.DataArray or xr.Dataset
        Fine scale emissions. Units of `da` determine the appropriate choice
        of `agg`

    grid_factor : int, default=3
        Number of gridcells in the x- and y-dimensions to combine to generate
        the coarse scale emissions.

    agg : function, default=np.sum
        Function used to combine fine scale emissions onto the coarse grid.

    Returns
    -------
    da_coarse : same type as `da_fine`
        Coarse scale emissions

    Notes
    -----
    Note on the choice of the `agg` function:
        It is important to conserve mass when coarsening emissions from the
        fine to the coarse grid.  If emissions are in units like
        [moles / second], then np.sum is likely appropriate, while if instead
        emissions are in units like [moles / second / km$^2$], then np.mean is
        likely appropriate.
    """

    da_coarse = da_fine.coarsen(x=grid_factor, y=grid_factor).reduce(agg)
    da_coarse = da_coarse.assign_attrs(
        {
            "COARSEN": f"""Emissions generated from fine to coarse scale by a factor of {grid_factor} in the x- and y-dimensions. Data aggregated with function: `{agg.__name__}`"""
        }
    )

    return da_coarse


def fractional_contribution(da_fine, da_coarse):
    """Calculate the fractional contribution of fine- to coarse-scale emissions

    Calculate the fraction of the total emissions within a coarse-scale
    gridcell that are due to each fine-scale gridcell that falls within the
    coarse-scale gridcell.

    Parameters
    ----------
     da_fine : xr.DataArray or xr.Dataset
        Fine scale emissions.

    da_coarse : same type as `da_fine` xr.DataArray or xr.Dataset
        Coarse scale emissions.

    Returns
    -------
    da_fractional_contribution: same type as `da_fine`
        Fractional contribution of each fine scale emissions to the total
        emissions within the coarse scale. Due to divide by zero issues, if
        the total emissions within a coarse scale gridcell are zero, then the
        emission fraction for the fine gridcells within the coarse cell are
        set equal to zero.

    Notes
    -----
    The implementation using xarray.DataArray.interp_like(...,method='nearest')
    leads to NaN values along the perimeter because of its reliance on
    scipy.interpolate.interpn, which interprets these perimeter values as
    outside of the domain.

    """

    # Regrid the coarse scale emissions back down to the fine scale so that the
    # fractional contribution calculation can be performed array-wise. See note
    # on filling NaN values along perimeter
    da_coarse_regridded = da_coarse.interp_like(da_fine, method="nearest")
    da_coarse_regridded = _fill_perimeter(da_coarse_regridded)

    da_fractional_contribution = da_fine / da_coarse_regridded

    return da_fractional_contribution.fillna(0)


def downscale_coarse_emissions(
    da_fine, da_coarse, proj_fine, proj_coarse, grid_factor=3, agg=np.sum
):
    """Downscale coarse emissions based on fine scale spatial information

    Parameters
    ----------
    da_fine : xr.DataArray or xr.Dataset
        Emissions on a fine grid which will be used to estimate the spatial
        allocation of emissions between the coarse and fine scales.

    da_coarse : xr.DataArray or xr.Dataset
        Emissions on a coarse grid which will be downscaled to a finer grid
        based on the spatial distribution of emissions learned from `da_fine`.

    proj_fine, proj_coarse: cartopy.crs
        Map projections associated with `da_fine` and `da_coarse`, respectively

    grid_factor : int, default=3
        The number of `da_fine` gridcells which it within a single `da_coarse`
        gridcell.

    agg : function, default=np.sum
        Aggregation function used to combine `da_fine` values when upscaling to
        the coarser grid. Whether `np.sum` or `np.mean` is appropriate is
        dependent on the units of the particular emission species. The default
        of `np.sum` is appropriate for emissions with units like [moles/second]

    Returns
    -------
    da_dscale : same type as da_coarse
        Downscaled emissions estimate based on the spatial distribution of
        emissions from `da_fine`.

    Notes
    -----
    The expected use case for this method is to take fine-scale gridded
    emissions from an older modeling platform (e.g., 2018 on a custom 4km grid)
    and use the spatial information associated with those emissions to estimate
    the fine-scale gridded emissions from a newer modeling platform (e.g., 2018
    on a 12US1 grid).
    """

    # =========================================================================
    # Step 1: Upscale the reference emissions from the fine to the coarse scale
    # =========================================================================
    # First, ensure that the x- and y-coordinates of the target and reference
    # emissions use the same false easting and false northing
    da_coarse = align_coordinates(
        da_coarse, proj_start=proj_coarse, proj_final=proj_fine
    )

    # Upscale the reference emissions up to the same resolution as the
    # target emissions; aggregate together using `agg`
    da_fine_coarsened = coarsen_finescale_emissions(
        da_fine, grid_factor=grid_factor, agg=agg
    )

    # =========================================================================
    # Step 2: Calculate the fractional contribution to the total emissions from
    #         the fine scale
    # =========================================================================
    # Calculate the fractional contribution that each fine-scale reference
    # gridcell makes to the total emissions on the coarsened reference
    # emissions
    ref_contrib = fractional_contribution(da_fine=da_fine, da_coarse=da_fine_coarsened)

    # =========================================================================
    # Step 3: Use the fractional contribution to downscale the target emissions
    #         onto the finer grid
    # =========================================================================

    # Interpolate the target emissions onto the finer grid using a nearest
    # neighbor method so that the downscaling can be achieved using a simple
    # array-wise multiplication. Note the need to call the internal
    # _fill_perimeter function due to the specific implementation of the
    # NN interpolation... see the associated docstring for that function
    da_coarse_nn = da_coarse.interp_like(da_fine, method="nearest")
    da_coarse_nn = _fill_perimeter(da_coarse_nn)

    # Finally, multiply the reference fraction and target NN arrays together
    # to downscale the emissions
    da_dscale = ref_contrib * da_coarse_nn

    return da_dscale


def parse_args():
    """Parse Command Line Arguments and enforce any necessary conditions"""
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "fine",
        help="emissions on fine grid, will be used to downscale coarse emissions",
    )
    parser.add_argument(
        "coarse", help="emissions on coarse grid, will be downscaled to fine grid"
    )

    parser.add_argument(
        "--out", help="output file for downscaled emissions", default="./out.ncf"
    )

    parser.add_argument(
        "--grid-factor",
        help="Ratio of coarse grid spacing to fine grid spacing. Must be an odd integer.",
        default=3,
        type=int,
        dest="gridfactor",
    )

    parser.add_argument(
        "--data-vars",
        help="Variable names for spatial downscaling",
        action="store",
        default=None,
        nargs="*",
        dest="datavars",
    )

    parser.add_argument(
        "--output-year",
        help="Set the year of the output file",
        default=1901,
        type=int,
        dest="outputyear",
    )

    parser.add_argument(
        "-d",
        "--debug",
        help="Print lots of debugging statements",
        action="store_const",
        dest="loglevel",
        const=logging.DEBUG,
        default=logging.WARNING,
    )

    parser.add_argument(
        "-v",
        "--verbose",
        help="increase output verbosity",
        action="store_const",
        dest="loglevel",
        const=logging.INFO,
    )

    parser.add_argument(
        "-p",
        "--progress-bar",
        help="Show a progress bar for downscaling vars",
        action="store_true",
        dest="progressbar",
    )

    args = parser.parse_args()

    if args.gridfactor % 2 == 0:
        raise ValueError(
            f"--grid-factor={args.gridfactor} Is not an odd integer. Exiting."
        )

    return args


def setup_logger(loglevel):

    logging.basicConfig(
        format="[%(asctime)s %(levelname)s] %(message)s", level=loglevel
    )
    logging.info("Logging Initialized.")

    return


def map_downscale(var, da_ref, da_target, proj_ref, proj_target, grid_factor):

    out = downscale_coarse_emissions(
        da_ref=da_ref[var],
        da_target=da_target[var],
        proj_ref=proj_ref,
        proj_target=proj_target,
        grid_factor=grid_factor,
    )

    return out


def downscale_vars(data_vars, da_ref, da_target, grid_factor, progress):

    proj_fine = get_cmaq_projection(da_ref)
    proj_coarse = get_cmaq_projection(da_target)

    map_downscale_partial = partial(
        map_downscale,
        da_ref=da_ref,
        da_target=da_target,
        grid_factor=grid_factor,
        proj_ref=proj_fine,
        proj_target=proj_coarse,
    )

    logging.debug("Begin Serial Processing of Downscaling Var")
    downscaled_output = {var: map_downscale_partial(var) for var in progress(data_vars)}

    return downscaled_output


def main():
    start_time = perf_counter()

    # -------------------------------------------------------------------------
    # Parse command line args
    # -------------------------------------------------------------------------

    args = parse_args()

    setup_logger(args.loglevel)

    file_coarse = args.coarse
    file_fine = args.fine
    file_out = args.out
    output_year = args.outputyear
    data_vars = args.datavars
    grid_factor = args.gridfactor
    progress_bar = args.progressbar

    # Null function for progress bar unless --progress-bar is flagged from CLI
    def progress(x):
        return x

    if progress_bar:
        progress = tqdm

    logging.info("Progress Bar: %s", progress_bar)
    logging.info("Coarse-scale file: %s", file_coarse)
    logging.info("Fine-scale file: %s", file_fine)
    logging.info("Output file: %s", file_out)
    logging.info("Output year set to %s", output_year)

    # -------------------------------------------------------------------------
    # Read Input Data
    # -------------------------------------------------------------------------

    logging.info("Reading Fine-scale file")
    grid_fine = update_datetime_year(
        get_cmaq_metadata(xr.open_dataset(file_fine, engine="netcdf4")),
        updated_year=output_year,
    )

    logging.info("Reading Coarse-scale file")
    grid_coarse = update_datetime_year(
        get_cmaq_metadata(xr.open_dataset(file_coarse, engine="netcdf4")),
        updated_year=output_year,
    )

    # -------------------------------------------------------------------------
    # Identify variables for downscaling
    # -------------------------------------------------------------------------

    if data_vars is None:
        data_vars = list(grid_coarse.data_vars)
        data_vars = [x for x in data_vars if x in grid_fine.data_vars]
        data_vars = [
            x
            for x in data_vars
            if ("x" in grid_coarse[x].dims) and ("y" in grid_coarse[x].dims)
        ]

    logging.info("Downscaling vars")
    logging.debug("Target vars: %s", data_vars)

    # -------------------------------------------------------------------------
    # Apply downscaling function to each variable
    # -------------------------------------------------------------------------

    downscaled_output = downscale_vars(
        data_vars,
        da_ref=grid_fine,
        da_target=grid_coarse,
        grid_factor=grid_factor,
        progress=progress,
    )

    logging.debug("Completed vars: %s", list(downscaled_output.keys()))

    # -------------------------------------------------------------------------
    # Collect downscaled variables and save to netcdf
    # -------------------------------------------------------------------------

    logging.info("Writing output to %s", file_out)
    dset_out = xr.Dataset(downscaled_output)
    dset_out.to_netcdf(file_out)
    logging.info("Done. Elapsed time in seconds: %s", perf_counter() - start_time)


if __name__ == "__main__":
    main()

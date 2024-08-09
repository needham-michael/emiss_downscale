Installation
===============

Getting the code
----------------

The most up-to-date version of this repository including all tutorial data can be downloaded locally using git. You can "get git" onto your local machine __[directly from the git website](https://git-scm.com/downloads)__, or it can be installed within a conda environment using `conda install -c conda-forge git`. Either way, once git is configured, you can download everything you need to run these examples with

```shell
git clone https://github.com/needham-michael/emiss_downscale.git
```

This will create a directory called `/emiss_downscale` on your local machine.

Preparing the python environment
--------------------------------

The `environment.yml` file includes instructions for recreating the same conda environment (also named `emiss_downscale`) used to develop and run these notebooks. Assuming conda has been __[installed locally](https://conda.io/projects/conda/en/latest/user-guide/install/index.html)__ and __[initialized](https://conda.io/projects/conda/en/latest/dev-guide/deep-dives/activation.html)__ for the user's shell, the environment can be recreated by running the following command from within the base directory

```shell
conda env create -f environment.yml`

# Then, activate the environment with
conda activate emiss_downscale
```

Installing the project package
------------------------------
You will need to install the project source code into the `emiss_downscale` conda environment by running the following command from the root `./emiss_downscale` folder (make sure that the correct conda environment is selected):

```shell 
(emiss_downscale) pip install .
```

This will install the package source code (`/emiss_downscale/downscaler`) into the active conda environment.

Configuring Jupyter Notebooks
-----------------------------

### Usage with JupyterHub

Once the environment has been created, Jupyter needs to be configured to execute the notebooks *using the environment.* This requires using the __[ipykernel](https://github.com/ipython/ipykernel)__ package, which was included in the `environment.yml` file. From the terminal window, run

```shell
python3 -m ipykernel install --user --name=cmaq_pyenv --display-name="Python3 (cmaq_pyenv)"
```

Then, select the appropriate tile from the jupyterlab launcher.

### Usage with JupyterLab or Jupyter Notebooks

Ensure the environment is active and run one of the following commands to launch a jupyter server.

```shell
# For jupyter lab
(emiss_downscale) jupyter lab

# For the classic notebooks
(emiss_downscale) jupyter notebook
```

Next Up: __[Getting Started](./getting_started.md)__
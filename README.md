<!-- TITLE AND SUBTITLE -->
<br />
<p align="center">
  <h1 align="center">SOTJ Profit Shifting Estimates</h1>
</p>
<p align="center">Calculation of SOTJ Profit Shifting Estimates </p>

<br />

<!-- TABLE OF CONTENTS -->
<details open="open">
  <summary><h2 style="display: inline-block">Table of Contents</h2></summary>
  <ol>
    <li><a href="#about-the-project">About The Project</a></li>
    <li><a href="#installation">Installation</a></li>
    <li><a href="#run">Run</a></li>
    <li><a href="#project-organization">Project Organization</a></li>
  </ol>
</details>

<br />

<!-- ABOUT THE PROJECT -->
## About The Project

The aim of this code is to produce the shifting profits estimates using the data from the corporate tax statistic database of the [OCDE](https://www.oecd.org/tax/tax-policy/corporate-tax-statistics-database.htm).


This code has been recycled from the repository `202107_SoTJ2021` from Share Point `Shared Documents > Data > Code > Code_projects`.

*Note:* Adding a new corporate tax rate dataset might produce running issues.

<br />

<!-- INSTALLATION -->
## Installation

To get a local copy up and running follow these simple steps.

### Set up environment

```
conda env create -f environment.yml

conda activate sotj_profit_shifting_estimates
```
### Visual Studio Code

After running the code above in Terminal, you still have to select the environment in VSCode. Click `F1`, select `Python: Select Interpreter`, click `Enter` and select the one that has `sotj_profit_shifting_estimates` in brackets. If you don't see the environment in the list, reload VS Code.

<br />

<!-- RUN -->
## Run

First you need to log in to ibfd.org website with an subscribed account. Details can be found in the notebooks comments.

Paths to input dataset must be set and can be found in `src/config.py` file.

In order to generate the report run the following jupyter notebook in the following order:
   ```sh
   1.clean_data.ipynb
   2.create_mislalignment.ipynb
   3.study_mislalignment.ipynb
   ```

The output will be stored in the `final` folder and `TJN - Shared Documents/Workstreams/Scale of Tax Injustice/State of Tax Justice report/{YEAR_SOTJ} Report/Tax avoidance/` in Share Point.

<br />

<!-- PROJECT ORGANIZATION -->
## Project Organization

The project is composed of 3 main notebooks.

Other files such as helper.py are used as auxiliary code to assist these main notebooks.

<br />

This is the structured followed by this project
<pre><code>

├── LICENSE 
├── README.md          <- The top-level README for developers using this project
├── data
│   ├── final          <- Final results and datasets
│   ├── intermediary   <- Intermediate datasets
│   └── raw            <- The original, immutable data dump
│
├── docs               <- Documents of interest for this project
│
├── src                <- Source code as Jupyter notebooks
│
├── environment.yml    <- YAML file to create conda environment to run the project
   
</code></pre>

<br />

<!-- BUILT WITH -->
## Built With

* [Python 3.11](https://www.python.org/)
* [Jupyter Notebook](https://jupyter.org/ )
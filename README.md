<!-- TITLE AND SUBTITLE -->
<br />
<p align="center">
  <h1 align="center">SOTJ Profit Shifting Estimates</h1>
</p>
<p align="center">Calculation of SOTJ Profit Shifting Estimates & Comparative Analysis </p>

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

The project is composed of two sections: A first one to calculate the profit shifting estimates, and a second one to perform a comparative analysis with the previous year estimates.

### 1. Profit shifting estimates
The aim of this code is to produce the shifting profits estimates using the data from the corporate tax statistic database of the [OCDE](https://www.oecd.org/tax/tax-policy/corporate-tax-statistics-database.htm).


This code has been recycled from the repository `202107_SoTJ2021` from Share Point `Shared Documents > Data > Code > Code_projects`.

*Note:* Adding a new corporate tax rate dataset might produce running issues.

### 2. Comparative analysis

This section analyses the potential causes behind the significant increase in profit shifting observed between 2017 and 2018 (or any given dates and data). Several hypotheses are tested, including increased coverage of countries and prior underestimation, inflation, a higher percentage of profits being shifted by multinational corporations (MNCs), and larger company profits.

The raw data is stored in the following Share Point folder: `Shared Documents > Workstreams > Scale of Tax Injustice > Scale of Tax Justice report > Analysis > Corporate tax abuse`.

The drafted comparative analysis can be found in [SharePoint](https://taxjustice.sharepoint.com/:w:/g/ETg3ZdAeu_dJr_YI1TJEypEB53ImwvckssE0q2yERaWMrw?e=E8vBP5).
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

Paths to input dataset must be set and can be found in `src/1_estimation/config.py` and `src/2_analysis/config.py` files.

To generate the estimates and the analysis, please begin by running the first jupyter notebook of each subfolder (1_estimation and 2_analysis) and continue through the subsequent notebooks.

The output will be stored in the `final` folder and `TJN - Shared Documents/Workstreams/Scale of Tax Injustice/State of Tax Justice report/{YEAR_SOTJ} Report/Tax avoidance/` in Share Point. 

<br />

<!-- PROJECT ORGANIZATION -->
## Project Organization

The project is composed of 2 main folders: the source code folder named `src` and the `data` folder containing raw, intermediate and final outputs.

The `src` folder contains one subfolder for each section of the project: the profit shifting estimates calculation and the comparative analysis.

<br />

This is the structured followed by this project
<pre><code>

├── README.md          <- The top-level README for developers using this project
├── data
│   ├── final          <- Final results and datasets
│   ├── intermediate   <- Intermediate datasets
│   └── raw            <- The original, immutable data dump
│
├── docs               <- Documents of interest for this project
│
├── src                <- Source code as Jupyter notebooks
│   ├── 1_estimate     <- Profit shifting estimates calculation
│   ├── 2_analysis     <- Comparative analysis
│
├── environment.yml    <- YAML file to create conda environment to run the project
   
</code></pre>

<br />

<!-- BUILT WITH -->
## Built With

* [Python 3.11](https://www.python.org/)
* [Jupyter Notebook](https://jupyter.org/ )
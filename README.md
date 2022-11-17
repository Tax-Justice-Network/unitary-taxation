<!-- TITLE AND SUBTITLE -->
<br />
<p align="center">
  <h1 align="center">IBFD Scraper</h1>
</p>
<p align="center">Collecting Tax Treaty data from the International Bureau of Fiscal Documentation </p>

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

To do.

<br />

<!-- INSTALLATION -->
## Installation

To get a local copy up and running follow these simple steps.

### Set up environment

```
conda env create -f environment.yml

conda activate ibfd_scraper
```
### Visual Studio Code

After running the code above in Terminal, you still have to select the environment in VSCode. Click `F1`, select `Python: Select Interpreter`, click `Enter` and select the one that has `ibfd_scraper` in brackets. If you don't see the environment in the list, reload VS Code.

<br />

<!-- RUN -->
## Run

First you need to log in to ibfd.org website with an subscribed account. Details can be found in the notebooks comments.

In order to generate the report run the following jupyter notebook in the following order:
   ```sh
   1a_download_snapshot_current.ipynb
   1b_download_country_surveys.ipynb
   2_clean_snapshot.ipynb
   3_extract_capital_gains.ipynb
   ```

The output will be stored in the `final` folder.

<br />

<!-- PROJECT ORGANIZATION -->
## Project Organization

The project is composed of 4 main notebooks

* 1a_download_snapshot_current.ipynb produces the folders `wht` and `kf`
* 1b_download_country_surveys.ipynb produces the folders `cta` and `gtha`
* 2_clean_snapshot.ipynb produces `treaty_wht_step1` and `treaty_wht_step2` excel files
* 3_extract_capital_gains.ipynb produces `all_kf` excel file


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
    ├── src          <- Source code as Jupyter notebooks
    │
    ├── environment.yml           <- YAML file to create conda environment to run the project
   
</code></pre>

<br />

<!-- BUILT WITH -->
## Built With

* [Python 3.11](https://www.python.org/)
* [Jupyter Notebook](https://jupyter.org/ )
import os
import sys
import subprocess
import pandas as pd

projects = pd.read_csv('./projects.tsv', sep='\t')
projects.set_index('id', inplace=True)


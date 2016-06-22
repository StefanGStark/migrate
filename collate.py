import os
import sys
import subprocess
import json
import re
import pandas as pd
import numpy as np

def extract_giturl(gitdir):
    cdir = os.getcwd()
    os.chdir(gitdir)
    origin_cmd = 'git remote show -n origin'.split()
    origin = subprocess.Popen(origin_cmd, stdout=subprocess.PIPE).communicate()[0]
    fetch = [line for line in origin.splitlines() if 'Fetch' in line][0]
    gitname = fetch.split(':')[2]
    project = gitname.split('/')[0]
    repo = re.sub('.git$', '', gitname.split('/')[1])
    os.chdir(cdir)
    return gitname, project, repo

def get_all_gitdirs(wdir=None):
    if wdir is None: wdir = '/cluster/project/raetsch/lab/01/home/starks/rgit'
    cmd = 'find %s -name *.git' %wdir
    files, stderr = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE).communicate()
    gitdirs = [os.path.dirname(fname) for fname in files.split()]
    return gitdirs

projects_path ='/cluster/project/raetsch/lab/01/home/starks/git_migrate/projects.tsv'
projects = pd.read_csv(projects_path, sep='\t')
projects.set_index('id', inplace=True)
gitdirs = get_all_gitdirs()
gitinfo = list()
for gdir in gitdirs:
    gitinfo.append(extract_giturl(gdir))
gitinfo = pd.DataFrame(gitinfo, columns=['giturl', 'gitparent', 'gitrepo'])

import os
import sys
import subprocess
import json
import re
import pandas as pd
import numpy as np
import shutil
import pdb

def extract_gitname(gitdir):
    cdir = os.getcwd()
    os.chdir(gitdir)
    origin_cmd = 'git remote show -n origin'.split()
    origin = subprocess.Popen(origin_cmd, stdout=subprocess.PIPE).communicate()[0]
    fetch = [line for line in origin.splitlines() if 'Fetch' in line][0]
    gitname = fetch.split(':')[2]
    project = gitname.split('/')[0]
    repo = re.sub('.git$', '', gitname.split('/')[1])
    os.chdir(cdir)
    return project, repo

def get_all_gitdirs(wdir=None):
    if wdir is None: wdir = '/cluster/project/raetsch/lab/01/home/starks/rgit'
    cmd = 'find %s -name *.git' %wdir
    files, stderr = subprocess.Popen(cmd.split(), stdout=subprocess.PIPE).communicate()
    gitdirs = [os.path.dirname(fname) for fname in files.split()]
    return gitdirs

def create(repo_url, repo_name):
    '''Pulls gitorious repo, creates github repo, adds github as remote.

    Creates a temporary directory and pulls gitorious repo (repo_url) there. Creates
    github repo given repo_name, adds it as a remote and pushes. If any errors are
    encountered, returns the repo_url.

    Arguments
    repo_url: url of gitorious repository
    repo_name: name of github repo

    Returns
    None: if remote successfully added
    repo_url: if any commands fail
    '''
    tmpdir = '/cluster/project/grlab/home/starks/tmp'
    count = 0
    while os.path.exists(tmpdir):
        tmpdir = '%s_%d' %(tmpdir, count)
        count = count + 1
    os.makedirs(tmpdir)
    os.chdir(tmpdir)
    # pull repo
    pipe = subprocess.PIPE
    initscript = '/cluster/project/raetsch/lab/01/home/starks/git_migrate/migrate_starks.sh'
    initproc = subprocess.Popen([initscrpit, reponame], stdout=subprocess.PIPE)
    (stdout, initstderr) = initproc.communicate()
    if initstderr is None:
        result = json.loads(stdout)
        url = result['url']
        add = 'git remote add github %s'%url
        push = 'git push --all github'
        addproc = subprocess.Popen(add.split(), stdout=pipe, stderr=pipe)
        (stdout, addstderr) = addproc.communicate()
        if addstderr is None:
            pushproc = subprocess.Popen(push.split(), stdout=pipe, stderr=pipe)
            (stdout, pushstderr) = pushproc.communicate()
    os.chdir('/cluster/project/grlab/home/starks')
    shutil.rmtree(tmpdir)
    if initstderr is not None or addstderr is not None or pushstderr is not None:
        return repo_url
    pass

def pull_gitorious_repo(gitor_repo_url):
    tmp_repo_dir = '/cluster/project/grlab/home/starks/tmp'
    count = 1
    if os.path.exists(tmp_repo_dir):
        tmp_repo_dir_ext = tmp_repo_dir + str(count)
        while os.path.exists(tmp_repo_dir_ext):
            count = count + 1
            tmp_repo_dir_ext = tmp_repo_dir + str(count)
        tmp_repo_dir = tmp_repo_dir_ext
    os.makedirs(tmp_repo_dir)
    clone_cmd = 'git clone %s %s' %(gitor_repo_url, tmp_repo_dir)
    clone_proc = subprocess.Popen(clone_cmd.split(), stdout=pipe, stderr=pipe)
    stdout, clone_stderr = clone_proc.communicate()
    if clone_stderr is not None and clone_stderr.lower().startswith('fatal'):
        raise ValueError(clone_stderr)
    return tmp_repo_dir

def init_github_repo(reponame):
    init_cmd = "curl -u %s:%s https://api.github.com/user/repos -d {\"name\":\"%s\"}"  %(gituser, token, reponame)
    init_proc = subprocess.Popen(init_cmd.split(), stdout=pipe, stderr=pipe)
    (stdout, init_stderr) = init_proc.communicate()
    if init_stderr is not None and not init_stderr.strip().startswith('% Total'):
        raise ValueError(init_stderr)
    url = 'git@github.com:%s/%s.git'%(gituser, reponame)
    return url

def add_github_remote(repo_dir, repo_url):
    wd = os.getcwd()
    os.chdir(repo_dir)
    add = 'git remote add github %s'%repo_url
    addproc = subprocess.Popen(add.split(), stdout=pipe, stderr=pipe)
    (stdout, add_stderr) = addproc.communicate()
    if len(add_stderr) > 0:
        os.chdir(wd)
        raise ValueError(add_stderr)
    else:
        push = 'git push --all github'
        pushproc = subprocess.Popen(push.split(), stdout=pipe, stderr=pipe)
        (stdout, push_stderr) = pushproc.communicate()
        if push_stderr is not None and not '[new branch]' in push_stderr:
            os.chdir(wd)
            raise ValueError(push_stderr)
        else:
            print push_stderr
    os.chdir(wd)

def process_one_repo(gitor_repo_url, github_repo_name):
    tmp_repo_dir = pull_gitorious_repo(gitor_repo_url)
    github_url = init_github_repo(github_repo_name)
    add_github_remote(tmp_repo_dir, github_url)
    pass

def format_clone_url(clone_url):
    clone_url = clone_url.replace('git.ratschlab.org/', 'git.ratschlab.org:')
    clone_url = re.sub('^git://', '', clone_url)
    if not clone_url.startswith('git@'):
        clone_url = 'git@%s'%clone_url
    return clone_url

gituser='stefangstark'
token='3d2c3b82da6ea189ef6fa032b434670ab95b1afc'

pipe = subprocess.PIPE
projects_path ='/cluster/project/raetsch/lab/01/home/starks/git_migrate/projects.tsv'
projects = pd.read_csv(projects_path, sep='\t')
projects.set_index('id', inplace=True)
parent_ignore = ['sandbox']

repo_names, repo_counts = np.unique(projects['repository'], return_counts=True)
repo_dup_names = repo_names[repo_counts > 1]
dup_mask = np.in1d(projects['repository'], repo_dup_names)
dups = projects[dup_mask][['repository', 'parent']]
for indx, (rname, pname) in dups.iterrows():
    if pname.startswith('Tex'):
        new_name = '%s:%s' %(pname, rname)
        projects.set_value(indx, 'repository', new_name)
    else:
        continue
_, project_counts = np.unique(projects['repository'].values, return_counts=True)
assert np.all(project_counts == 1), "Project names are not unique!"


def test():
   gitor_repo_url = 'git@git.ratschlab.org:migratetest/migratetest.git'; tmp_repo_dir = mig.pull_gitorious_repo(gitor_repo_url)
   github_repo_name = 'gitmigrate_test'; github_url = mig.init_github_repo(github_repo_name)
   mig.add_github_remote(tmp_repo_dir, github_url)


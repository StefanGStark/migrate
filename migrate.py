import os
import sys
import subprocess
import json
import re
import pandas as pd
import numpy as np
import shutil
import pdb
import shlex
import datetime
import stat

script_dir = os.path.dirname(os.path.abspath(__file__))
fetch_script = os.path.join(script_dir, 'fetch_branches.sh')
logfile = open('/cluster/project/raetsch/lab/01/home/starks/git_migrate/log', 'a+', 1)

def del_rw(action, name, exc):
    os.chmod(name, 0o777)
    os.remove(name)
    pass

def add(gitor_repo_url, github_repo_name, test=False, debug=False):
    tmp_repo_dir = None
    if test: github_repo_name = 'test_' + github_repo_name
    try:
        logfile.write('%s\tInitializing %s\n' %(time(), github_repo_name))
        github_url = init_github_repo(github_repo_name, debug=debug)
        logfile.write('%s\tPulling %s\n' %(time(), gitor_repo_url))
        tmp_repo_dir = pull_gitorious_repo(gitor_repo_url)
        logfile.write('%s\tJoining %s and %s\n' %(time(), gitor_repo_url, github_url))
        add_github_remote(tmp_repo_dir, github_url)
        logfile.write('%s\tJoin successful %s\n' %(time(), gitor_repo_url))
        if not test: update_projects(github_repo_name)
    except Exception as e:
        logfile.write('Error: %s\n' %e)
    finally:
        if tmp_repo_dir is not None:
            if os.getcwd() == tmp_repo_dir: os.chdir(os.path.expanduser('~'))
            if os.path.exists(tmp_repo_dir):
                os.system("chmod -R 777 %s" %tmp_repo_dir) # SUPER HACK -- PLEASE SOMEONE HELP
                shutil.rmtree(tmp_repo_dir)
    pass

def init_github_repo(reponame, private=True, debug=False, desc=None, gitor_repo_url=None):
    '''Initializes a repository on github.

    If the repositiory exists or something went wrong ('name' is not in the result json),
    raises a ValueError
    '''
    if desc is None: desc = ''
    if not gitor_repo_url is None: desc = desc + '\nCloned from %s' %gitor_repo_url
    init_json = "{\"name\":\"%s\",\"private\":%s,\"description\":\"%s\"}" %(reponame, str(private).lower(), desc)
    init_cmd = "curl -u %s:%s https://api.github.com/orgs/%s/repos -d '%s'"  %(gituser, token, org, init_json)
    init_proc = subprocess.Popen(shlex.split(init_cmd), stdout=pipe, stderr=pipe)
    (stdout, init_stderr) = init_proc.communicate()
    result = json.loads(stdout)
    if debug: pdb.set_trace()
    if not 'name' in result:
        raise ValueError(result)
    url = 'git@github.com:%s/%s.git'%(org, reponame)
    return url

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
    gitor_repo_url = format_clone_url(gitor_repo_url)
    clone_cmd = 'git clone %s %s' %(gitor_repo_url, tmp_repo_dir)
    clone_proc = subprocess.Popen(shlex.split(clone_cmd), stdout=pipe, stderr=pipe)
    stdout, clone_stderr = clone_proc.communicate()
    fetch_all_branches(tmp_repo_dir)
    assert len(os.listdir(tmp_repo_dir)) > 0, 'Git was not pulled or was empty'
    return tmp_repo_dir

def extract_gitname(gitdir):
    cdir = os.getcwd()
    os.chdir(gitdir)
    origin_cmd = 'git remote show -n origin'
    origin = subprocess.Popen(shlex.split(origin_cmd), stdout=subprocess.PIPE).communicate()[0]
    fetch = [line for line in origin.splitlines() if 'Fetch' in line][0]
    gitname = fetch.split(':')[2]
    project = gitname.split('/')[0]
    repo = re.sub('.git$', '', gitname.split('/')[1])
    os.chdir(cdir)
    return project, repo

def get_all_gitdirs(wdir=None):
    if wdir is None: wdir = '/cluster/project/raetsch/lab/01/home/starks/rgit'
    cmd = 'find %s -name *.git' %wdir
    files, stderr = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE).communicate()
    gitdirs = [os.path.dirname(fname) for fname in files.split()]
    return gitdirs

def fetch_all_branches(tmp_repo_dir):
    fetch = subprocess.Popen([fetch_script, tmp_repo_dir], stdout=pipe)
    pass

def fetch_all_branches_old(tmp_repo_dir):
    cwd = os.getcwd()
    os.chdir(tmp_repo_dir)
    branch = subprocess.Popen(shlex.split("git branch -r"), stdout=pipe)
    grep = subprocess.Popen(shlex.split("grep -v master"), stdin=branch.stdout, stdout=pipe)
    grep_stdout = grep.communicate()[0]
    if len(grep_stdout) > 0:
        fetch_cmd = "while read remote; do git branch --track \"${remote#origin/}\" \"$remote\"; done"
        fetch = subprocess.Popen(shlex.split(fetch_cmd), stdin=pipe, stdout=pipe)
        stdout = fetch.communicate(input=grep_stout.strip())[0]
        fetch.stdout.close()
    else:
        stdout = None
    branch.stdout.close()
    grep.stdout.close()
    return stdout

def add_github_remote(repo_dir, repo_url):
    wd = os.getcwd()
    os.chdir(repo_dir)
    add = 'git remote add github %s'%repo_url
    addproc = subprocess.Popen(shlex.split(add), stdout=pipe, stderr=pipe)
    (stdout, add_stderr) = addproc.communicate()
    if len(add_stderr) > 0 and not 'remote github already exists' in add_stderr:
        os.chdir(wd)
        raise ValueError(add_stderr)
    else:
        repo_url = re.sub('^git@', '', repo_url)
        repo_url = re.sub('github.com:', 'github.com/', repo_url)
        repo_https_url = 'https://%s@%s' %(token, repo_url)
        push = 'git push --all %s'%repo_https_url
        pushproc = subprocess.Popen(shlex.split(push), stdout=pipe, stderr=pipe)
        (stdout, push_stderr) = pushproc.communicate()
        if push_stderr is not None and not '[new branch]' in push_stderr:
            os.chdir(wd)
            raise ValueError(push_stderr)
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

def get_token(gituser):
    path = '/cluster/project/raetsch/lab/01/home/starks/.github.oauth'
    token = None
    for line in open(path, 'r'):
        if line.startswith('#'): continue
        if line.split()[0].lower() == gituser.lower(): token = line.split()[1]
    return token

def delete_repository(github_repo_name, orgs=None, tkn=None):
    if tkn is None: tkn = token
    if orgs is None: orgs = org
    cmd = "curl -X DELETE -H 'Authorization: token %s' https://api.github.com/repos/%s/%s" %(tkn, orgs, github_repo_name)
    return cmd

def time():
    now = datetime.datetime.now()
    return str(now)

def update_projects(github_repo_name):
    pdb.set_trace()
    index = np.where(projects['repository'] == github_repo_name)[0]
    assert index.size == 1, "Found a duplicate project name!!"
    index = index[0]
    projects.set_value(index, 'is_added', True)
    pass

def main(debug=False):
    repo_info = projects[['clone_url', 'repository']].values
    for indx, (gitor_repo_url, github_repo_name) in enumerate(repo_info):
        print github_repo_name
        add(gitor_repo_url, github_repo_name, test=True, debug=debug)
        if (indx + 1) % 10 == 0:
            projects.to_csv(projects_path, sep='\t')

gituser='ratschlab'
org = 'ratschlab'
#gituser = 'stefangstark'
#org = 'starkstest'
token = get_token(gituser)
if token is None: raise ValueError('Token is missing')

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
        new_name = '%s-%s' %(pname, rname)
        projects.set_value(indx, 'repository', new_name)
    else:
        continue
_, project_counts = np.unique(projects['repository'].values, return_counts=True)
assert np.all(project_counts == 1), "Project names are not unique!"
if not 'is_updated' in projects.columns:
    projects['is_updated'] = pd.Series(False, index=projects.index)
projects.to_csv(projects_path, sep='\t')

if __name__ == '__main__':
    main()

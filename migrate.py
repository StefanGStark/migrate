import os
import sys
import subprocess
import json
import re
import pandas as pd
import numpy as np
import shutil
import shlex
import datetime
import stat

script_dir = os.path.dirname(os.path.abspath(__file__))

def _get_token(gituser):
    path = '/cluster/project/raetsch/lab/01/home/starks/.github.oauth'
    token = None
    for line in open(path, 'r'):
        if line.startswith('#'): continue
        if line.split()[0].lower() == gituser.lower(): token = line.split()[1]
    return token


fetch_script = os.path.join(script_dir, 'fetch_branches.sh')
logfile = sys.stdout
#logfile = open('/cluster/project/raetsch/lab/01/home/starks/git_migrate/log', 'a+', 1)
_TMP_REPO_DIR = '/cluster/project/raetsch/lab/01/home/starks/git_migrate/repo_tmp_dirs'
_TMP_GITOR_BASE = os.path.join(_TMP_REPO_DIR, 'gitor_tmp')
_TMP_GITHUB_BASE = os.path.join(_TMP_REPO_DIR, 'github_tmp')
if not os.path.exists(_TMP_REPO_DIR): os.makedirs(_TMP_REPO_DIR)

gituser ='ratschlab'
ORG = 'ratschlab'
#gituser = 'stefangstark'
#ORG = 'starkstest'
_TOKEN = _get_token(gituser)
if _TOKEN is None: raise ValueError('Token is missing')

def _authorize_github_repo(reponame):
    auth = 'https://%s@github.com/%s/%s'%(_TOKEN, ORG, reponame)
    return auth

pipe = subprocess.PIPE
projects_path ='/cluster/project/raetsch/lab/01/home/starks/git_migrate/projects.tsv'
parent_ignore = ['sandbox']

projects = _load_projects(projects_path, parent_ignore)

def del_rw(name):
    '''Super hack to delete a rw directory,
    '''
    os.system("chmod -R 777 %s" %name) # SUPER HACK -- PLEASE SOMEONE HELP
    shutil.rmtree(name)
    pass

def add(gitor_repo_url, github_repo_name, test=False, debug=False):
    '''Move a gitorios repository to github.

    Pulls repo from gitorious. Initializes new repository on github. Adds github
    repository as remote. Pushes new repository. Updates project status (pushed).
    Removes gitorious repository.
    '''
    tmp_repo_dir = None
    if test: github_repo_name = 'TEST-' + github_repo_name
    try:
        logfile.write('%s\tInitializing %s\n' %(time(), github_repo_name))
        github_url = init_github_repo(github_repo_name, debug=debug)
        logfile.write('%s\tPulling %s\n' %(time(), gitor_repo_url))
        tmp_repo_dir = pull_gitorious_repo(gitor_repo_url, debug=debug)
        logfile.write('%s\tJoining %s and %s\n' %(time(), gitor_repo_url, github_url))
        add_github_remote(tmp_repo_dir, github_url, debug=debug)
        logfile.write('%s\tJoin successful %s\n' %(time(), gitor_repo_url))
        push_github_remote(tmp_repo_dir, github_url, debug)
        logfile.write('%s\tPush successful %s\n' %(time(), gitor_repo_url))
        if test:
            github_repo_name = re.sub('^TEST-', '', github_repo_name)
        update_projects(github_repo_name)
#    except Exception as e:
#        message = str(e)
#        message = message.replace(_TOKEN, '<TOKEN>')
#        logfile.write('ERROR: %s\n' %message)
    finally:
        # always remove the tmp dir
        if tmp_repo_dir is not None:
            if os.getcwd() == tmp_repo_dir: os.chdir(os.path.expanduser('~'))
            if os.path.exists(tmp_repo_dir):
                del_rw(tmp_repo_dir)
    pass

def init_github_repo(reponame, private=True, debug=False, desc=None, gitor_repo_url=None):
    '''Initializes a repository on github.

    If the repositiory exists or something went wrong ('name' is not in the result json),
    raises a ValueError.
    '''
    repo_delim = '-'
    _test_tag = 'TEST%s' %repo_delim
    url = _name_github_url(reponame)
    if desc is None: desc = list()
    if not gitor_repo_url is None:
        cloned_text = 'Cloned from %s' %gitor_repo_url
        desc.append(cloned_text)
    nontest_reponame = re.sub('^%s'%_test_tag, '', reponame)
    if repo_delim in nontest_reponame.replace(_test_tag, ''):
        tag_desc = ' '.join(['TAG-%s'%tag for tag in nontest_reponame.split(repo_delim)[:-1]])
        desc.append(tag_desc)
    desc = '\n'.join(desc)
    init_json = "{\"name\":\"%s\",\"private\":%s,\"description\":\"%s\"}" %(reponame, str(private).lower(), desc)
    init_cmd = "curl -u %s:%s https://api.github.com/orgs/%s/repos -d '%s'"  %(gituser, _TOKEN, ORG, init_json)
    init_proc = subprocess.Popen(shlex.split(init_cmd), stdout=pipe, stderr=pipe)
    (stdout, stderr) = init_proc.communicate()
    handle_git_init_response(url, init_proc, stdout, stderr, debug=debug)
    return url

def _name_github_url(url):
    if not url.startswith('git@github.com'):
        url = 'git@github.com:%s/%s'%(ORG, url)
    if not url.endswith('.git'):
        url = url + '.git'
    return url

def _format_github_url_with_token(github_repo_url):
    if not 'github.com' in github_repo_url or ORG in github_repo_url:
        github_repo_url = _name_github_url(github_repo_url)
    if not github_repo_url.startswith('https'):
        github_repo_url = github_repo_url.split('@')[-1]
        github_repo_url = re.sub(':', '/', github_repo_url)
        github_repo_url = 'https://%s@%s' %(_TOKEN, github_repo_url)
    return github_repo_url

def _initialize_tmp_dir(tmp_dir_base):
    tmp_dir = tmp_dir_base
    count = 1
    if os.path.exists(tmp_dir):
        tmp_dir_ext = tmp_dir_base + str(count)
        while os.path.exists(tmp_dir_ext):
            count = count + 1
            tmp_dir_ext = tmp_dir_base + str(count)
        tmp_dir = tmp_dir_ext
    return tmp_dir

def github_repo_is_empty(github_repo_url, cleanup=False):
    github_repo_url = _format_github_url_with_token(github_repo_url)
    if not 'github.com' in github_repo_url and ORG in github_repo_url:
        github_repo_url = _name_github_url(github_repo_url)
    tmp_github_dir = pull_github_repo(github_repo_url, with_token=True)
    is_empty = _dir_is_empty(tmp_github_dir)
    del_rw(tmp_github_dir)
    return is_empty

def pull_github_repo(github_repo_url, with_token=True):
    if with_token:
        github_repo_url = _format_github_url_with_token(github_repo_url)
    return pull_repo(github_repo_url, _TMP_GITHUB_BASE)

def pull_gitorious_repo(gitor_repo_url):
    gitor_repo_url = format_clone_url(gitor_repo_url)
    return pull_repo(gitor_repo_url, _TMP_GITOR_BASE)

def pull_repo(repo_url, tmp_repo_base):
    '''Pulls repository into a tmp directory.
    '''
    tmp_repo_dir = _initialize_tmp_dir(tmp_repo_base)
    clone_cmd = 'git clone %s %s' %(repo_url, tmp_repo_dir)
    clone_proc = subprocess.Popen(shlex.split(clone_cmd), stdout=pipe, stderr=pipe)
    stdout, stderr = clone_proc.communicate()
    handle_generic_git_call(clone_proc, stdout, stderr)
    if not _dir_is_empty(tmp_repo_dir):
        _fetch_all_branches(tmp_repo_dir)
    return tmp_repo_dir

def add_github_remote(repo_dir, repo_url):
    '''Adds the github repository to the gitorious clone.
    '''
    wd = os.getcwd()
    os.chdir(repo_dir)
    add = 'git remote add github %s'%repo_url
    addproc = subprocess.Popen(shlex.split(add), stdout=pipe, stderr=pipe)
    (stdout, add_stderr) = addproc.communicate()
    try:
        handle_generic_git_call(addproc, stdout, add_stderr)
    finally:
        os.chdir(wd)
    pass

def push_github_remote(repo_dir, repo_url):
    '''Pushes the repository to github.
    '''
    wd = os.getcwd()
    os.chdir(repo_dir)
    repo_url = re.sub('^git@', '', repo_url)
    repo_url = re.sub('github.com:', 'github.com/', repo_url)
    repo_https_url = 'https://%s@%s' %(_TOKEN, repo_url)
    push = 'git push --all %s'%repo_https_url
    pushproc = subprocess.Popen(shlex.split(push), stdout=pipe, stderr=pipe)
    (stdout, push_stderr) = pushproc.communicate()
    try:
        handle_generic_git_call(pushproc, stdout, push_stderr)
    finally:
        os.chdir(wd)
    pass

def get_all_gitdirs(wdir=None):
    if wdir is None: wdir = '/cluster/project/raetsch/lab/01/home/starks/rgit'
    cmd = 'find %s -name *.git' %wdir
    files, stderr = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE).communicate()
    gitdirs = [os.path.dirname(fname) for fname in files.split()]
    return gitdirs

def _dir_is_empty(dirpath):
    contents = os.listdir(dirpath)
    is_empty = len(contents) == 0 or contents[0] == '.git'
    return is_empty

def _fetch_all_branches(tmp_repo_dir):
    fetch = subprocess.Popen([fetch_script, tmp_repo_dir], stdout=pipe)
    pass

def process_one_repo(gitor_repo_url, github_repo_name, private=True):
    tmp_repo_dir = pull_gitorious_repo(gitor_repo_url)
    github_url = init_github_repo(github_repo_name, private=private)
    add_github_remote(tmp_repo_dir, github_url)
    pass

def format_clone_url(clone_url):
    clone_url = clone_url.replace('git.ratschlab.org/', 'git.ratschlab.org:')
    clone_url = re.sub('^git://', '', clone_url)
    if not clone_url.startswith('git@'):
        clone_url = 'git@%s'%clone_url
    return clone_url

def delete_repository(github_repo_name, orgs=None, tkn=None):
    if tkn is None: tkn = _TOKEN
    if orgs is None: orgs = ORG
    cmd = "curl -X DELETE -H 'Authorization: token %s' https://api.github.com/repos/%s/%s" %(tkn, orgs, github_repo_name)
    return cmd

def time():
    now = datetime.datetime.now()
    return str(now)

def update_projects(github_repo_name):
    index = np.where(projects['repository'] == github_repo_name)[0]
    assert index.size == 1, "Found a duplicate project name!!"
    index = projects.iloc[index[0]].name
    projects.loc[index, 'is_updated'] = True
    pass

def main(debug=False, test=True):
    repo_info = projects[['clone_url', 'repository']].values
    for indx, (gitor_repo_url, github_repo_name) in enumerate(repo_info):
        if project_is_updated(github_repo_name): continue
        print github_repo_name
        add(gitor_repo_url, github_repo_name, test=test, debug=debug)
        if (indx + 1) % 10 == 0:
            projects.to_csv(projects_path, sep='\t')
    pass

def project_is_updated(repo_name):
    index = np.where(projects['repository'] == repo_name)[0]
    assert index.size == 1, "Found a duplicate project name!!"
    is_updated = projects.loc[index[0]]['is_updated']
    return is_updated

def list_repos(run_cmd=True):
    list_cmd = 'curl -u %s:%s https://api.github.com/orgs/%s/repos' %(gituser, _TOKEN, ORG)
    if run_cmd:
        cmd_proc = subprocess.Popen(shlex.split(list_cmd), stdout=pipe, stderr=pipe)
        (stdout, list_stderr) = cmd_proc.communicate()
        data = json.loads(stdout)
        return data
    return list_cmd

def _load_projects(projects_path, parent_ignore):
    projects = pd.read_csv(projects_path, sep='\t')
    projects.set_index('id', inplace=True)
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
    return projects

class RepositoryExists(Exception):
    def __init__(self, value):
        self.value = value
        pass

    def __str__(self):
        return repr(self.value)

def _error_flag(result):
    flag = 'documentation_url' in result and 'message' in result or 'errors' in result
    return flag

def handle_generic_git_call(proc, stdout=None, stderr=None, debug=False):
    '''Handle the output of a git command, e.g. git pull ...
    '''
    if proc.returncode < 0:
        msg = 'git command failed'
        if stdout is not None:
            msg = msg + '\nstdout: %s' %stdout
        if stderr is not None:
            msg = msg + '\nstderr: %s' %stderr
        raise ValueError('git command failed')
    pass

def handle_git_init_response(github_url, proc, stdout, stderr=None, debug=False):
    '''Handles the output of a repositoty init call from the git API.

    Throws ValueError if repository was not initialized.
    Command:
        curl -u USER:PASS https://api.github.com/orgs/ORG/repos -d INIT_JSON
    Response:
        https://developer.github.com/v3/repos/#create
    '''
    result = json.loads(stdout)
    if proc.returncode < 0:
        raise ValueError(result)
    if _error_flag(result):
        has_error = 'errors' in result
        exit_msg = 'name already exists on this account'
        if has_error and exit_msg in result['errors'][0]['message']:
            if not github_repo_is_empty(github_url):
                raise RepositryExists(github_url)
        else:
            raise ValueError(result)
    pass

if __name__ == '__main__':
    main()

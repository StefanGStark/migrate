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
import pdb
import glob

script_dir = os.path.dirname(os.path.abspath(__file__))

def _get_token(gituser):
    path = '/cluster/project/raetsch/lab/01/home/starks/.github.oauth'
    token = None
    for line in open(path, 'r'):
        if line.startswith('#'): continue
        if line.split()[0].lower() == gituser.lower(): token = line.split()[1]
    return token


fetch_script = os.path.join(script_dir, 'fetch_branches.sh')
comp_dir_script = os.path.join(script_dir, 'comp_dirs.sh')
#logfile = sys.stdout
logfile = open('/cluster/project/raetsch/lab/01/home/starks/git_migrate/log', 'a+', 1)
_TMP_REPO_DIR = '/cluster/project/raetsch/lab/01/home/starks/git_migrate/repo_tmp_dirs'
_TMP_GITOR_BASE = os.path.join(_TMP_REPO_DIR, 'gitor_tmp')
_TMP_GITHUB_BASE = os.path.join(_TMP_REPO_DIR, 'github_tmp')
if not os.path.exists(_TMP_REPO_DIR): os.makedirs(_TMP_REPO_DIR)

_CONFIRMED_FINISHED_COL = 'confirmed_finished'

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

projects = _load_projects(projects_path, parent_ignore)

def del_rw(name):
    '''Super hack to delete a rw directory,
    '''
    os.system("chmod -R 777 %s" %name) # SUPER HACK -- PLEASE SOMEONE HELP
    shutil.rmtree(name)
    pass

def _write_to_log(msg):
    msg = msg.replace(_TOKEN, '<TOKEN>')
    logfile.write('%s\t%s' %(time(), msg))
    pass

def add(gitor_repo_url, github_repo_name, test=False):
    '''Move a gitorios repository to github.

    Pulls repo from gitorious. Initializes new repository on github. Adds github
    repository as remote. Pushes new repository. Updates project status (pushed).
    Removes gitorious repository.

    Commands:
        Initialize github repository:
             curl -u $USR:$TKN https://api.github.com/orgs/%s/repos \\
                 -d {"name":"$REPONAME","private":true, "description":"$REPODESC"}
        Pull gitor repo:
            git clone $GITOR_URL $GITOR_REPO_DIR
        Add remote to gitor repo:
            git remote ad github $GITHUB_URL
        Push github repo:
            git push --all https://$TKN@github.com/$GITHUB_NAME
    '''
    tmp_repo_dir = None
    if test: github_repo_name = 'TEST-' + github_repo_name
    print github_repo_name
    try:
        _write_to_log('Initializing %s\n' %(github_repo_name))
        github_url = init_github_repo(github_repo_name)
        _write_to_log('Pulling %s\n' %(gitor_repo_url))
        tmp_repo_dir = pull_gitorious_repo(gitor_repo_url)
        fix_large_files_and_symlinks(tmp_repo_dir)
        _write_to_log('Joining %s and %s\n' %(gitor_repo_url, github_url))
        add_github_remote(tmp_repo_dir, github_url)
        _write_to_log('Join successful %s\n' %(gitor_repo_url))
        push_github_remote(tmp_repo_dir, github_url)
        _write_to_log('Push successful %s\n' %(gitor_repo_url))
        if test:
            github_repo_name = re.sub('^TEST-', '', github_repo_name)
        update_projects(github_repo_name)
    except Exception as e:
        message = str(e)
        message = message.replace(_TOKEN, '<TOKEN>')
        _write_to_log('ERROR: %s\n' %message)
    finally:
        # always remove the tmp dir
        if tmp_repo_dir is not None:
            if os.getcwd() == tmp_repo_dir: os.chdir(os.path.expanduser('~'))
            if os.path.exists(tmp_repo_dir):
                del_rw(tmp_repo_dir)
        projects.to_csv(projects_path, sep='\t')
    pass

def init_github_repo(reponame, private=True, desc=None, gitor_repo_url=None):
    '''Initializes a repository on github.

    If the repositiory exists or something went wrong ('name' is not in the result json),
    raises a ValueError.
    '''
    repo_delim = '-'
    _test_tag = 'TEST%s' %repo_delim
    github_url = _name_github_url(reponame)
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
    _write_to_log('\tCOMMAND: ' + init_cmd + '\n')
    init_proc = subprocess.Popen(shlex.split(init_cmd), stdout=pipe, stderr=pipe)
    (stdout, stderr) = init_proc.communicate()
    handle_git_init_response(github_url, init_proc, stdout, stderr)
    return github_url

def _name_github_url(url, test_name=False):
    if not url.startswith('git@github.com'):
        if test_name:
            url = 'TEST-' + url
        url = 'git@github.com:%s/%s'%(ORG, url)
    if not url.endswith('.git'):
        url = url + '.git'
    return url

def _format_github_url_with_token(github_repo_url, test_name=False):
    if not 'github.com' in github_repo_url or ORG in github_repo_url:
        github_repo_url = _name_github_url(github_repo_url, test_name)
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

def pull_github_repo(github_repo_url, with_token=True, test_name=False, dirname=None):
    if dirname is None: dirname = _TMP_GITHUB_BASE
    if with_token:
        github_repo_url = _format_github_url_with_token(github_repo_url, test_name=test_name)
    return pull_repo(github_repo_url, dirname)

def pull_gitorious_repo(gitor_repo_url, dirname=None):
    if dirname is None: dirname = _TMP_GITOR_BASE
    gitor_repo_url = format_clone_url(gitor_repo_url)
    return pull_repo(gitor_repo_url, dirname)

def pull_repo(repo_url, tmp_repo_base):
    '''Pulls repository into a tmp directory.
    '''
    tmp_repo_dir = _initialize_tmp_dir(tmp_repo_base)
    clone_cmd = 'git clone %s %s' %(repo_url, tmp_repo_dir)
    _write_to_log('\tCOMMAND: ' + clone_cmd + '\n')
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
    add_cmd = 'git remote add github %s'%repo_url
    _write_to_log('\tCOMMAND: ' + add_cmd + '\n')
    addproc = subprocess.Popen(shlex.split(add_cmd), stdout=pipe, stderr=pipe)
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
    push_cmd = 'git push --all %s'%repo_https_url
    _write_to_log('\tCOMMAND: ' + push_cmd + '\n')
    pushproc = subprocess.Popen(shlex.split(push_cmd), stdout=pipe, stderr=pipe)
    (stdout, push_stderr) = pushproc.communicate()
    pdb.set_trace()
    try:
        handle_generic_git_call(pushproc, stdout, push_stderr)
    finally:
        os.chdir(wd)
    pass

def _find_failed_dirs_wo_symlinks():
    large_files = dict()
    symlinks = dict()
    failed_basedir = '/cluster/project/raetsch/lab/01/home/starks/git_migrate/repo_tmp_dirs/failed_repos'
    failed_repos = glob.glob(os.path.join(failed_basedir, '*', 'gitor'))
    for dname in failed_repos:
        lfs, links = _find_large_files(dname)
        if len(lfs) > 0:
            large_files[dname] = lfs
        if len(links) > 0:
            symlinks[dname] = links
    return large_files, symlinks

def find_large_files_and_symlinks(repo_dir):
    repo_dir = os.path.abspath(repo_dir)
    size_limit = 50 * 1024 * 1024
    large_files = list()
    symlinks = list()
    for (path, dirs, files) in os.walk(repo_dir):
        for fname in files:
            full_path = os.path.join(path, fname)
            if os.path.islink(full_path):
                symlinks.append(full_path)
            elif os.path.getsize(full_path) >= size_limit:
                large_files.append(full_path)
    return large_files, symlinks

def fix_large_files_and_symlinks(repo_dir):
    large_files, symlinks = find_large_files_and_symlinks(repo_dir)
    if len(symlinks) > 0:
        raise ValueError('Symlinks found in %s' %repo_dir)
    if len(large_files) > 0:
        git_lfs_add(repo_dir, large_files)
    pass

def git_lfs_add(repo_dir, large_files):
    cwd = os.getcwd()
    os.chdir(repo_dir)
    try:
        cmd = 'git lfs track %s' %' '.join(large_files)
        _write_to_log('\tCOMMAND: ' + cmd + '\n')
        proc = subprocess.Popen(shlex.split(cmd), stdout=pipe, stderr=pipe)
        (stdout, stderr) = proc.communicate()
        print cmd
        print stdout, stderr
        handle_generic_git_call(proc, stdout, stderr)
    finally:
        os.chdir(cwd)
    pass

def get_all_gitdirs(wdir=None):
    if wdir is None: wdir = '/cluster/project/raetsch/lab/01/home/starks/rgit'
    cmd = 'find %s -name *.git' %wdir
    files, stderr = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE).communicate()
    gitdirs = [os.path.dirname(fname) for fname in files.split()]
    return gitdirs

def _dir_is_empty(dirpath):
    if not os.path.exists(dirpath): os.makedirs(dirpath)
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

def main(test=True):
    repo_info = projects[['clone_url', 'repository']].values
    for indx, (gitor_repo_url, github_repo_name) in enumerate(repo_info):
        if project_is_updated(github_repo_name): continue
        print github_repo_name
        add(gitor_repo_url, github_repo_name, test=test)
    pass

def project_is_updated(repo_name):
    index = np.where(projects['repository'] == repo_name)[0]
    assert index.size == 1, "Found a duplicate project name!!"
    is_updated = projects.loc[index[0]]['is_updated']
    return is_updated

def _get_num_repo_pages(per_page=100):
    header_cmd = 'curl -Iu %s:%s https://api.github.com/orgs/%s/repos?per_page=%d' %(gituser, _TOKEN, ORG, per_page)
    header_proc = subprocess.Popen(shlex.split(header_cmd), stdout=pipe, stderr=pipe)
    (stdout, stderr) = header_proc.communicate()
    link_info = [line for line in stdout.splitlines() if line.lower().startswith('link')][0].split()
    index = [indx for indx, phrase in enumerate(link_info) if phrase == 'rel="last"'][0] - 1
    page_info = link_info[index]
    match = re.search('=[0-9]*>;$', page_info)
    num_pages = int(page_info[match.start(): match.end()][1:-2])
    return num_pages

def list_repos(per_page=100):
    data = list()
    num_pages = _get_num_repo_pages(per_page) + 1
    for pgnum in range(num_pages):
        list_cmd = 'curl -u %s:%s https://api.github.com/orgs/%s/repos?per_page=%d&page=%d' %(gituser, _TOKEN, ORG, per_page, pgnum)
        cmd_proc = subprocess.Popen(shlex.split(list_cmd), stdout=pipe, stderr=pipe)
        (stdout, list_stderr) = cmd_proc.communicate()
        data.extend(json.loads(stdout))
    return data

class RepositoryExists(Exception):
    def __init__(self, value):
        self.value = value
        pass

    def __str__(self):
        return repr(self.value)

class RepositoriesSame(Exception):
    def __init__(self, value):
        self.value = value
        pass

    def __str(self):
        return repr(self.value)

def _error_flag(result):
    flag = 'documentation_url' in result and 'message' in result or 'errors' in result
    return flag

def handle_generic_git_call(proc, stdout=None, stderr=None):
    '''Handle the output of a git command, e.g. git pull ...
    '''
    error_flag = False
    if (stderr is not None and len(stderr) > 0) or (stdout is not None and len(stdout) > 0):
        print "stderr: %s" %stderr
        print "stdout: %s" %stdout
    if stderr is not None and ('is not a git command' in stderr or stderr.startswith('Invalid')):
        error_flag = True
    if proc.returncode < 0 or error_flag:
        msg = 'git command failed'
        if stdout is not None and len(stdout) > 0:
            msg = msg + '\nstdout: %s' %stdout
        if stderr is not None and len(stderr) > 0:
            msg = msg + '\nstderr: %s' %stderr
        raise ValueError(msg)
    pass

def handle_git_init_response(github_url, proc, stdout, stderr=None):
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
                _write_to_log('repository was initialized, but was empty\n')
        else:
            raise ValueError(result)
    pdb.set_trace()
    pass

def gitor_and_github_are_same(gitor_tmp_dir, github_repo_name):
    github_tmp_dir = pull_github_repo(github_repo_name)
    res = _dir_are_same(gitor_tmp_dir, github_tmp_dir)
    return res

def _filter_diff_stdout(stdout):
    filter_stdout = list()
    for line in stdout.splitlines():
        if not re.match('^[><]', line): continue
        if re.match('^[><] ./.git', line): continue
        filter_stdout.append(line)
    filter_stdout = '\n'.join(filter_stdout)
    return filter_stdout

def _dir_are_same(dira, dirb, ret_output=False):
    fetch = subprocess.Popen([comp_dir_script, dira, dirb], stdout=pipe, stderr=pipe)
    stdout, stderr = fetch.communicate()
    stdout = _filter_diff_stdout(stdout)
    assert len(stderr) == 0
    res = len(stdout) == 0
    if ret_output:
        return res, stdout, stderr
    return len(stdout) == 0

def _add_conf_col():
    projects[_CONFIRMED_FINISHED_COL] = pd.Series(None, index=projects.index)
    pass

def _check_single_repo(github_repo_name, gitor_repo_url, debug=False):
    try:
        github_dir = pull_github_repo(github_repo_name, test_name=True)
        gitor_dir = pull_gitorious_repo(gitor_repo_url)
        res = _dir_are_same(github_dir, gitor_dir, ret_output=True)
        if debug:
            print github_dir
            print gitor_dir
    finally:
        if not debug:
            del_rw(github_dir)
            del_rw(gitor_dir)
    return res

def get_repo_info(index=None):
    if index is None: index = np.random.randint(projects.shape[0])
    row = projects.iloc[index]
    github_repo_name = row['repository']
    gitor_repo_url = row['clone_url']
    return github_repo_name, gitor_repo_url

def check_results():
    failed_repo_dir = '/cluster/project/raetsch/lab/01/home/starks/git_migrate/repo_tmp_dirs/failed_repos'
    if not os.path.exists(failed_repo_dir): os.makedirs(failed_repo_dir)
    failures = list()
    if not _CONFIRMED_FINISHED_COL in projects.columns:
        _add_conf_col()
    for _, row in projects.iterrows():
        if not row['repository'] == 'projects2014-wordreps': continue
        print row['repository']
        if not row['is_updated'] or row[_CONFIRMED_FINISHED_COL]: continue
        indx = row.name
        github_repo_name = row['repository']
        gitor_repo_url = row['clone_url']
        res, stdout, stderr = _check_single_repo(github_repo_name, gitor_repo_url, True)
        print github_repo_name, res
        print "gitor repo url: %s" %gitor_repo_url
        print stdout
        print '\n'
        projects.loc[indx, _CONFIRMED_FINISHED_COL] = res
        projects.to_csv(projects_path, sep='\t')
        if not res:
            failures.append((github_repo_name, gitor_repo_url, stdout, stderr))
            basedir = os.path.join(failed_repo_dir, github_repo_name)
            github_dir =  os.path.join(basedir, 'github')
            gitor_dir =  os.path.join(basedir, 'gitor')
            if not os.path.exists(github_dir): pull_github_repo(github_repo_name, test_name=True, dirname=github_dir)
            if not os.path.exists(gitor_dir): pull_gitorious_repo(gitor_repo_url, dirname=gitor_dir)
    return failures

def get_unfinished_details():
    unfinished_indxs = [indx for indx,x in enumerate(projects[_CONFIRMED_FINISHED_COL].values) if not x]
    data = projects.iloc[unfinished_indxs][['repository', 'clone_url']].values
    with_github_url = [(repo_name, gitor_url, _name_github_url(repo_name)) for repo_name, gitor_url in data]
    return data


def write_unfinished_details():
    data = get_unfinished_details()
    outfile = os.path.join(script_dir, 'unfinished_repo_info.txt')
    np.savetxt(outfile, data, fmt='%s', delimiter='\t')
    pass

def write_unfinished_logs():
    unfinished_logdir = os.path.join(_TMP_REPO_DIR, 'logs')
    if not os.path.exists(unfinished_logdir): os.makedirs(unfinished_logdir)
    unfinished_indxs = [indx for indx,x in enumerate(projects[_CONFIRMED_FINISHED_COL].values) if not x]
    for github_repo, gitor_url in projects.iloc[unfinished_indxs][['repository', 'clone_url']].values:
        print github_repo
        github_dir_name = os.path.join(os.path.dirname(_TMP_GITHUB_BASE), 'github', github_repo)
        gitor_dir_name = os.path.join(os.path.dirname(_TMP_GITOR_BASE), 'gitor', github_repo)
        if not os.path.exists(os.path.dirname(github_dir_name)): os.makedirs(os.path.dirname(github_dir_name))
        if not os.path.exists(os.path.dirname(gitor_dir_name)): os.makedirs(os.path.dirname(gitor_dir_name))
        if not os.path.exists(github_dir_name):
            github_dir = pull_github_repo(github_repo, test_name=True, dirname=github_dir_name)
        else:
            github_dir = github_dir_name
        if not os.path.exists(gitor_dir_name):
            gitor_dir = pull_gitorious_repo(gitor_url, dirname=gitor_dir_name)
        else:
            gitor_dir = gitor_dir_name
        res, stdout, stderr = _dir_are_same(github_dir, gitor_dir, ret_output=True)
        with open(os.path.join(unfinished_logdir, github_repo + '.log'), 'w') as logout:
            logout.write(stdout + '\n')
    pass

def du(path):
    return int(subprocess.check_output(['du', '-s', path]).split()[0])

def is_too_big(gitor_repo_dir):
    size = du(gitor_repo_dir)
    return float(size) / (1024 * 1024) >= 1

if __name__ == '__main__':
    main()

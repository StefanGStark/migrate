import os
import sys
import subprocess
import shlex
import migrate as mig
import numpy as np

SCRIPT_DIR = os.path.dirname(__file__)
PIPE = subprocess.PIPE

def get_map_gitor_to_github():
    map_gitor_to_github = dict()
    mask = mig.projects['confirmed_finished'] == True
    for repo_name, gitor_url in mig.projects[mask][['repository', 'clone_url']].values:
        gitor_url = mig.format_clone_url(gitor_url)
        github_url = mig._name_github_url(repo_name)
        map_gitor_to_github[gitor_url] = github_url
    blacklist = [mig.format_clone_url(url) for url in mig.projects[np.invert(mask)]['clone_url'].values]
    return map_gitor_to_github, blacklist

def get_all_gitdirs(wdir=None):
    if wdir is None: os.path.expanduser('~')
    cmd = 'find %s -name *.git' %wdir
    files, stderr = subprocess.Popen(shlex.split(cmd), stdout=subprocess.PIPE).communicate()
    gitdirs = [os.path.dirname(fname) for fname in files.split()]
    return gitdirs

def get_remote_info(gitdir=None):
    if not gitdir is None: os.chdir(gitdir)
    cmd = 'git remote -v'
    proc = subprocess.Popen(shlex.split(cmd), stdout=PIPE, stderr=PIPE)
    (stdout, stderr) = proc.communicate()
    #print "COMMAND: %s\nSTDOUT:\n\t%s" %(cmd, stdout.replace('\n', '\n\t'))
    map_url_to_remote_name = _extract_remote_info(stdout)
    return map_url_to_remote_name

def _extract_remote_info(stdout):
    '''Extracts the git url and remote label from git remote stdout.
    '''
    remote_info = dict()
    if stdout is None or len(stdout) == 0:
        return
    for line in stdout.splitlines():
        remote_name, url, _ = line.split()
        remote_info[url] = remote_name
    return remote_info

def _change_single_remote(url, remote_name):
    try:
        github_url = _MAP_GITOR_TO_GITHUB[url]
    except KeyError:
        return
    else:
        cmd = 'git remote set-url %s %s' %(remote_name, github_url)
        oldcmd = 'git remote add %s %s' %('gitor_' + remote_name, url)
        proc = subprocess.Popen(shlex.split(cmd), stdout=PIPE, stderr=PIPE)
        (stdout, stderr) = proc.communicate()
        oldproc = subprocess.Popen(shlex.split(oldcmd), stdout=PIPE, stderr=PIPE)
        (oldstdout, oldstderr) = oldproc.communicate()
    pass

def update_single_git(gitdir):
    ''' Changes remote from gitor to github

    If gitdir has a remote on gitor that has been moved to github, change
    the remote url to the github url, add a new remote to back up the gitor url
    '''
    cwd = os.getcwd()
    os.chdir(gitdir)
    try:
        remote_info = get_remote_info()
        for url, remote_name in remote_info.iteritems():
            if url in _BLACKLIST:
                print "WARNING: %s is blacklisted" %url
            else:
                _change_single_remote(url, remote_name)
    finally:
        os.chdir(cwd)
    pass

_MAP_GITOR_TO_GITHUB, _BLACKLIST = get_map_gitor_to_github()

if __name__ == '__main__':
    wdir = sys.argv[1] if len(sys.argv) > 1 else None
    gitdirs = get_all_gitdirs(wdir)
    for gdir in gitdirs:
        update_single_git(gdir)
        _ = get_remote_info(gdir)


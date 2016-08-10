import os
import sys
import json

class RepositoryExists(Exception):
    def __init__(self, value):
        self.value = value
        pass

    def __str__(self):
        return repr(self.value)

def _error_flag(result):
    flag = 'documentation_url' in result and 'message' in result or 'errors' in result
    return flag

def generic_git_call(proc, stdout=None, stderr=None, debug=False):
    if proc.returncode < 0:
        msg = 'git command failed'
        if stdout is not None:
            msg = msg + '\nstdout: %s' %stdout
        if stderr is not None:
            msg = msg + '\nstderr: %s' %stderr
        raise ValueError('git command failed')
    pass

def git_init_response(proc, stdout, stderr=None, debug=False):
    '''Handles the output of a git init call.

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
        exist_msg = 'name already exists on this account'
        if has_error and exist_msg in result['errors'][0]['message']:
            raise RepositoryExists(result)
        else:
            raise ValueError(result)
    pass


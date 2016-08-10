import os
import sys
import xml.etree.ElementTree
import pandas as pd
import re

# Converts projects.xml into a tsv where rows are repositiories, columns are
# properties, including project & team information 

_ORG_DOMAIN = 'git.ratschlab.org/'

def name_repo(clone_url):
    res = re.search(_ORG_DOMAIN, clone_url)
    name = clone_url[res.end():]
    name = re.sub('.git$', '', name)
    name = re.sub('-', '_', name)
    name = re.sub('/', '-', name)
    name = re.sub('~', '', name)
    return name

path = '/cluster/project/raetsch/lab/01/home/starks/git_migrate/projects.xml'
outpath = path.replace('.xml', '.tsv')
tree = xml.etree.ElementTree.parse(path)
root = tree.getroot()

cols = ['id', 'repository', 'owner', 'team', 'parent', 'parent_desc', 'clone_url', 'lisc']
entries = list()

indx = 0
for project in root.getchildren():
    parent = project.find('title').text
    desc = project.find('description').text
    lisc = project.find('license').text
    team = project.find('owner').text
    date = project.find('created-at').text
    print parent
    for repo in project.iter('repository'):
        _id = str(indx)
        indx = indx + 1
        owner = repo.find('owner').text
        clone_url = repo.find('clone_url').text
        name = name_repo(clone_url)
        row = [_id, name, owner, team, parent, desc, clone_url, lisc]
        entries.append([ent.replace('\t', ' ') for ent in row])
        print '\t%s' %name

df = pd.DataFrame(entries, columns=cols)
df.set_index('id', inplace=True)
df.to_csv(outpath, sep='\t')

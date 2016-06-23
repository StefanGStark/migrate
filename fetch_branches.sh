#!/bin/bash

wdir=$1
cd $wdir

git branch -r | grep -v master | while read remote
do
    git branch --track "${remote#origin/}" "$remote"
done

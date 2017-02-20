#!/bin/bash

DIR=/home/$(whoami)/uploader
source $DIR/.env
$DIR/venv/bin/python3 $DIR/notify.py > $DIR/notifier.log 2>&1

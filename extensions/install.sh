#!/bin/bash
EXT_DIR=~/.local/share/ulauncher/extensions
mkdir -p $EXT_DIR
rm -rf $EXT_DIR/fd
cp -r ./fd $EXT_DIR/

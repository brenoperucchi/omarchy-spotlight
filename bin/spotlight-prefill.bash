#!/bin/bash
# Loaded via `bash --rcfile` by Spotlight's "Open in terminal". $1 is the
# command to place on the prompt, unexecuted, so it can still be edited.
#
# Readline has no "prefill" hook, so the terminal is asked for a Device Status
# Report; its reply (ESC[0n) arrives as keyboard input at the first prompt and
# the binding on that sequence moves the command onto the line.
# ponytail: bash only; zsh (print -z) and fish (commandline) when asked for.
[[ -f ~/.bashrc ]] && source ~/.bashrc
SPOTLIGHT_PREFILL=$1
shift
bind -x '"\e[0n": READLINE_LINE=$SPOTLIGHT_PREFILL; READLINE_POINT=${#READLINE_LINE}; unset SPOTLIGHT_PREFILL; bind -r "\e[0n"'
printf '\e[5n'

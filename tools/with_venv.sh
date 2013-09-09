#!/bin/bash

set -e

me=${0##*/}
dir="$(dirname $0)"

function print_usage() {
  cat >&2 <<EOS
Run commands in a default (or specific) virtualenv

Usage: $me [-E venv] commands

Options:
  -h        prints out this message
  -E venv   use this virtualenv (default: ${venv})
EOS
}

venv="${dir}/../.venv"

while getopts ":hE:" opt; do
  case "$opt" in
    h|\?) print_usage; exit 1 ;;
    E) venv=$OPTARG ;;
  esac
done
shift $((OPTIND-1))

source "${venv}/bin/activate" && "$@"

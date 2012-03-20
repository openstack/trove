#!/bin/sh

# Define the various templates
MEMSIZE=( "512M:1" "1G:2" "2G:4" "4G:8" "8G:16" "16G:32" "32G:64" )

# Create the individual templates from the master template
for i in "${MEMSIZE[@]}"; do
    key=${i%%:*}
    multiplier=${i##*:}
    cat ../etc/my.cnf.base | while read line; do
        if [[ `expr "$line" : ".*{.*}"` != "0" ]]; then
            oldval=`echo $line | sed -e 's/.*{\(.*\)}.*/\1/'`
            newval=`echo "$oldval * $multiplier" | bc`
            line=`echo $line | sed -e "s/{$oldval}/$newval/"`
        fi
        echo $line >> etc/my.cnf.$key
    done
done


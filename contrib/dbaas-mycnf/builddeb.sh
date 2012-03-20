#!/bin/bash
# Build the debian package for my.cnf templates

# chdir to the script dir
self="${0#./}"
base="${self%/*}"
current=`pwd`

if [ "$base" = "$self" ] ; then
    home=$current
elif [[ $base =~ ^/ ]]; then
    home="$base"
else
    home="$current/$base"
fi

cd $home

# Setup the build directory for building the package
build_dir="build"
rm -rf $build_dir
mkdir -p $build_dir
cp -R debian $build_dir
cp -R etc $build_dir

cd $build_dir

# Define the various templates
MEMSIZE=( "512M:1" "1024M:2" "2048M:4" "4096M:8" "8192M:16" "16384M:32" "32768M:64" )

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

# Build the package
DEB_BUILD_OPTIONS=nocheck,nodocs dpkg-buildpackage -rfakeroot -b -uc -us -d

# sometimes the primary key server is unavailable and we should try an
# alternate.  see
# https://bugs.launchpad.net/percona-server/+bug/907789.  Disable
# shell errexit so we can interrogate the exit code and take action
# based on the exit code. We will reenable it later.
#
# NOTE(zhaochao): we still have this problem from time to time, so it's
# better use more reliable keyservers and just retry on that(for now, 3
# tries should be fine).
# According to:
# [1] https://www.gnupg.org/faq/gnupg-faq.html#new_user_default_keyserver
# [2] https://sks-keyservers.net/overview-of-pools.php
# we'll just the primary suggested pool: pool.sks-keyservers.net.
function get_key_robust() {
    KEY=$1
    set +e

    tries=1
    while [ $tries -le 3 ]; do
        if [ $tries -eq 3 ]; then
            set -e
        fi

        echo "Importing the key, try: $tries"
        apt-key adv --keyserver hkp://pool.sks-keyservers.net \
            --recv-keys ${KEY} && break

        tries=$((tries+1))
    done

    set -e
}

export -f get_key_robust

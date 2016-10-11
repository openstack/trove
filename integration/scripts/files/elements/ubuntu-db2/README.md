 Creates an image for DB2 Express-C v10.5

 The packages for DB2 Express-C can be downloaded from:
 http://www-01.ibm.com/software/data/db2/express-c/download.html
 and click on the link "DB2 Express-C for Linux 64-bit".
 New users can either get an IBM ID or click on the "Proceed without an
 IBM ID". User is provided with a registration form which needs to be
 completed in order to proceed further to download the DB2 Express-C
 packages. After accepting the license agreement, user can download the
 the DB2 Express-C package (.tar.gz file).

 There are 2 options for making the DB2 Express-C package accessible to
 the Trove disk-image building process:
  - place the package in a private repository and set the environment
    variable DATASTORE_PKG_LOCATION with the url to this private
    repository.
    e.g. export DATASTORE_PKG_LOCATION="http://www.foo.com/db2/v10.5_linuxx64_expc.tar.gz"

  - download the package and place it in any directory on the local
    filesystem that the trovestack script can access. Set the
    environment variable DATASTORE_PKG_LOCATION with the full path to
    the downloaded package.
    e.g. export DATASTORE_PKG_LOCATION="/home/stack/db2/v10.5_linuxx64_expc.tar.gz"

 The environment variables used are as follows:

 DATASTORE_PKG_LOCATION - is the place where user stores the DB2
             Express-C package after registration. This can either be a
             url to a private repository or the full path to the
             downloaded package on a local filesystem.
 DATASTORE_DOWNLOAD_OPTS - defines any wget options user wants to specify
             like user,password, etc. This is an optional variable and is
             needed only if specifying a private repository to download
             the packages from.
    e.g. export DATASTORE_DOWNLOAD_OPTS="--user=foo --password='secret'"


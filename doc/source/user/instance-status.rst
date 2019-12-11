========================
Database instance status
========================

HEALTHY
  The database service is functional, e.g. table is accessible.

RUNNING
  The database service is alive, but maybe not functional yet.

SHUTDOWN
  The database service is stopped.

NEW
  The database service creation request is just received by Trove.

BUILD
  The database service is being installed.

BLOCKED
  The database service process exists but service is not accessible for some
  reason.

PROMOTE
  Trove is replicating data between a replication group in order to promote a
  new master instance.

EJECT
  The master election is happening within a replication group.

RESTART_REQUIRED
  The database service needs to restart, e.g. due to the configuration change.

FAILED
  The database service is failed to spawn.

ERROR
  There are some errors in a running database service.

DELETED
  The database service is deleted.

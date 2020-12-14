========================
Database instance status
========================

Trove is maintaining two types of status, named ``status`` and ``operating_status``.

``status`` is reflecting the trove instance VM status and instance task status, e.g. after successfully creating a trove instance, the ``status`` is ``ACTIVE``, when doing backup, the ``status`` is ``BACKUP``, etc.

``operating_status`` is the actual database status inside the trove instance, trove guest agent is actively monitoring the database status and reporting back to trove, e.g. when MySQL service is up and running, the ``operating_status`` should be ``HEALTHY``, if MySQL service is not running for some reason, the ``operating_status`` is ``SHUTDOWN``.

The possible values for ``status`` are:

NEW
  The database instance creation request is just received by Trove.

BUILD
  The database instance is being installed.

ACTIVE
  The database instance is up and running.

REBOOT
  The database instance is rebooting.

RESIZE
  The database instance is being resized.

UPGRADE
  The database instance is upgrading its datastore, e.g. from mysql 5.7.29 to mysql 5.7.30

RESTART_REQUIRED
  The database service needs to restart, e.g. due to the configuration change.

PROMOTE
  A replica instance in the replication cluster is being promoted to the primary.

EJECT
  The current primary instance in a replication cluster is being ejected, one of the replicas is going to be elected as the new primary.

DETACH
  One of the replicas in a replication cluster is being detached and will become a standalone instance.

SHUTDOWN
  The database instance is being shutdown during deletion.

BACKUP
  The database instance is being backed up.

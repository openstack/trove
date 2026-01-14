.. _database_management:

===================
Database Management
===================

PostgreSQL
----------

WAL(Write Ahead Log)
~~~~~~~~~~~~~~~~~~~~

By default, ``archive_mode`` is enabled in order to create incremental database backup, which is triggered by the users. ``archive_command`` is configured as well for continuous WAL archiving, the WAL files in pg_wal subdirectory are copied to ``/var/lib/postgresql/data/wal_archive``.

That is going to be a problem if the WAL segment files in the archive folder keep increasing, especially in the busy system, several TBs of WALs can be piled up in archive destination(part of the data volume), which will lead to the database service unavailable.

In the PostgreSQL manager of trove-guestagent, there is a periodic task aiming at cleaning up the archive folder, when it's running, it checks the size of the archive folder, if the size is greater than ``max_wal_size * WAL_SAFETY_FACTOR``:
1. If there is no ``.backup`` file, it means the database has never been backed up before, all the WAL segment files except for the latest one are removed.
2. If there are ``.backup`` files, remove all the files older than the backup file. Check the size again, if the size condition is still met, all the WAL segment files except for the latest one are removed.
By default, ``WAL_SAFETY_FACTOR = 5``.

As an alternative, you can override default behavior by modifying ``archive_command`` value by trove's configuration or setting ``ALTER SYSTEM SET archive_command '<value>'`` to command:
``echo DISABLE_TROVE_WAL_CLEANUP > /dev/null && find /var/lib/postgresql/data/wal_archive/ -type f -mtime +7 -delete && test ! -f /var/lib/postgresql/data/wal_archive/%f && cp %p /var/lib/postgresql/data/wal_archive/%f``

In the example above, the ``echo DISABLE_TROVE_WAL_CLEANUP  > /dev/null`` part tells trove to disable it's default wal archive cleanup routine. In addition, the part ``find /var/lib/postgresql/data/wal_archive/ -type f -mtime +7 -delete``, will automatically remove wal files older than 7 days.

WAL and incremental backups
~~~~~~~~~~~~~~~~~~~~~~~~~~~

When creating the incremental backup, trove will check if the parent backup file still exists in the archive folder, the backup creation will fail if that's not found. The user is able to see the error message in the instance detail and has to create full backup instead.

Another option is to archive WAL files to Swift(in the user's account), e.g. using WAL-G or other 3rd party tools, but that will incur charges for the object storage usage which is not optimal. We leave it to the users to decide when and how the backups should be created.

from reddwarf.guestagent.backup.backupagent import BackupAgent

AGENT = BackupAgent()


def backup(context, backup_id):
    """
    Main entry point for starting a backup based on the given backup id.  This
    will create a backup for this DB instance and will then store the backup
    in a configured repository (e.g. Swift)

    :param context:     the context token which contains the users details
    :param backup_id:   the id of the persisted backup object
    """
    return AGENT.execute_backup(context, backup_id)


def restore(context, backup_id, restore_location):
    """
    Main entry point for restoring a backup based on the given backup id.  This
    will transfer backup data to this instance an will carry out the
    appropriate restore procedure (eg. mysqldump)

    :param context:     the context token which contains the users details
    :param backup_id:   the id of the persisted backup object
    """
    return AGENT.execute_restore(context, backup_id, restore_location)

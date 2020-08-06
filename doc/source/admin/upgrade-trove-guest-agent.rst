=========================
Trove guest agent upgrade
=========================

Normally, during Trove service upgrade, a new guest image needs to be rebuilt and used to rebuild the guest instance when the interfaces between Trove controller and guest agent change. Otherwise, the newer version Trove controller can't talk to the older version guest agent.

Prior to Victoria release, the process to upgrade guest agent is:

#. The cloud administrator builds a new guest image based on the target Trove code version.
#. The cloud user creates backup for their instance.
#. The cloud administrator upgrades Trove controller service.
#. The cloud administrator updates the existing datastore version using the new image.
#. The cloud user creates a new instance using the backup created above.
#. The cloud user deletes the old instance.

From Victoria release, the upgrade process is much simpler:

#. The cloud administrator builds a new guest image based on the target Trove code version.
#. The cloud administrator updates the existing datastore version using the new image.
#. The cloud administrator triggers rebuild for the existing instances using the new image.
# Copyright 2011 OpenStack Foundation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
"""I totally stole most of this from melange, thx guys!!!"""


import re

from oslo_concurrency import processutils
from oslo_log import log as logging

from trove.common import base_exception as openstack_exception
from trove.common.i18n import _


ClientConnectionError = openstack_exception.ClientConnectionError
ProcessExecutionError = processutils.ProcessExecutionError
DatabaseMigrationError = openstack_exception.DatabaseMigrationError
LOG = logging.getLogger(__name__)
wrap_exception = openstack_exception.wrap_exception


def safe_fmt_string(text):
    return re.sub(r'%([0-9]+)', r'\1', text)


class TroveError(openstack_exception.OpenstackException):
    """Base exception that all custom trove app exceptions inherit from."""
    internal_message = None

    def __init__(self, message=None, **kwargs):
        if message is not None:
            self.message = message
        if self.internal_message is not None:
            try:
                LOG.error(safe_fmt_string(self.internal_message), kwargs)
            except Exception:
                LOG.error(self.internal_message)
        self.message = safe_fmt_string(self.message)
        super(TroveError, self).__init__(**kwargs)


class DBConstraintError(TroveError):

    message = _("Failed to save %(model_name)s because: %(error)s.")


class InvalidRPCConnectionReuse(TroveError):

    message = _("Invalid RPC Connection Reuse.")


class NotFound(TroveError):

    message = _("Resource %(uuid)s cannot be found.")


class CapabilityNotFound(NotFound):

    message = _("Capability '%(capability)s' cannot be found.")


class CapabilityDisabled(TroveError):

    message = _("Capability '%(capability)s' is disabled.")


class FlavorNotFound(TroveError):

    message = _("Resource %(uuid)s cannot be found.")


class UserNotFound(NotFound):

    message = _("User %(uuid)s cannot be found on the instance.")


class RootHistoryNotFound(NotFound):

    message = _("Root user has never been enabled on the instance.")


class DatabaseNotFound(NotFound):

    message = _("Database %(uuid)s cannot be found on the instance.")


class ComputeInstanceNotFound(NotFound):

    # internal_message is used for log, stop translating.
    internal_message = ("Cannot find compute instance %(server_id)s for "
                        "instance %(instance_id)s.")

    message = _("Resource %(instance_id)s can not be retrieved.")


class DnsRecordNotFound(NotFound):

    message = _("DnsRecord with name= %(name)s not found.")


class DatastoreNotFound(NotFound):

    message = _("Datastore '%(datastore)s' cannot be found.")


class DatastoreVersionNotFound(NotFound):

    message = _("Datastore version '%(version)s' cannot be found.")


class DatastoresNotFound(NotFound):

    message = _("Datastores cannot be found.")


class DatastoreFlavorAssociationNotFound(NotFound):

    message = _("Flavor %(id)s is not supported for datastore "
                "%(datastore)s version %(datastore_version)s")


class DatastoreFlavorAssociationAlreadyExists(TroveError):

    message = _("Flavor %(id)s is already associated with "
                "datastore %(datastore)s version %(datastore_version)s")


class DatastoreVolumeTypeAssociationNotFound(NotFound):

    message = _("The volume type %(id)s is not valid for datastore "
                "%(datastore)s and version %(version_id)s.")


class DatastoreVolumeTypeAssociationAlreadyExists(TroveError):

    message = _("Datastore '%(datastore)s' version %(datastore_version)s "
                "and volume-type %(id)s mapping already exists.")


class DataStoreVersionVolumeTypeRequired(TroveError):

    message = _("Only specific volume types are allowed for a "
                "datastore %(datastore)s version %(datastore_version)s. "
                "You must specify a valid volume type.")


class DatastoreVersionNoVolumeTypes(TroveError):

    message = _("No valid volume types could be found for datastore "
                "%(datastore)s and version %(datastore_version)s.")


class DatastoreNoVersion(TroveError):

    message = _("Datastore '%(datastore)s' has no version '%(version)s'.")


class DatastoreVersionInactive(TroveError):

    message = _("Datastore version '%(version)s' is not active.")


class DatastoreDefaultDatastoreNotFound(TroveError):

    message = _("Please specify datastore. Default datastore "
                "'%(datastore)s' cannot be found.")


class DatastoreDefaultDatastoreNotDefined(TroveError):

    message = _("Please specify datastore. No default datastore "
                "is defined.")


class DatastoreDefaultVersionNotFound(TroveError):

    message = _("Default version for datastore '%(datastore)s' not found.")


class InvalidDatastoreManager(TroveError):

    message = _("Datastore manager %(datastore_manager)s cannot be found.")


class DatastoreOperationNotSupported(TroveError):

    message = _("The '%(operation)s' operation is not supported for "
                "the '%(datastore)s' datastore.")


class NoUniqueMatch(TroveError):

    message = _("Multiple matches found for '%(name)s', "
                "use an UUID to be more specific.")


class OverLimit(TroveError):

    # internal_message is used for log, stop translating.
    internal_message = ("The server rejected the request due to its size or "
                        "rate.")


class QuotaLimitTooSmall(TroveError):

    message = _("Quota limit '%(limit)s' for '%(resource)s' is too small"
                " - must be at least '-1'.")


class QuotaExceeded(TroveError):

    message = _("Quota exceeded for resources: %(overs)s.")


class VolumeQuotaExceeded(QuotaExceeded):

    message = _("Instance volume quota exceeded.")


class GuestError(TroveError):

    message = _("An error occurred communicating with the guest: "
                "%(original_message)s.")


class GuestTimeout(TroveError):

    message = _("Timeout trying to connect to the Guest Agent.")


class BadRequest(TroveError):

    message = _("The server could not comply with the request since it is "
                "either malformed or otherwise incorrect.")


class MissingKey(BadRequest):

    message = _("Required element/key - %(key)s was not specified.")


class DatabaseAlreadyExists(BadRequest):

    message = _('A database with the name "%(name)s" already exists.')


class UserAlreadyExists(BadRequest):

    message = _('A user with the name "%(name)s" already exists.')


class InstanceAssignedToConfiguration(BadRequest):

    message = _('A configuration group cannot be deleted if it is '
                'associated with one or more non-terminated instances. '
                'Detach the configuration group from all non-terminated '
                'instances and please try again.')


class UnprocessableEntity(TroveError):

    message = _("Unable to process the contained request.")


class ConfigurationNotSupported(UnprocessableEntity):

    message = _("Configuration groups not supported by the datastore.")


class CannotResizeToSameSize(TroveError):

    message = _("No change was requested in the size of the instance.")


class VolumeAttachmentsNotFound(NotFound):

    message = _("Cannot find the volumes attached to compute "
                "instance %(server_id)s.")


class VolumeCreationFailure(TroveError):

    message = _("Failed to create a volume in Nova.")


class VolumeSizeNotSpecified(BadRequest):

    message = _("Volume size was not specified.")


class LocalStorageNotSpecified(BadRequest):

    message = _("Local storage not specified in flavor ID: %(flavor)s.")


class LocalStorageNotSupported(TroveError):

    message = _("Local storage support is not enabled.")


class VolumeNotSupported(TroveError):

    message = _("Volume support is not enabled.")


class ReplicationNotSupported(TroveError):

    message = _("Replication is not supported for "
                "the '%(datastore)s' datastore.")


class ReplicationSlaveAttachError(TroveError):

    message = _("Exception encountered attaching slave to new replica source.")


class TaskManagerError(TroveError):

    message = _("An error occurred communicating with the task manager: "
                "%(original_message)s.")


class BadValue(TroveError):

    message = _("Value could not be converted: %(msg)s.")


class PollTimeOut(TroveError):

    message = _("Polling request timed out.")


class Forbidden(TroveError):

    message = _("User does not have admin privileges.")


class PolicyNotAuthorized(Forbidden):

    message = _("Policy doesn't allow %(action)s to be performed.")


class InvalidModelError(TroveError):

    message = _("The following values are invalid: %(errors)s.")


class ModelNotFoundError(NotFound):

    message = _("Not Found.")


class UpdateGuestError(TroveError):

    message = _("Failed to update instances.")


class ConfigNotFound(NotFound):

    message = _("Config file not found.")


class PasteAppNotFound(NotFound):

    message = _("Paste app not found.")


class QuotaNotFound(NotFound):
    message = _("Quota could not be found.")


class TenantQuotaNotFound(QuotaNotFound):
    message = _("Quota for tenant %(tenant_id)s could not be found.")


class QuotaResourceUnknown(QuotaNotFound):
    message = _("Unknown quota resources %(unknown)s.")


class BackupUploadError(TroveError):
    message = _("Unable to upload Backup to swift.")


class BackupDownloadError(TroveError):
    message = _("Unable to download Backup from swift")


class BackupCreationError(TroveError):
    message = _("Unable to create Backup.")


class BackupUpdateError(TroveError):
    message = _("Unable to update Backup table in database.")


class SecurityGroupCreationError(TroveError):

    message = _("Failed to create Security Group.")


class SecurityGroupDeletionError(TroveError):

    message = _("Failed to delete Security Group.")


class SecurityGroupRuleCreationError(TroveError):

    message = _("Failed to create Security Group Rule.")


class SecurityGroupRuleDeletionError(TroveError):

    message = _("Failed to delete Security Group Rule.")


class MalformedSecurityGroupRuleError(TroveError):

    message = _("Error creating security group rules."
                " Malformed port(s). Port must be an integer."
                " FromPort = %(from)s greater than ToPort = %(to)s.")


class BackupNotCompleteError(TroveError):

    message = _("Unable to create instance because backup %(backup_id)s is "
                "not completed. Actual state: %(state)s.")


class BackupFileNotFound(NotFound):
    message = _("Backup file in %(location)s was not found in the object "
                "storage.")


class BackupDatastoreMismatchError(TroveError):
    message = _("The datastore from which the backup was taken, "
                "%(datastore1)s, does not match the destination"
                " datastore of %(datastore2)s.")


class ReplicaCreateWithUsersDatabasesError(TroveError):
    message = _("Cannot create a replica with users or databases.")


class SwiftAuthError(TroveError):
    message = _("Swift account not accessible for tenant %(tenant_id)s.")


class SwiftNotFound(TroveError):
    message = _("Swift is disabled for tenant %(tenant_id)s.")


class SwiftConnectionError(TroveError):
    message = _("Cannot connect to Swift.")


class DatabaseForUserNotInDatabaseListError(TroveError):
    message = _("The request indicates that user %(user)s should have access "
                "to database %(database)s, but database %(database)s is not "
                "included in the initial databases list.")


class DatabaseInitialDatabaseDuplicateError(TroveError):
    message = _("Two or more databases share the same name in the initial "
                "databases list. Please correct the names or remove the "
                "duplicate entries.")


class DatabaseInitialUserDuplicateError(TroveError):
    message = _("Two or more users share the same name and host in the "
                "initial users list. Please correct the names or remove the "
                "duplicate entries.")


class RestoreBackupIntegrityError(TroveError):
    message = _("Current Swift object checksum does not match original "
                "checksum for backup %(backup_id)s.")


class ConfigKeyNotFound(NotFound):
    message = _("%(key)s is not a supported configuration parameter.")


class NoConfigParserFound(NotFound):
    message = _("No configuration parser found for datastore "
                "%(datastore_manager)s.")


class ConfigurationDatastoreNotMatchInstance(TroveError):
    message = _("Datastore Version on Configuration "
                "%(config_datastore_version)s does not "
                "match the Datastore Version on the instance "
                "%(instance_datastore_version)s.")


class ConfigurationParameterDeleted(TroveError):
    message = _("%(parameter_name)s parameter can no longer be "
                "set as of %(parameter_deleted_at)s.")


class ConfigurationParameterAlreadyExists(TroveError):
    message = _("%(parameter_name)s parameter already exists "
                "for datastore version %(datastore_version)s.")


class ConfigurationAlreadyAttached(TroveError):
    message = _("Instance %(instance_id)s already has a "
                "Configuration Group attached: %(configuration_id)s.")


class InvalidInstanceState(TroveError):
    message = _("The operation you have requested cannot be executed because "
                "the instance status is currently: %(status)s.")


class NoServiceEndpoint(TroveError):
    """Could not find requested endpoint in Service Catalog."""
    message = _("Endpoint not found for service_type=%(service_type)s, "
                "endpoint_type=%(endpoint_type)s, "
                "endpoint_region=%(endpoint_region)s.")


class EmptyCatalog(NoServiceEndpoint):
    """The service catalog is empty."""
    message = _("Empty catalog.")


class IncompatibleReplicationStrategy(TroveError):
    message = _("Instance with replication strategy %(guest_strategy)s "
                "cannot replicate from instance with replication strategy "
                "%(replication_strategy)s.")


class InsufficientSpaceForReplica(TroveError):
    message = _("The target instance has only %(slave_volume_size)sG free, "
                "but the replication snapshot contains %(dataset_size)sG "
                "of data.")


class InsufficientSpaceForBackup(TroveError):
    message = _("The instance has only %(free)sG free while the estimated "
                "backup size is %(backup_size)sG.")


class ReplicaSourceDeleteForbidden(Forbidden):
    message = _("The replica source cannot be deleted without detaching the "
                "replicas.")


class ModuleTypeNotFound(NotFound):
    message = _("Module type '%(module_type)s' was not found.")


class ModuleAppliedToInstance(BadRequest):

    message = _("A module cannot be deleted or its contents modified if it "
                "has been applied to a non-terminated instance, unless the "
                "module has been marked as 'live_update.' "
                "Please remove the module from all non-terminated "
                "instances and try again.")


class ModuleAlreadyExists(BadRequest):

    message = _("A module with the name '%(name)s' already exists for "
                "datastore '%(datastore)s' and datastore version "
                "'%(ds_version)s'")


class ModuleAccessForbidden(Forbidden):

    message = _("You must be admin to %(action)s a module with these "
                "options. %(options)s")


class ModuleInvalid(Forbidden):

    message = _("The module is invalid: %(reason)s")


class InstanceNotFound(NotFound):
    message = _("Instance '%(instance)s' cannot be found.")


class ClusterNotFound(NotFound):
    message = _("Cluster '%(cluster)s' cannot be found.")


class ClusterFlavorsNotEqual(TroveError):
    message = _("The flavor for each instance in a cluster must be the same.")


class ClusterNetworksNotEqual(TroveError):
    message = _("The network for each instance in a cluster must be the same.")


class NetworkNotFound(TroveError):
    message = _("Network Resource %(uuid)s cannot be found.")


class ClusterVolumeSizeRequired(TroveError):
    message = _("A volume size is required for each instance in the cluster.")


class ClusterVolumeSizesNotEqual(TroveError):
    message = _("The volume size for each instance in a cluster must be "
                "the same.")


class ClusterNumInstancesNotSupported(TroveError):
    message = _("The number of instances for your initial cluster must "
                "be %(num_instances)s.")


class ClusterNumInstancesNotLargeEnough(TroveError):
    message = _("The number of instances for your initial cluster must "
                "be at least %(num_instances)s.")


class ClusterNumInstancesBelowSafetyThreshold(TroveError):
    message = _("The number of instances in your cluster cannot "
                "safely be lowered below the current level based "
                "on your current fault-tolerance settings.")


class ClusterShrinkMustNotLeaveClusterEmpty(TroveError):
    message = _("Must leave at least one instance in the cluster when "
                "shrinking.")


class ClusterShrinkInstanceInUse(TroveError):
    message = _("Instance(s) %(id)s currently in use and cannot be deleted. "
                "Details: %(reason)s")


class ClusterInstanceOperationNotSupported(TroveError):
    message = _("Operation not supported for instances that are part of a "
                "cluster.")


class ClusterOperationNotSupported(TroveError):

    message = _("The '%(operation)s' operation is not supported for cluster.")


class TroveOperationAuthError(TroveError):
    message = _("Operation not allowed for tenant %(tenant_id)s.")


class ClusterDatastoreNotSupported(TroveError):
    message = _("Clusters not supported for "
                "%(datastore)s-%(datastore_version)s.")


class BackupTooLarge(TroveError):
    message = _("Backup is too large for given flavor or volume. "
                "Backup size: %(backup_size)s GBs. "
                "Available size: %(disk_size)s GBs.")


class ImageNotFound(NotFound):

    message = _("Image %(uuid)s cannot be found.")


class DatastoreVersionAlreadyExists(BadRequest):

    message = _("A datastore version with the name '%(name)s' already exists.")


class LogAccessForbidden(Forbidden):

    message = _("You must be admin to %(action)s log '%(log)s'.")


class SlaveOperationNotSupported(TroveError):

    message = _("The '%(operation)s' operation is not supported for slaves in "
                "replication.")

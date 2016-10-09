
import unittest

from proboscis import test

from trove.tests.api.instances import instance_info
from trove.tests.api.instances import GROUP_START as INSTANCE_START
from trove.tests.api.instances import GROUP_TEST
from trove.tests.api.instances import GROUP_STOP as INSTANCE_STOP
from trove.tests.config import CONFIG
from trove.common.utils import import_object
from trove.common.utils import poll_until

WHITE_BOX = CONFIG.white_box

if WHITE_BOX:
    # TODO(tim.simpson): Restore this once white box functionality can be
    #                    added back to this test module.
    pass
    # import rsdns
    # from nova import flags
    # from nova import utils

    # from trove import exception
    # from trove.utils import poll_until

    # FLAGS = flags.FLAGS

dns_driver = None

GROUP = "dbaas.guest.dns"


@test(groups=[GROUP, GROUP_TEST])
class Setup(unittest.TestCase):
    """Creates the DNS Driver and entry factory used in subsequent tests."""

    def test_create_rs_dns_driver(self):
        global dns_driver
        dns_driver = import_object(FLAGS.dns_driver)


def expected_dns_entry():
    """Returns expected DNS entry for this instance.

    :rtype: Instance of :class:`DnsEntry`.

    """
    return create_dns_entry(instance_info.local_id, instance_info.id)


@test(depends_on_classes=[Setup],
      depends_on_groups=[INSTANCE_START],
      groups=[GROUP, GROUP_TEST])
class WhenInstanceIsCreated(unittest.TestCase):
    """Make sure the DNS name was provisioned.

    This class actually calls the DNS driver to confirm the entry that should
    exist for the given instance does exist.

    """

    def test_dns_entry_should_exist(self):
        entry = expected_dns_entry()
        if entry:
            def get_entries():
                return dns_driver.get_entries_by_name(entry.name)
            try:
                poll_until(get_entries, lambda entries: len(entries) > 0,
                           sleep_time=2, time_out=60)
            except exception.PollTimeOut:
                self.fail("Did not find name " + entry.name + \
                          " in the entries, which were as follows:"
                          + str(dns_driver.get_entries()))


@test(depends_on_classes=[Setup, WhenInstanceIsCreated],
      depends_on_groups=[INSTANCE_STOP],
      groups=[GROUP])
class AfterInstanceIsDestroyed(unittest.TestCase):
    """Make sure the DNS name is removed along with an instance.

    Because the compute manager calls the DNS manager with RPC cast, it can
    take awhile.  So we wait for 30 seconds for it to disappear.

    """

    def test_dns_entry_exist_should_be_removed_shortly_thereafter(self):
        entry = expected_dns_entry()

        if not entry:
            return

        def get_entries():
            return dns_driver.get_entries_by_name(entry.name)

        try:
            poll_until(get_entries, lambda entries: len(entries) == 0,
                       sleep_time=2, time_out=60)
        except exception.PollTimeOut:
            # Manually delete the rogue item
            dns_driver.delete_entry(entry.name, entry.type, entry.dns_zone)
            self.fail("The DNS entry was never deleted when the instance "
                      "was destroyed.")

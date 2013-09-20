import inspect
import os

from trove.openstack.common import importutils
from trove.openstack.common import loopingcall
from trove.openstack.common.rpc import service as rpc_service
from trove.common import cfg

CONF = cfg.CONF


class RpcService(rpc_service.Service):

    def __init__(self, host=None, binary=None, topic=None, manager=None):
        host = host or CONF.host
        binary = binary or os.path.basename(inspect.stack()[-1][1])
        topic = topic or binary.rpartition('trove-')[2]
        self.manager_impl = importutils.import_object(manager)
        self.report_interval = CONF.report_interval
        super(RpcService, self).__init__(host, topic,
                                         manager=self.manager_impl)

    def start(self):
        super(RpcService, self).start()
        # TODO(hub-cap): Currently the context is none... do we _need_ it here?
        pulse = loopingcall.LoopingCall(self.manager_impl.run_periodic_tasks,
                                        context=None)
        pulse.start(interval=self.report_interval,
                    initial_delay=self.report_interval)
        pulse.wait()

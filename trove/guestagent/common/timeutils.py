from datetime import datetime

from oslo_utils import timeutils


def float_utcnow():
    return float(datetime.strftime(timeutils.utcnow(), "%s.%f"))

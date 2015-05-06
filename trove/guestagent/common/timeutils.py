from oslo_utils import timeutils
from datetime import datetime


def float_utcnow():
    return float(datetime.strftime(timeutils.utcnow(), "%s.%f"))

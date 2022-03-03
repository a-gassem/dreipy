from enum import Enum
from datetime import datetime

class Status(Enum):
    PENDING = 1
    ONGOING = 2
    CLOSED = 3

def checkStatus(start: datetime, end: datetime) -> Status:
    """Given a start and end time, return the corresponding Status based on
the current time."""
    now = datetime.now().replace(tzinfo=start.tzinfo)
    if (now < start):
        return Status.PENDING
    elif (now >= start and now < end):
        return Status.ONGOING
    return Status.CLOSED


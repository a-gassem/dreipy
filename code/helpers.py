from uuid import uuid4
from datetime import datetime

from typing import Union

LONG_FORMAT = "%A %d %B %Y %I:%M:%S%p"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

def makeID() -> str:
    """Generates a random, unique ID by making a UUID 4, converting to hex and
taking its string representation. Note, this is not cryptographically secure,
it's simply for indexing in the database!"""
    return str(uuid4().hex)

def longTime(time_obj: datetime) -> str:
    """Returns the given datetime object as a long-form, user-friendly string.
E.g: Wednesday 30 March 2022 10:45:30AM"""
    return time_obj.strftime(LONG_FORMAT)

def parseTime(time_str: str) -> Union[datetime, None]:
    """Returns a datetime object constructed from parsing the input string. If
the string is not well-formed, returns None."""
    try:
        return datetime.strptime(time_str, TIME_FORMAT)
    except ValueError:
        return None

def mergeTime(year: str, month: str, day: str, hour: str, mins: str,
              secs: str) -> str:
    return f"{year}-{month}-{day} {hour}:{mins}:{secs}" 

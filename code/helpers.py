from uuid import uuid4

def makeID():
    """Generates a random, unique ID by making a UUID 4, converting to hex and
taking its string representation. Note, this is not cryptographically secure,
it's simply for indexing in the database!"""
    return str(uuid4().hex)

def longTime(timeObj):
    """Returns the given datetime object as a long-form, user-friendly string."""
    return str(timeObj)

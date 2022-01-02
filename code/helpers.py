from pyisemail import is_email
from pyisemail.diagnosis import InvalidDiagnosis, ValidDiagnosis

from uuid import uuid4
from datetime import datetime
from typing import Union, Dict, Any, Tuple, List, Generic
import csv

LONG_FORMAT = "%A %d %B %Y %I:%M:%S%p"
DOB_FORMAT = "%d-%m-%Y"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

CSV_HEADERS = sorted(['fname', 'lname', 'postcode', 'email', 'dob'])

# maximum size of our sample from the CSV
SAMPLE_SIZE = 5

# these are the max lengths for first and last names
FNAME_MAX_LENGTH = 35
LNAME_MAX_LENGTH = 35
POSTCODE_LENGTH = 8

# Code for these case insensitive classes used from
# https://www.pythonpool.com/python-csv-dictreader/
class InsensitiveDict(dict):
    def __getitem__(self, key):
        return dict.__getitem__(self, key.strip().lower())

class InsensitiveDictReader(csv.DictReader):
    @property
    def fieldnames(self):
        return [field.strip().lower() for field in
                csv.DictReader.fieldnames.fget(self)]

    def next(self):
        return InsensitiveDict(csv.DictReader.next(self))

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

def clearSession(session: Dict, keys: List[str]) -> None:
    """Given a Flask session and some keys, pop all those keys if they exist.
Useful for when we want to clear out session data when a user is redirected."""
    for key in keys:
        session.pop(key, None)

def isCsv(filename: str) -> bool:
    """Takes a filename *that has been passed through the secure_filename()
function* and then does some simple checks to see if it is indeed a CSV file."""
    parts = filename.split('.')
    if (len(parts) != 2):
        return False
    return parts[1].lower() == 'csv'
    
def newFilename() -> str:
    """Generates a random, new filename for the voter CSV file for us to save
it as."""
    return f"{makeID()}.csv"

def checkCsv(filepath: str, delimiter: str) \
    -> Tuple[Union[List, None], List[str]]:
    """Does some basic checks on an input CSV file. We do not exhaustively
check for things like valid email addresses, valid postcodes and so on -- it
is the responsibility of the person creating the election to gather the details
of voters and store them correctly before passing them to DRE-ipy. That being
said we do flag email addresses that are likely to be incorrect, check for
duplicate email addresses and have set an upper limit on the length of names
and postcodes."""
    errors = []
    voters = []
    emails = {'warn':[]}
    badEmails = []
    with open(filepath, 'r', newline='') as f:
        reader = InsensitiveDictReader(f, delimiter=delimiter)
        if sorted(reader.fieldnames) != CSV_HEADERS:
            errors.append("Mismatch in CSV file headers. Did you pass the \
correct delimiter? Did you spell one of your headers wrong?")
            return None, errors
        for row in reader:
            # extra data gets put under the None key in the dict -- we don't
            # want this!
            if None in row:
                errors.append("Found a row with more data than fields specified\
. Please ensure that each row has exactly 1 entry for each header.")
                return None, errors
            # DoB checks
            try:
                row['dob'] = datetime.strptime(row['dob'], DOB_FORMAT)
            except ValueError:
                errors.append("Found a row with a badly-formed date of birth. \
Please ensure that each date of birth is in the form DD-MM-YYYY.")
                return None, errors
            # email checks
            email = row['email']
            if email in emails:
                errors.append(f"Found a duplicate email address: {email}\
. Please ensure that each email address is unique in the CSV file.")
                return None, errors
            diagnosis = is_email(email, diagnosis=True)
            if isinstance(diagnosis, InvalidDiagnosis):
                badEmails.append(email)
            elif isinstance(diagnosis, ValidDiagnosis):
                emails[email] = ''
            else:
                # if not Valid or Invalid, then it's ambiguous and we should
                # simply warn the user about the email address
                emails['warn'].append(email)
            # length checks on other fields - truncate long names rather than
            # reject outright for maximum accessibility
            if row['fname'] > FNAME_MAX_LENGTH:
                row['fname'] = row['fname'][:FNAME_MAX_LENGTH]
            if row['lname'] > LNAME_MAX_LENGTH:
                row['lname'] = row['lname'][:FNAME_MAX_LENGTH]
            
            if len(voters) < SAMPLE_SIZE:
                voters.append(row)
    if badEmails:
        errors.append(f"Invalid email address(es) found: {badEmails}. \
Please ensure that all invalid email addresses are removed from the CSV file.")
        return None, errors
    return voters, errors

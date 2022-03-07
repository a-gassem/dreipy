from pyisemail import is_email
from pyisemail.diagnosis import InvalidDiagnosis, ValidDiagnosis
from gmpy2 import mpz, powmod
from ecdsa import SigningKey, NIST256p
from ecdsa.ellipticcurve import Point
import jsonpickle

from Voter import Voter
from Election import Election
from Question import Question
from crypto import (generateRandSecret, signData, generateR, generateZ,
                    generateZKProof, generatePair, hashString)

from uuid import uuid4
from ast import literal_eval
from base64 import b64decode, b64encode
from datetime import datetime
from typing import Union, Dict, Any, Tuple, List, Generic, Optional
import csv
import json
import os


DOB_FORMAT = "%d-%m-%Y"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

CSV_HEADERS = sorted(['fname', 'lname', 'postcode', 'email', 'dob'])

# maximum size of our sample from the CSV
SAMPLE_SIZE = 5

# these are the max lengths for first and last names
FNAME_MAX_LENGTH = 35
LNAME_MAX_LENGTH = 35
POSTCODE_MAX_LENGTH = 8

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

## TODO!!!
def generateSession() -> str:
    """Returns a cryptographically secure session ID"""
    return "TODO"

def _makeFolder(path: str, permissions: int) -> None:
    """Helper procedure to create a folder that may or may not already exist."""
    try:
        os.makedirs(path, mode=permissions)
    except OSError:
        pass

def makeID() -> str:
    """Generates a random, unique ID by making a UUID 4, converting to hex and
taking its string representation. Note, this is not cryptographically secure,
it's simply for indexing in the database!"""
    return str(uuid4().hex)

def parseTime(time_str: str) -> Optional[datetime]:
    """Returns a datetime object constructed from parsing the input string. If
the string is not well-formed, returns None."""
    try:
        return datetime.strptime(time_str, TIME_FORMAT)
    except ValueError:
        return None

def parseElection(electionDict: Dict, start_time: datetime,
              end_time: datetime) -> Optional[Election]:
    """Given a dictionary of questions and choices, with the start/end times try
to create an Election object and return it; otherwise return None"""
    questionObjs = []
    questions = electionDict['questions']
    # note that we sort all our dictionaries to ensure that we get the correct
    # ordering of our lists when we iterate through them
    try:
        for questionNum, qDict in sorted(questions.items()):
            choices = [choice for choiceNum, choice \
                       in sorted(qDict['choices'].items())]
            q_id = makeID()
            gen_1, gen_2 = generatePair(q_id)
            questionObjs.append(Question(q_id, qDict['query'],
                                         qDict['maxanswers'], choices, gen_2))
        return Election(makeID(), electionDict['title'], questionObjs,
                        start_time, end_time)
    except Exception as e:
        # there shouldn't be any errors, but print to console just in case
        print(e)
        return None

def mergeTime(year: str, month: str, day: str, hour: str, mins: str,
              secs: str) -> str:
    return f"{year}-{month}-{day} {hour}:{mins}:{secs}" 

def clearSession(session: Dict, keys: Optional[List]=None) -> None:
    """Given a Flask session and some keys, pop all those keys if they exist.
Useful for when we want to clear out session data when a user is redirected.
If no keys are passed (or the list is empty), then all keys are popped."""
    if keys is None:
        for key in list(session.keys()):
            session.pop(key, None)
    else:
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
    -> Tuple[Optional[List], Optional[List], List[str]]:
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
            return None, emails['warn'], errors
        for row in reader:
            # extra data gets put under the None key in the dict -- we don't
            # want this!
            if None in row:
                errors.append("Found a row with more data than fields specified\
. Please ensure that each row has exactly 1 entry for each header.")
                return None, emails['warn'], errors
            # DoB checks
            try:
                row['dob'] = datetime.strptime(row['dob'], DOB_FORMAT)
            except ValueError:
                errors.append("Found a row with a badly-formed date of birth. \
Please ensure that each date of birth is in the form DD-MM-YYYY.")
                return None, None, errors
            # email checks
            email = row['email']
            if email in emails:
                errors.append(f"Found a duplicate email address: {email}\
. Please ensure that each email address is unique in the CSV file.")
                return None, None, errors
            diagnosis = is_email(email, diagnose=True)
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
            row['fname'] = row['fname'][:FNAME_MAX_LENGTH]
            row['lname'] = row['lname'][:LNAME_MAX_LENGTH]
            row['postcode'] = row['postcode'][:POSTCODE_MAX_LENGTH]
            if not row['fname'] or not row['lname'] or not row['postcode']:
                errors.append("Empty field found in CSV file. Please make sure\
 that all fields are filled out with the appropriate data.")
                return None, None, errors
            if len(voters) < SAMPLE_SIZE:
                voters.append(row)
    if badEmails:
        errors.append(f"Invalid email address(es) found: {badEmails}. \
Please ensure that all invalid email addresses are removed from the CSV file.")
        return None, None, errors
    return voters, emails['warn'], errors

def _getVoters(election_id: str, filepath: str, delimiter: str) -> List[Voter]:
    """Takes a path to a validated CSV file and returns a list of Voters whose
details are stored in the file"""
    voters = []
    with open(filepath, 'r', newline='') as f:
        reader = InsensitiveDictReader(f, delimiter=delimiter)
        for voter in reader:
            fname = voter['fname'][:FNAME_MAX_LENGTH]
            lname = voter['lname'][:LNAME_MAX_LENGTH]
            postcode = voter['postcode'][:POSTCODE_MAX_LENGTH]
            email = voter['email']
            dob = datetime.strptime(voter['dob'], DOB_FORMAT)
            voters.append(Voter(makeID(), election_id, fname, lname, postcode,
                                email, dob, "SOME_HASH"))
    return voters

def bytestrToPoint(bytestring: str) -> Point:
    return Point.from_bytes(NIST256p.curve, b64decode(literal_eval(bytestring)))

def pointToBytestr(point: Point) -> str:
    return str(b64encode(point.to_bytes()))

def sKeyToBytestr(key: SigningKey) -> str:
    return str(b64encode(key.to_string()))

def bytestrToSKey(bytestring: str) -> SigningKey:
    return SigningKey.from_string(b64decode(literal_eval(bytestring)),
                                  curve=NIST256p)

def validateHash(user_code: str, db_hash: str) -> bool:
    """Given a user's election code, checks that its hash matches with the stored
value when passed through hash function."""
    return user_code == db_hash

def firstReceipt(question: Question, choices: List[int]) \
    -> Optional[str]:
    from db import getNewBallotID, insertBallot, updateReceipt, getPrivateKey
    
    ## go through all the chosen answers to do proofs and add to receipt
    gen_2 = question.gen_2
    all_choices = [i for i in range(len(question.choices))]
    ballot_id = getNewBallotID(question.question_id)
    receipt_data = {"question_id":question.question_id,
                    "ballot_id":str(ballot_id),
                    "choices":[]}
    for choice in all_choices:
        voted = choice in choices
        
        # Get a random secret
        r = generateRandSecret()
        
        # Make first receipt
        R = generateR(gen_2, r)
        
        # Make second receipt
        Z = generateZ(r, choice)

        # Make proof
        r_1, r_2, c_1, c_2 = generateZKProof(gen_2, R, Z, r, voted,
                                             question.question_id,
                                             choice, ballot_id)

        # Add ballot to question
        if insertBallot(ballot_id, question.question_id, r,
                        choice, R, Z, r_1, r_2, c_1, c_2) is None:
            return None
        receipt_data['choices'].append({
            "choice":str(choice),
            "Z":pointToBytestr(Z),
            "R":pointToBytestr(R),
            "c_1":str(c_1),
            "c_2":str(c_2),
            "r_1":str(r_1),
            "r_2":str(r_2)
            })

    ## Get hash of data and insert into database with our signature; updating all
    #  ballots
    json_data = json.dumps(receipt_data)
    data_hash = hashString(json_data)
    signature = signData(data_hash, getPrivateKey())
    updateReceipt(signature, data_hash, ballot_id)

    return json_data

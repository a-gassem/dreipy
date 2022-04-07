from flask import flash
from gmpy2 import mpz, powmod
from ecdsa import SigningKey, VerifyingKey, NIST256p
from ecdsa.ellipticcurve import Point
import jsonpickle
import gmpy2

from Voter import Voter
from Election import Election
from Question import Question
from crypto import (generateRandSecret, generateR, generateZ, generateZKProof,
                    generatePair, hashString)

from urlparse import urlparse, urljoin
from uuid import uuid4
from ast import literal_eval
from base64 import b64decode, b64encode
from datetime import datetime
from secrets import token_urlsafe, token_hex
from typing import Union, Dict, Any, Tuple, List, Generic, Optional
import csv
import json
import os

DOB_FORMAT = "%d-%m-%Y"
TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

CSV_HEADERS = sorted(['fname', 'lname', 'postcode', 'uname', 'dob', 'pass'])

# maximum size of our sample from the CSV
SAMPLE_SIZE = 5

# these are the max lengths for first and last names
FNAME_MAX_LENGTH = 35
LNAME_MAX_LENGTH = 35
POSTCODE_MAX_LENGTH = 8

# how short to truncate a hash digest to
HASH_LENGTH = 5

SECRET_BYTES = 32

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

def generateSession() -> str:
    """Returns a cryptographically secure session ID"""
    return token_urlsafe(SECRET_BYTES)

def _makeFolder(path: str, permissions: int) -> None:
    """Helper procedure to create a folder that may or may not already exist."""
    try:
        os.makedirs(path, mode=permissions)
    except OSError:
        pass

def isSafeUrl(target_endpoint: str) -> bool:
    """Basic function to check if a redirect target will lead to the same server. Source:
    https://web.archive.org/web/20120517003641/http://flask.pocoo.org/snippets/62/"""
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and \
           ref_url.netloc == test_url.netloc

def makeID() -> str:
    """Generates a random, unique ID from token_hex (not long enough to be
cryptographically secure!!)"""
    return token_hex(32)[:6].upper()

def parseTime(time_str: str) -> Optional[datetime]:
    """Returns a datetime object constructed from parsing the input string. If
the string is not well-formed, returns None."""
    try:
        return datetime.strptime(time_str, TIME_FORMAT)
    except ValueError:
        return None

def parseElection(election_id: str, questions: Dict, start_time: datetime,
                  end_time: datetime, title: str, contact: str) -> Election:
    """Given a dictionary of questions and choices, with the start/end times try
to create an Election object and return it; otherwise return None"""
    question_objs = []
    # note that we sort all our dictionaries to ensure that we get the correct
    # ordering of our lists when we iterate through them
    for question_num, question_dict in sorted(questions.items()):
        choices = [choice for choice_num, choice \
                   in sorted(question_dict['choices'].items())]
        question_id = makeID()
        gen_1, gen_2 = generatePair(question_id)
        question_objs.append(Question(question_id, question_dict['query'],
                                      question_dict['numanswers'], choices,
                                      gen_2))
    return Election(election_id, title, question_objs, start_time, end_time, contacts)

def mergeTime(year: str, month: str, day: str, hour: str) -> str:
    return f"{year}-{month}-{day} {hour}:00:00" 

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
    
def newFilename() -> str:
    """Generates a random, new filename for the voter CSV file for us to save
it as."""
    return f"{makeID()}.csv"

def checkCsv(election_id: str, filepath: str, delimiter: str) \
    -> Optional[List[Voter]]:
    """Does some basic checks on an input CSV file. We do not exhaustively
check for things like valid email addresses, valid postcodes and so on -- it
is the responsibility of the person creating the election to gather the details
of voters and store them correctly before passing them to DRE-ipy.

    Returns all the Voter objects for the election."""
    voters = []
    with open(filepath, 'r', newline='') as f:
        reader = InsensitiveDictReader(f, delimiter=delimiter)
        if sorted(reader.fieldnames) != CSV_HEADERS:
            flash("Mismatch in CSV file headers. Did you pass the correct delimiter? Did you spell one of your headers wrong?")
            return None
        for row in reader:
            # extra data gets put under the None key in the dict -- we don't
            # want this!
            if None in row:
                flash("Found a row with more data than fields specified. Please ensure that each row has exactly 1 entry for each header.")
                return None
            # DoB checks
            try:
                dob = datetime.strptime(row['dob'], DOB_FORMAT)
            except ValueError:
                flash("Found a row with a badly-formed date of birth. Please ensure that each date of birth is in the form DD-MM-YYYY.")
                return None
            # username checks
            uname = row['uname']
            if uname in unames:
                flash(f"Found a duplicate username: {uname}. Please ensure that each username is unique in the CSV file.")
                return None
            # length checks on other fields - truncate long names rather than
            # reject outright for maximum accessibility
            fname = row['fname'][:FNAME_MAX_LENGTH]
            lname = row['lname'][:LNAME_MAX_LENGTH]
            postcode = row['postcode'][:POSTCODE_MAX_LENGTH]
            hash = hashString(row['pass'])
            if not row['fname'] or not row['lname'] or not row['postcode']:
                flash("Empty field found in CSV file. Please make sure that all fields are filled out with the appropriate data.")
                return None
            voters.append(Voter(makeID(), election_id, fname, lname, postcode,
                                uname, dob, hash))
    return voters

def bytestrToPoint(bytestring: str) -> Point:
    return Point.from_bytes(NIST256p.curve, bytes.fromhex(bytestring))

def pointToBytestr(point: Point) -> str:
    """Returns the hexadecimal representation of the byte-encoding of a Point
object."""
    return point.to_bytes().hex()

def sKeyToBytestr(key: Union[SigningKey, VerifyingKey]) -> str:
    """Returns the hexadecimal representation of the byte-encoding of a
SigningKey or VerifyingKey object."""
    return key.to_string().hex()

def bytestrToVKey(bytestring: str) -> VerifyingKey:
    return VerifyingKey.from_string(bytes.fromhex(bytestring), curve=NIST256p)

def bytestrToSKey(bytestring: str) -> SigningKey:
    return SigningKey.from_string(bytes.fromhex(bytestring), curve=NIST256p)

def prettyReceipt(receipt: str) -> str:
    return " ".join([receipt[i:i+5] for i in range(0, len(receipt), 5)])

def validateHash(user_code: str, db_hash: str) -> bool:
    """Given a user's election code, checks that its hash matches with the stored
value when passed through hash function."""
    return hashString(user_code) == db_hash

def hexToMpz(hexstring: Union[str, int]) -> mpz:
    """Converts a hexstring to an mpz object."""
    if isinstance(hexstring, int):
        return mpz(hexstring)
    return gmpy2.mpz_from_old_binary(bytes.fromhex(hexstring))

def truncHash(hash_str: str) -> str:
    """Given some string digest of a hash, truncate to HASH_LENGTH characters
for ease of comparison for the user."""
    return hash_str.upper()[:HASH_LENGTH]

def firstReceipt(question: Question, election_id: str, session_id: str,
                 choices: List[str]) -> Optional[dict]:
    from db import getNewBallotID, insertBallot, getVoterFromSession
    
    ## go through all the possible choices to do proofs and add to receipt
    gen_2 = question.gen_2
    ballot_id = str(getNewBallotID(question.question_id))
    receipt_data = {"election_d":election_id,
                    "question_id":question.question_id,
                    "ballot_id":ballot_id,
                    "choices":[]}
    voter_id = getVoterFromSession(session_id)
    question_id = question.question_id
    num_choices = len(question.choices)
    R_list = []
    Z_list = []
    r_list = []
    for choice in range(num_choices):
        # was this choice voted on?
        voted = str(choice) in choices
        
        # Make receipts and secret
        r = generateRandSecret()
        R = generateR(gen_2, r)
        Z = generateZ(r, int(voted))

        # Make proof
        c_1, c_2, r_1, r_2 = generateZKProof(question_id, gen_2, R, Z, r)

        # Add ballot to question
        if insertBallot(ballot_id, question_id, r, R, Z, r_1, r_2,
                        c_1, c_2, choice, election_id, voter_id) is None:
            return None
        receipt_data['choices'].append({
            "Z":truncHash(pointToBytestr(Z)),
            "R":truncHash(pointToBytestr(R)),
            "proof":{
                "c_1":truncHash(str(c_1)),
                "c_2":truncHash(str(c_2)),
                "r_1":truncHash(str(r_1)),
                "r_2":truncHash(str(r_2))
                }
            })

        # add receipts and secret to list for final proof
        R_list.append(R)
        Z_list.append(Z)
        r_list.append(r)

    # calculate the extra proof to ensure number of choices is correct
    num_c, num_r = generateNumProof(question_id, gen_2, R_list, Z_list, r_list,
                                    num_choices)
    if addNumProofs(ballot_id, num_c, num_r) is None:
        return None
    receipt_data['num_proof_c'] = truncHash(str(num_c))
    receipt_data['num_proof_r'] = truncHash(str(num_r))

    ## Get hash of data and insert into database with our signature, before
    # before returning it
    return receipt_data

def auditBallot(question_id: str, ballot_id: str) -> Optional[dict]:
    """Marks a ballot as 'audited' and creates a new signature."""
    from db import getBallotData, updateAuditBallot
    receipt_list = getBallotData(ballot_id)
    if receipt_list is None:
        return None
    receipt_data = {
        "ballot":"AUDITED",
        "question_id":question_id,
        "ballot_id":ballot_id,
        "choices":[]}
    for R, Z, secret, index, choice, c_1, c_2, r_1, r_2 in receipt_list:
        receipt_data['choices'].append({
            "R":R,
            "Z":Z,
            "secret": secret,
            "vote":choice,
            "choice_id":index,
            "proof":{
                "c_1":c_1,
                "c_2":c_2,
                "r_1":r_1,
                "r_2":r_2
                }
            })
    if updateAuditBallot(ballot_id, audited=True) is None:
        return None
    return receipt_data

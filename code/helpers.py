from flask import flash, current_app
from gmpy2 import mpz, powmod
from ecdsa import SigningKey, VerifyingKey, NIST256p
from ecdsa.ellipticcurve import Point
from markupsafe import escape
import jsonpickle
import gmpy2

from Voter import Voter
from Election import Election
from Question import Question
from crypto import (generateRandSecret, generateR, generateZ, generateZKProof,
                    generatePair, hashString, generateNumProof, signData)

from urllib.parse import urlparse, urljoin
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
HASH_LENGTH = 50

# Code for dicts from: https://www.pythonpool.com/python-csv-dictreader/
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
    from main import SECRET_BYTES
    return token_urlsafe(SECRET_BYTES)

def makeFolder(path: str, permissions: int) -> None:
    """Create a folder that may or may not already exist."""
    try:
        os.makedirs(path, mode=permissions)
    except OSError:
        pass

def makeID() -> str:
    """
    Generates a random, unique ID; note not long enough to be cryptographically
    secure!!
    """
    from main import SECRET_BYTES
    return token_hex(SECRET_BYTES)[:6].upper()

def parseTime(time_str: str) -> Optional[datetime]:
    """
    Returns a datetime object constructed from parsing the input string. If the
    string is not well-formed, returns None.
    """
    try:
        return datetime.strptime(time_str, TIME_FORMAT)
    except ValueError:
        return None

def parseElection(election_id: str, questions: Dict, start_time: datetime,
                  end_time: datetime, title: str, contact: str) -> Election:
    """
    Given a dictionary of questions and choices, with the start/end times try
    to create an Election object and return it; otherwise return None.
    """
    question_objs = []
    # note that we sort all our dictionaries to ensure that we get the correct
    # ordering of our lists when we iterate through them
    for question_num, question_dict in sorted(questions.items()):
        choices = [choice for choice_num, choice \
                   in sorted(question_dict['choices'].items())]
        question_id = makeID()
        gen_1, gen_2 = generatePair(question_id)
        question_objs.append(Question(question_id, election_id, question_dict['query'],
                                      question_dict['numanswers'], choices,
                                      gen_2))
    return Election(election_id, title, question_objs, start_time, end_time,
                    contact)

def mergeTime(year: str, month: str, day: str, hour: str) -> str:
    """
    Combines a string for the year, month, day and hour into a string that
    should be able to be parsed with parseTime().
    """
    return f"{year}-{month}-{day} {hour}:00:00" 

def clearSession(session: Dict) -> None:
    """Given a Flask session, pop all its keys if any exist."""
    for key in list(session.keys()):
        session.pop(key, None)
    
def newFilename() -> str:
    """
    Generates a random, new filename for the voter CSV file for us to save it
    as.
    """
    return f"{makeID()}.csv"

def checkCsv(election_id: str, filepath: str, delimiter: str) \
    -> Optional[List[Voter]]:
    """
    Returns all the Voter objects for the election after some basic checks on
    the input voter CSV file. We do not exhaustively check for things like
    valid postcodes -- it is the responsibility of the person creating the
    election to gather the details of voters and store them correctly before
    passing them to DRE-ipy.
    """
    voters = []
    unames = {}
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
            uname = escape(row['uname'])
            if uname in unames:
                flash(f"Found a duplicate username: {uname}. Please ensure that each username is unique in the CSV file.")
                return None
            unames[uname] = True
            # length checks on other fields - truncate long names rather than
            # reject outright for maximum accessibility
            fname = escape(row['fname'][:FNAME_MAX_LENGTH])
            lname = escape(row['lname'][:LNAME_MAX_LENGTH])
            name = f"{fname} {lname}".upper()
            postcode = escape(row['postcode'][:POSTCODE_MAX_LENGTH].upper())
            hash = hashString(row['pass'])
            if not row['fname'] or not row['lname'] or not row['postcode']:
                flash("Empty field found in CSV file. Please make sure that all fields are filled out with the appropriate data.")
                return None
            voters.append(Voter(makeID(), election_id, name, postcode,
                                uname, dob, hash))
    return voters

def stringToHex(string: str) -> str:
    """Converts string to base-64 encoding after encoding as UTF-8."""
    return b64encode(string.encode('utf-8'))

def hexToString(hex_string: str) -> str:
    """Decodes base-64 encoded string."""
    return b64decode(hex_string).decode('utf-8')

def bytestrToPoint(bytestring: str) -> Point:
    """
    Given a hex representation of a Point object, return it converted into a
    Point object.
    """
    return Point.from_bytes(NIST256p.curve, bytes.fromhex(bytestring))

def pointToBytestr(point: Point) -> str:
    """
    Returns the hexadecimal representation of the byte-encoding of a Point
    object.
    """
    return point.to_bytes().hex()

def sKeyToBytestr(key: Union[SigningKey, VerifyingKey]) -> str:
    """
    Returns the hexadecimal representation of the byte-encoding of a SigningKey
    or VerifyingKey object.
    """
    return key.to_string().hex()

def bytestrToVKey(bytestring: str) -> VerifyingKey:
    """
    Given a hex representation of a NIST256p public key, returns it as a
    VerifyingKey object.
    """
    return VerifyingKey.from_string(bytes.fromhex(bytestring), curve=NIST256p)

def bytestrToSKey(bytestring: str) -> SigningKey:
    """
    Given a hex representation of a NIST256p private key, returns it as a
    SigningKey object.
    """
    return SigningKey.from_string(bytes.fromhex(bytestring), curve=NIST256p)

def prettyReceipt(receipt: str) -> str:
    """Returns a 'pretty print' version of a receipt string."""
    first = " ".join([receipt[i:i+5] for i in range(0, len(receipt)//2, 5)])
    second = " ".join([receipt[i:i+5] for i in range(len(receipt)//2, len(receipt), 5)])
    return f"{first}<br>{second}"

def validateHash(user_code: str, db_hash: str) -> bool:
    """
    Given a user's election code, checks that its hash matches with the stored
    value when passed through hash function.
    """
    return hashString(user_code) == db_hash

def hexToMpz(hexstring: Union[str, int]) -> mpz:
    """Converts a hexstring or int to an mpz object."""
    if isinstance(hexstring, int):
        return mpz(hexstring)
    return gmpy2.mpz_from_old_binary(bytes.fromhex(hexstring))

def truncHash(hash_str: str) -> str:
    """
    Given some string digest of a hash, truncate to the first HASH_LENGTH
    characters for ease of comparison for the user.
    """
    return hash_str.upper()[HASH_LENGTH:]

def firstReceipt(question: Question, election_id: str, voter_id: str,
                 choices: List[str]) -> Optional[dict]:
    from db import getNewBallotID, insertNewBallot, insertReceipt, addNumProofs

    # get a new ballot ID for this ballot
    ballot_id = int(getNewBallotID(question.question_id))
    num_choices = len(question.choices)
    R_list = []
    Z_list = []
    r_list = []
    choice_list = []

    # insert ballot into database
    if insertNewBallot(ballot_id, question.question_id, election_id) is None:
        flash("Could not add a ballot for your vote to the database!", "error")
        return None

    for choice in range(num_choices):
        # was this choice voted on?
        voted = choice in choices
        
        # make cryptograms
        r = generateRandSecret()
        R = generateR(question.gen_2, r)
        Z = generateZ(r, int(voted))

        # make proof of well-formedness
        c_1, c_2, r_1, r_2 = generateZKProof(question.question_id,
                                             question.gen_2, R, Z, r)

        # add receipt to database for this ballot
        if insertReceipt(ballot_id, hex(r)[2:], R, Z, r_1, r_2, c_1, c_2,
                         choice, voted) is None:
            flash("Could not finish making your ballot receipt", "error")
            return None
        
        choice_list.append({
            "choice": question.choices[choice],
            "index": choice,
            "Z": pointToBytestr(Z),
            "R": pointToBytestr(R),
            "c_1": c_1,
            "c_2": c_2,
            "r_1": r_1,
            "r_2": r_2
            })

        # add receipts and secret to list for final proof
        R_list.append(R)
        Z_list.append(Z)
        r_list.append(r)

    # calculate the extra proof to ensure number of choices is correct
    num_c, num_r = generateNumProof(question.question_id, question.gen_2,
                                    R_list, Z_list, r_list, num_choices)
    if addNumProofs(ballot_id, num_c, num_r) is None:
        flash("Could not generate the final proof for your ballot", "error")
        return None

    receipt_data = {
        "ballot_id":ballot_id,
        "question_id":question.question_id,
        "num_proof_c": num_c,
        "num_proof_r": num_r,
        "max_answers": question.max_answers,
        "choices": choice_list
        }
    
    return receipt_data

def auditBallot(ballot_id: int) -> Optional[dict]:
    """Marks a ballot as 'audited' and adds its secrets."""
    from db import updateAuditBallot, getBallotData
    new_receipt = {
        "ballot_id": ballot_id,
        "state": "AUDITED",
        "choices": []
        }
    secret_list = getBallotData(ballot_id)
    if secret_list is None:
        return None
    
    for i in range(len(secret_list)):
        secret, voted = secret_list[i]
        new_receipt['choices'].append({
            'r': secret,
            'voted': bool(voted)})
    updateAuditBallot(ballot_id, audited=True)
    return new_receipt

def confirmBallot(ballot_id: dict, num_choices: int) -> Optional[dict]:
    """Marks a ballot as 'confirmed' and marks its secrets as DELETED."""
    from db import updateAuditBallot
    new_receipt = {
        "ballot_id": ballot_id,
        "state": "CONFIRMED",
        "choices": []
        }
    for i in range(num_choices):
        new_receipt['choices'].append({
            'r': "DELETED",
            'voted': "DELETED"})
        old_receipt['choices'][i]['r'] = "DELETED"
        old_receipt['choices'][i]['voted'] = "DELETED"
    updateAuditBallot(ballot_id, audited=False)
    return old_receipt

def electionTotals(election: Election) -> Optional[dict]:
    """
    Given an election object, returns a dictionary of the totals
    calculated for it.
    """
    from db import getQuestionTallies
    totals = {}
    for question in election.questions:
        totals[question.question_id] = []
        results = getQuestionTallies(question.question_id)
        if results is None:
            flash(f"Could not get tallies for question ID: {question.question_id}",
                  "error")
            return None
        for choice, tally, sum in results:
            totals[question.question_id].append({
                "choice": choice,
                "tally": tally,
                "sum": sum
                })
    return totals

def makeElectionJson(election: Election) -> Optional[bool]:
    """
    Given an election ID, returns a JSON file containing all election data for
    verification.
    """
    from db import getJSONBallots, getPrivateKey, getChoiceTallies
    filepath = os.path.join(current_app.config["JSON_FOLDER"],
                            f"{election.election_id}.json")
    if os.path.exists(filepath):
        return True

    # get all audited/confirmed ballots
    ballots = getJSONBallots(election)
    if ballots is None:
        return False

    # get the generators and choice tallies for each question
    choices = getChoiceTallies(election)
    if choices is None:
        return False
    
    questions = {}
    for question in election.questions:
        questions[question.question_id] = {
            "gen_1": pointToBytestr(question.gen_1),
            "gen_2": pointToBytestr(question.gen_2),
            "choices": choices[question.question_id]
            }

    # put all data into single dictionary
    json_dict = {
        "election_data": {
            "election_id": election.election_id,
            "questions": questions,
            "ballots": ballots
            }
        }

    # sign data and provide public key
    private_key = getPrivateKey()
    json_dict['public_key'] = sKeyToBytestr(private_key.verifying_key)
    json_dict['hash'] = hashString(json.dumps(json_dict['election_data']))
    json_dict['sign'] = signData(json_dict['hash'], private_key)

    with open(filepath, 'w') as f:
        f.write(json.dumps(json_dict))

    return True

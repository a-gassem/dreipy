import sqlite3
import os
from typing import Optional, List, Tuple, Dict, Any
from ast import literal_eval
from base64 import b64decode

from helpers import (_getVoters, validateHash, bytestrToPoint, pointToBytestr,
                     generateSession, parseTime, bytestrToSKey, sKeyToBytestr,
                     hexToMpz)
from Election import Election
from Status import Status, checkStatus
from Question import Question
from crypto import generateKeyPair

import click
from gmpy2 import mpz
from ecdsa import SigningKey
from ecdsa.ellipticcurve import Point
from flask import Flask, current_app, g
from flask.cli import with_appcontext

# Define SQL queries in global scope as they are reused many times

# insert an election with these
choiceSql = """INSERT INTO choices
(question_id, index_num, text, tally_total, sum_total)
VALUES (?, ?, ?, 0, 0);"""

questionSql = """INSERT INTO questions
(question_id, text, question_num, num_answers, gen_2)
VALUES (?, ?, ?, ?, ?);"""

electionSql = """INSERT INTO elections
(election_id, title, start_time, end_time) VALUES (?, ?, ?, ?);"""

electionQuestionSql = """INSERT INTO election_questions
(election_id, question_id) VALUES (?, ?);"""

inVoterSql = """INSERT INTO voters
(voter_id, session_id, election_id, pass_hash, full_name, dob, postcode, uname,
finished_voting, current_question) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, 1);"""

# reconstruct an election with these
fetchElection = """SELECT title, start_time, end_time
FROM elections
WHERE election_id = ? LIMIT 1;"""

fetchQuestions = """SELECT question_id, text, num_answers, gen_2
FROM questions NATURAL JOIN election_questions
WHERE election_id = ? ORDER BY question_num ASC;"""

fetchNumQuestions = """SELECT COUNT(question_id) AS num_qs
FROM election_questions WHERE election_id = ?;"""

fetchChoices = """SELECT text
FROM choices
WHERE question_id = ? ORDER BY index_num ASC;"""

fetchChoiceText = """SELECT text
FROM choices
WHERE question_id = ? AND index_num = ? LIMIT 1;"""

fetchElectionQuestion = """SELECT question_id, text, num_answers, gen_2
FROM questions NATURAL JOIN election_questions
WHERE (election_questions.election_id = ?) AND (questions.question_num = ?);"""

# get voter info with these
fetchVoter = """SELECT election_id, pass_hash, session_id, finished_voting,
current_question
FROM voters
WHERE election_id = ? AND uname = ? LIMIT 1;"""

fetchSession = """SELECT election_id, current_question
FROM voters
WHERE session_id = ? LIMIT 1;"""

fetchSessionVoter = """SELECT voter_id
FROM voters WHERE session_id = ? LIMIT 1;"""

fetchVoterQuestion = """SELECT current_question
FROM voters WHERE voter_id = ? LIMIT 1;"""

newVoterQuestion = """UPDATE voters
SET current_question = ? WHERE voter_id = ?;"""

finishVoterElection = """UPDATE voters
SET finished_voting = 1 WHERE voter_id = ?;"""

# validate election data with these
checkElectionId = """SELECT election_id
FROM elections
WHERE election_id = ? LIMIT 1;"""

checkElectionDates = """SELECT start_time, end_time
FROM elections
WHERE election_id = ? LIMIT 1;"""

# ballot operations
fetchTopBallotID = """SELECT MAX(ballot_id) as max_id
FROM ballots
WHERE question_id = ? LIMIT 1;"""

insertNewBallot = """INSERT INTO ballots
(ballot_id, election_id, voter_id, first_sign, hash, second_sign, choice_index, question_id,
was_audited, random_receipt, vote_receipt, random_secret, r_1, r_2, c_1, c_2,
num_r, num_c)
VALUES (?, ?, ?, NULL, NULL, NULL, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, NULL, NULL);"""

addNumToBallot = """UDPDATE ballots
SET num_r = ?, num_c = ?
WHERE ballot_id = ?;"""

updateFirstReceipt = """UPDATE ballots
SET first_sign = ?, hash = ? WHERE ballot_id = ?;"""

fetchBallotData = """SELECT random_receipt, vote_receipt, random_secret,
choice_index, text, c_1, c_2, r_1, r_2
FROM ballots NATURAL JOIN choices
WHERE ballots.ballot_id = ? AND choices.index_num = ballots.choice_index;"""

updateAuditData = """UPDATE ballots
SET was_audited = ? WHERE ballot_id = ?;"""

updateAuditSign = """UPDATE ballots
SET second_sign = ? WHERE ballot_id = ?;"""

deleteBallotSecrets = """UPDATE ballots
SET random_secret = NULL, choice_index = NULL WHERE ballot_id = ?;""" 

deleteBallotData = """DELETE FROM ballots WHERE ballot_id = ?;"""

getAllConfirmed = """SELECT ballot_id, voter_id, first_sign, hash, question_id,
random_receipt, vote_receipt, r_1, r_2, c_1, c_2
FROM ballots WHERE election_id = ?
AND was_audited IS NOT NULL
AND was_audited = 0;"""

getAllAudited = """SELECT ballot_id, voter_id, first_sign, second_sign, hash,
text, question_id, random_receipt, vote_receipt, random_secret, r_1, r_2, c_1,
c_2
FROM ballots NATURAL JOIN choices
WHERE ballots.election_id = ?
AND choices.question_id = ballots.question_id
AND choices.index_num = ballots.choice_index
AND was_audited IS NOT NULL
AND was_audited = 1;"""

getCurrentTallies = """SELECT question_id, index_num, random_secret,
tally_total, sum_total
FROM ballots NATURAL JOIN choices
WHERE ballots.ballot_id = ? AND choices.index_num = ballots.choice_index;"""

updateTallies = """UPDATE choices
SET tally_total = ?, sum_total = ?
WHERE question_id = ? AND index_num = ?;"""

tallyVotes = """SELECT text, tally_total, sum_total
FROM choices
WHERE question_id = ? ORDER BY index_num ASC;"""

# key operations
deleteKeys = """DELETE FROM keys;"""

insertKeys = """INSERT INTO keys (private_k, public_k) VALUES (?, ?);"""

fetchKey = """SELECT private_k FROM keys LIMIT 1;"""

def getDBConnection() -> Optional[sqlite3.Connection]:
    """Creates a Connection object that is reused with the special 'g' variable.
If for whatever reason we are unsuccessful then we print the error message and
return None.
"""
    if 'db' not in g:
        try:
            g.db = sqlite3.connect(current_app.config["DATABASE"])
            
            # Lets us access row columns by name
            g.db.row_factory = sqlite3.Row
        except Exception as e:
            print(f"Could not connect to database: {e}")
            return None
    return g.db

def closeDB(e=None) -> None:
    """Closes the database gracefully when Flask exits."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

@click.command('init-db')
@with_appcontext
def initDB() -> Optional[bool]:
    """Code to run our schema for the database. This is executed with the
'init-db' command which we automatically run when the setup script is run. If
you would like to re-initialise the database then you can run this again but
it will CLEAR ALL DATA in the database so use it carefully.
"""
    con = getDBConnection()
    if con is None:
        return None
    try:
        with current_app.open_resource("schema.sql") as f:
            con.executescript(f.read().decode('utf8'))
            con.commit()
            click.echo("Database initialised successfully.")
            return True
    except Exception as e:
        click.echo(f"Could not initialise database: {e}")
        return None
    finally:
        con.close()

@click.command('init-keys')
@with_appcontext
def initKeys() -> Optional[bool]:
    """Code to generate and store a public-private key pair. Note running this
command will overwrite the previous key pair!"""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        private, public = generateKeyPair()
        cur.execute(deleteKeys)
        cur.execute(insertKeys, (sKeyToBytestr(private), sKeyToBytestr(public)))
        con.commit()
        click.echo("New key pair successfully generated!")
        return True
    except Exception as e:
        click.echo(f"Could not make key pair: {e}")
        return None
    finally:
        cur.close()

def initApp(main: Flask) -> None:
    main.teardown_appcontext(closeDB)
    main.cli.add_command(initDB)
    main.cli.add_command(initKeys)

def insertVoters(election_id: str, filepath: str, delim: str,
                 cur: sqlite3.Cursor) -> Optional[bool]:
    """Given a valid voter CSV file, inserts all voters into the database."""
    voterList = _getVoters(election_id, filepath, delim)
    try:
        for voter in voterList:
            cur.execute(inVoterSql, (voter.voter_id, generateSession(),
                                     election_id, voter.hash, voter.name,
                                     voter.dob, voter.postcode, voter.email))
    except Exception as e:
        print(f"Could not insert voters: {e}")
        return None
    return True

def insertElection(election: Election, csvPath: str, delim: str) \
    -> Optional[List[str]]:
    """Takes an Election object, inserts all of its Questions, Choices and other
data into the database. Returns None if we encounter an error -- True otherwise."""

    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        # insert voters from CSV file
        if insertVoters(election.election_id, csvPath, delim, cur) is None:
            raise Exception
        
        # insert election metadata
        cur.execute(electionSql, (election.election_id, election.title,
                                  election.start_time, election.end_time))
        
        # insert questions
        cur.executemany(questionSql, election.sql_questions)

        # link all the questions with this given election
        cur.executemany(electionQuestionSql, list(map(lambda x:
                                                      (election.election_id, x.question_id),
                                                      election.questions)))
        # insert choices
        for question in election.questions:
            cur.executemany(choiceSql, question.sql_choices)
        con.commit()
        return True
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def getElectionFromDb(election_id: str) -> Tuple[Optional[Election], List[str]]:
    """Called when an Election object with the given ID is not already in memory.
Tries to find the Election in the database and return it for quick access later."""
    con = getDBConnection()
    if con is None:
        return None
    errors = []
    try:
        cur = con.cursor()
        # first find election
        row = cur.execute(fetchElection, (election_id,)).fetchone()
        if row is None:
            errors.append(f"No elections found with ID: {election_id}. Double \
check that you have typed it in correctly and try again.")
            raise Exception
        # then parse main metadata
        title, start_time, end_time = row
        start_time = parseTime(start_time)
        end_time = parseTime(end_time)
        if start_time is None:
            errors.append("The start time could not be parsed into a datetime object.")
            raise Exception
        if end_time is None:
            errors.append("The end time could not be parsed into a datetime object.")
            raise Exception
        # fetch its questions
        rows = cur.execute(fetchQuestions, (election_id,)).fetchall()
        if rows is None:
            errors.append(f"No questions found for election ID: {election_id}. Double \
check that you have typed it in correctly and try again.")
            raise Exception
        election_questions = []
        for question_id, query, max_answers, g2 in rows:
            sub_rows = cur.execute(fetchChoices, (question_id,)).fetchall()
            if sub_rows is None:
                errors.append(f"No choices found for question: {index_num} in\
election {election_id}.")
                raise Exception
            choices = [row['text'] for row in sub_rows]
            election_questions.append(Question(question_id, query, max_answers,
                                               choices, bytestrToPoint(g2)
                                               )
                                      )
        new_election = Election(election_id, title, election_questions,
                                start_time, end_time)
        return new_election, errors
    except Exception as e:
        print(e)
        return None, errors
    finally:
        cur.close()
        
def isElectionInDb(election_id: str) -> bool:
    """Given an election ID, check whether an election exists with that ID
in the database."""
    con = getDBConnection()
    if con is None:
        return False
    try:
        cur = con.cursor()
        if cur.execute(checkElectionId, (election_id,)).fetchone() is None:
            return False
        return True
    except Exception as e:
        print(e)
        return False
    finally:
        cur.close()

def getElectionStatus(election_id: str) -> Optional[Status]:
    """Given an election ID, returns its Status if it exists otherwise return None"""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        row = cur.execute(checkElectionDates, (election_id,)).fetchone()
        if row is None:
            return None
        start_time, end_time = row
        start_time = parseTime(start_time)
        end_time = parseTime(end_time)
        return checkStatus(start_time, end_time)
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def validSessionData(session_id: str, election_id: str, question_num: int) \
    -> bool:
    """Checks that the passed session data aligns with what is stored in the
database."""
    con = getDBConnection()
    if con is None:
        return False
    try:
        cur = con.cursor()
        # check the session even exists
        row = cur.execute(fetchSession, (session_id,)).fetchone()
        if row is None:
            return False
        # unpack the session and check with passed values
        db_election_id, db_question_num = row
        return election_id == db_election_id \
               and question_num == int(db_question_num)
    except Exception as e:
        print(e)
        return False
    finally:
        cur.close()

def getVoterFromDb(email: str, code: str, election_id: str) \
    -> Optional[Dict[str, Any]]:
    """Given an email, login code and election id, attempts to fetch the
corresponding voter data from the database; returns all None if unsuccessful."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        row = cur.execute(fetchVoter, (election_id, email)).fetchone()
        if not row:
            return None
        db_election_id, db_hash, session_id, finished, q_num = row
        if election_id != db_election_id \
           or not validateHash(code, db_hash):
            return None
        return {'session_id':session_id,
                'question':int(q_num),
                'finished':bool(finished)}
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def getVoterFromSession(session_id: str) -> Optional[str]:
    """Given a session ID, returns the corresponding voter ID."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        row = cur.execute(fetchSessionVoter, (session_id,)).fetchone()
        if not row:
            return None
        return row['voter_id']
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def getElectionQuestion(election_id: str, question_num: int) \
    -> Optional[Question]:
    """Given an election ID and question number, returns a constructed Question
object from the database if possible; otherwise return None."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        row = cur.execute(fetchElectionQuestion, (election_id, question_num)).fetchone()
        if not row:
            return None
        question_id, query, num_answers, g2 = row
        rows = cur.execute(fetchChoices, (question_id,)).fetchall()
        if not rows:
            return None
        return Question(question_id, query, num_answers,
                        [choice['text'] for choice in rows],
                        bytestrToPoint(g2)
                        )
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def getNewBallotID(question_id: str) -> Optional[int]:
    """Returns a new ballot ID for the given question."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        row = cur.execute(fetchTopBallotID, (question_id,)).fetchone()
        if not row:
            return None
        # base case for the first ballot
        if row['max_id'] is None:
            return 0
        return int(row['max_id']) + 1
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def getPrivateKey() -> Optional[SigningKey]:
    """Returns the private key for the current database."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        row = cur.execute(fetchKey).fetchone()
        if row is None:
            return None
        return bytestrToSKey(row['private_k'])
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def insertBallot(ballot_id: str, question_id: str, r: mpz, R: Point,
                 Z: Point, r_1: mpz, r_2: mpz, c_1: mpz, c_2: mpz,
                 index: int, election_id: str, voter_id: str) \
                 -> Optional[bool]:
    """Inserts a ballot for a given question choice with its receipts and
secrets."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        cur.execute(insertNewBallot, (int(ballot_id), election_id, voter_id,
                                      index, question_id, pointToBytestr(R),
                                      pointToBytestr(Z), hex(r)[2:],
                                      hex(r_1)[2:], hex(r_2)[2:],
                                      hex(c_1)[2:], hex(c_2)[2:]))
        con.commit()
        return True
    except Exception as e:
        print(e)
        deleteBallot(ballot_id)
        return None
    finally:
        cur.close()

def addNumProofs(ballot_id: str, proof_c: mpz, proof_r: mpz) -> Optional[bool]:
    """Adds the extra proof needed for questions with more than two choices."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        cur.execute(addNumToBallot, (hex(proof_r)[2:], hex(proof_c)[2:],
                                     int(ballot_id)))
        con.commit()
        return True
    except Exception as e:
        print(e)
        deleteBallot(ballot_id)
        return None
    finally:
        cur.close()

def updateVoteReceipt(signature: str, data_hash: str, ballot_id: str) \
    -> Optional[bool]:
    """Updates a ballot with its signature and hash in the database."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        cur.execute(updateFirstReceipt, (signature, data_hash, int(ballot_id)))
        con.commit()
        return True
    except Exception as e:
        print(e)
        deleteBallot(ballot_id)
        return None
    finally:
        cur.close()

def deleteBallot(ballot_id: str) -> Optional[bool]:
    """Deletes the ballot with the given ID. Used if an error occurs upon the
audit or confirmation of a partially submitted ballot."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        rows = cur.execute(deleteBallotData, (int(ballot_id),))
        con.commit()
        return True
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()
    
def getBallotData(ballot_id: str) -> Optional[List[Tuple]]:
    """Returns the relevant receipts for a given ballot."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        rows = cur.execute(fetchBallotData, (int(ballot_id),)).fetchall()
        if not rows:
            return None
        return rows
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def updateAuditBallot(ballot_id: str, audited: bool) -> Optional[bool]:
    """Marks a ballot with was_audited=True or False depending on if it was
confirmed or not."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        cur.execute(updateAuditData, (int(audited), int(ballot_id)))
        con.commit()
        return True
    except Exception as e:
        print(e)
        deleteBallot(ballot_id)
        return None
    finally:
        cur.close()

def updateAuditReceipt(ballot_id: str, signature: str) -> Optional[bool]:
    """Updates an audited ballot with the signature of it """
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        cur.execute(updateAuditSign, (signature, int(ballot_id)))
        con.commit()
        return True
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def deleteSecrets(ballot_id: str) -> Optional[bool]:
    """Deletes the vote and random secret from a confirmed ballot."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        cur.execute(deleteBallotSecrets, (int(ballot_id),))
        con.commit()
        return True
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def incrementTallies(ballot_id: str) -> Optional[bool]:
    """Increases the tallies for the relevant choices for a given ballot."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        rows = cur.execute(getCurrentTallies, (int(ballot_id),)).fetchall()
        if rows is None:
            return None
        for q_id, index, secret, current_tally, current_sum in rows:
            new_tally = current_tally + 1
            new_sum = hexToMpz(current_sum) + hexToMpz(secret)
            cur.execute(updateTallies, (new_tally, hex(new_sum)[2:], q_id, index))
        con.commit()
        return True
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def totalQuestions(election_id: str) -> Optional[int]:
    """Returns the total number of questions in a given election."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        row = cur.execute(fetchNumQuestions, (election_id,)).fetchone()
        if row is None:
            return None
        return row['num_qs']
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def nextQuestion(voter_id: str) -> Optional[int]:
    """Given a voter's ID, increments their question in the database and
returns it."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        row = cur.execute(fetchVoterQuestion, (voter_id,)).fetchone()
        if row is None:
            return None
        new_question = row['current_question'] + 1
        cur.execute(newVoterQuestion, (new_question, voter_id))
        con.commit()
        return new_question
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def completeVoting(voter_id: str) -> Optional[bool]:
    """Given a voter's ID, marks them as having completed their election."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        cur.execute(finishVoterElection, (voter_id,))
        con.commit()
        return True
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def getConfirmedReceipts(election_id: str) -> Optional[List]:
    """Given an election, return a list of the confirmed receipts for it."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        rows = cur.execute(getAllConfirmed, (election_id,)).fetchall()
        if rows is None:
            return None
        receipts = []
        for ballot_id, voter, sign_1, hash, q_id, R, Z, r_1, r_2, c_1, c_2 \
            in rows:
            receipts.append({"voter": voter,
                             "receipt":{
                                 "ballot_id":ballot_id,
                                 "question_id":q_id,
                                 "signature":sign_1,
                                 "hash":hash,
                                 "R":R,
                                 "Z":Z,
                                 "proof":{
                                     "r_1":r_1,
                                     "r_2":r_2,
                                     "c_1":c_1,
                                     "c_2":c_2}
                                 }
                             })
            
        return receipts
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def getAuditedReceipts(election_id: str) -> Optional[List]:
    """Given a voter's ID, returns a list of their receipts for the election."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        rows = cur.execute(getAllAudited, (election_id,)).fetchall()
        if rows is None:
            return None
        receipts = []
        for ballot_id, voter, sign_1, sign_2, hash, choice, q_id, R, Z, r, r_1, \
            r_2, c_1, c_2 in rows:
            receipts.append({"voter": voter,
                             "receipt":{
                                 "ballot_id":ballot_id,
                                 "question_id":q_id,
                                 "signature":sign_2,
                                 "choice":choice,
                                 "secret":r,
                                 "hash":hash,
                                 "R":R,
                                 "Z":Z,
                                 "proof":{
                                     "r_1":r_1,
                                     "r_2":r_2,
                                     "c_1":c_1,
                                     "c_2":c_2}
                                 }
                             })
        return receipts
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def getQuestionTallies(question_id: str) -> Optional[List[Tuple]]:
    """Given a question, returns the tallies and sums for all its choices."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        rows = cur.execute(tallyVotes, (question_id,)).fetchall()
        if rows is None:
            return None
        return rows
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

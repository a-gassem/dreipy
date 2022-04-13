import sqlite3
import os
from typing import Optional, List, Tuple, Dict, Any
from ast import literal_eval
from base64 import b64decode

from helpers import (validateHash, bytestrToPoint, pointToBytestr,
                     generateSession, parseTime, bytestrToSKey, sKeyToBytestr,
                     hexToMpz, truncHash)
from Election import Election
from Voter import Voter
from Status import Status, checkStatus
from Question import Question
from crypto import generateKeyPair

import click
from gmpy2 import mpz
from ecdsa import SigningKey
from ecdsa.ellipticcurve import Point
from flask import Flask, current_app, g, flash
from flask.cli import with_appcontext

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
        cur.execute("DELETE FROM keys;")
        cur.execute("INSERT INTO keys (private_k, public_k) VALUES (?, ?);",
                    (sKeyToBytestr(private), sKeyToBytestr(public))
                    )
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

def insertVoters(voters: List[Voter], election_id: str, cur: sqlite3.Cursor) \
    -> Optional[bool]:
    """Given a valid voter CSV file, inserts all voters into the database."""
    try:
        for voter in voters:
            cur.execute("""INSERT INTO voters (voter_id, election_id,
                        pass_hash, full_name, dob, postcode, uname, finished_voting,
                        current_question) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 1);""",
                        (voter.voter_id, election_id, voter.hash, voter.name,
                         voter.dob, voter.postcode, voter.uname)
                        )
        return True  
    except Exception as e:
        print(f"Could not insert voters: {e}")
        return None

def insertElection(election: Election, voters: List[Voter]) \
    -> Optional[List[str]]:
    """Takes an Election object, inserts all of its Questions, Choices and other
data into the database. Returns None if we encounter an error -- True otherwise."""

    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        # insert election metadata
        cur.execute("""INSERT INTO elections (election_id, title, start_time,
                    end_time, contact) VALUES (?, ?, ?, ?, ?);""",
                    (election.election_id, election.title, election.start_time,
                     election.end_time, election.contact)
                    )
        
        # insert questions
        cur.executemany("""INSERT INTO questions
                        (question_id, text, question_num, num_answers, gen_2)
                        VALUES (?, ?, ?, ?, ?);""", election.sql_questions)

        # link all the questions with this given election
        cur.executemany("""INSERT INTO election_questions (election_id, question_id)
                        VALUES (?, ?);""", list(map(lambda x:
                                                    (election.election_id, x.question_id),
                                                    election.questions))
                        )
        
        # insert choices
        for question in election.questions:
            cur.executemany("""INSERT INTO choices 
                            (question_id, index_num, text, tally_total, sum_total) 
                            VALUES (?, ?, ?, 0, 0);""", question.sql_choices)
        # insert voters from CSV file
        if insertVoters(voters, election.election_id, cur) is None:
            raise Exception
        con.commit()
        return True
    except Exception as e:
        print(f"Could not insert election: {e}")
        return None
    finally:
        cur.close()

def getElectionFromDb(election_id: str) -> Tuple[Optional[Election], List[str]]:
    """Called when an Election object with the given ID is not already in memory.
Tries to find the Election in the database and return it for quick access later."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        # first find election
        row = cur.execute("""SELECT title, start_time, end_time, contact
                            FROM elections
                            WHERE election_id = ? LIMIT 1;""", (election_id,)
                          ).fetchone()
        if row is None:
            flash(f"""No elections found with that ID. Double
                    check that you have typed it in correctly and try again.""", "error")
            raise Exception
        # then parse main metadata
        title, start_time, end_time, contact = row
        start_time = parseTime(start_time)
        end_time = parseTime(end_time)
        if start_time is None:
            print("The start time could not be parsed into a datetime object.")
            raise Exception
        if end_time is None:
            print("The end time could not be parsed into a datetime object.")
            raise Exception
        # fetch its questions
        rows = cur.execute("""SELECT q.question_id
                            FROM election_questions AS e
                            INNER JOIN questions AS q
                            ON e.question_id = q.question_id
                            WHERE e.election_id = ?
                            ORDER BY q.question_num ASC;""", (election_id,)
                           ).fetchall()
        if rows is None:
            flash(f"""No questions found for that election ID. Double
                    check that you have typed it in correctly and try again.""", "error")
            raise Exception
        election_questions = []
        for row in rows:
            question = getQuestionById(row['question_id'])
            if question is None:
                print("Could not create question object.")
                return None
            election_questions.append(question)
        return Election(election_id, title, election_questions,
                                start_time, end_time, contact)
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def getQuestionByNum(election_id: str, question_num: int) \
    -> Optional[Question]:
    """
    Given a question's ID, returns a constructed Question
    object from the database if possible; otherwise return None.
    """
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        row = cur.execute("""SELECT q.question_id, text, num_answers, gen_2
                            FROM questions AS q
                            INNER JOIN election_questions AS e
                            ON q.question_id = e.question_id
                            WHERE (e.election_id = ?) AND (q.question_num = ?)
                            LIMIT 1;""", (election_id, question_num)
                          ).fetchone()
        if not row:
            return None
        question_id, query, num_answers, g2 = row
        rows = cur.execute("""SELECT text FROM choices WHERE question_id = ? ORDER BY
                            index_num ASC;""", (question_id,)
                           ).fetchall()
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

def getQuestionById(question_id: str) -> Optional[Question]:
    """
    Given a question's ID, returns a constructed Question
    object from the database if possible; otherwise return None.
    """
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        row = cur.execute("""SELECT text, num_answers, gen_2
                            FROM questions WHERE (question_id = ?)
                            LIMIT 1;""", (question_id,)
                          ).fetchone()
        if not row:
            return None
        query, num_answers, g2 = row
        rows = cur.execute("""SELECT text FROM choices WHERE question_id = ?
                            ORDER BY index_num ASC;""", (question_id,)
                           ).fetchall()
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
        
def isElectionInDb(election_id: str) -> bool:
    """Given an election ID, check whether an election exists with that ID
in the database."""
    con = getDBConnection()
    if con is None:
        return False
    try:
        cur = con.cursor()
        return cur.execute("""SELECT election_id FROM elections
                            WHERE election_id = ? LIMIT 1;""", (election_id,)
                           ).fetchone() is not None
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
        row = cur.execute("""SELECT start_time, end_time FROM elections
                            WHERE election_id = ? LIMIT 1;""", (election_id,)
                          ).fetchone()
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

def validVoterData(voter_id: str, election_id: str, question_num: int) \
    -> bool:
    """Checks that the passed session data aligns with what is stored in the
database."""
    con = getDBConnection()
    if con is None:
        return False
    try:
        cur = con.cursor()
        # check the session even exists
        row = cur.execute("""SELECT election_id, current_question FROM voters
                            WHERE voter_id = ? LIMIT 1;""", (voter_id,)
                          ).fetchone()
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

def getVoterFromDb(username: str, code: str, election_id: str) \
    -> Optional[Dict[str, Any]]:
    """Given an email, login code and election id, attempts to fetch the
corresponding voter data from the database; returns all None if unsuccessful."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        row = cur.execute("""SELECT voter_id, election_id, pass_hash,
                            full_name, dob, postcode, finished_voting,
                            uname, current_question
                            FROM voters WHERE election_id = ?
                            AND uname = ? LIMIT 1;""", (election_id, username)
                          ).fetchone()
        if not row:
            return None
        (voter_id, db_election_id, db_hash, name, dob, postcode,
         finished, uname, q_num) = row
        if election_id != db_election_id \
           or not validateHash(code, db_hash):
            return None
        return Voter(voter_id, election_id, name, postcode, uname, dob, db_hash,
                     bool(finished), int(q_num))
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def getVoterById(voter_id: str) -> Optional[Voter]:
    """Given a voter ID, returns the corresponding voter or None if there is
no voter with that ID."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        row = cur.execute("""SELECT voter_id, election_id, pass_hash,
                            full_name, dob, postcode, finished_voting,
                            uname, current_question
                            FROM voters WHERE voter_id = ?
                            LIMIT 1;""", (voter_id,)
                          ).fetchone()
        if not row:
            return None
        (voter_id, election_id, hash, name, dob, postcode,
         finished, uname, q_num) = row
        return Voter(voter_id, election_id, name, postcode, uname, dob, hash,
                     bool(finished), int(q_num))
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
        row = cur.execute("""SELECT MAX(ballot_id) as max_id FROM ballots
                            LIMIT 1;""").fetchone()
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
        row = cur.execute("SELECT private_k FROM keys LIMIT 1;").fetchone()
        if row is None:
            return None
        return bytestrToSKey(row['private_k'])
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def insertBallot(ballot_id: str, question_id: str, r: str, R: Point,
                 Z: Point, r_1: str, r_2: str, c_1: str, c_2: str,
                 index: int, election_id: str, voted: bool) \
                 -> Optional[bool]:
    """Inserts a ballot for a given question choice with its receipts and
secrets (in hex form)"""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        cur.execute("""INSERT INTO ballots (ballot_id, election_id,
                    signature, hash, voted, choice_index, question_id,
                    was_audited, random_receipt, vote_receipt, random_secret,
                    r_1, r_2, c_1, c_2, num_r, num_c)
                    VALUES (?, ?, NULL, NULL, ?, ?, ?, NULL, ?, ?, ?, ?,
                    ?, ?, ?, NULL, NULL);""",
                    (int(ballot_id), election_id, voted, index, question_id,
                     pointToBytestr(R), pointToBytestr(Z), r, r_1, r_2, c_1, c_2)
                    )
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
        cur.execute("""UPDATE ballots SET num_r = ?, num_c = ?
                        WHERE ballot_id = ?;""", (proof_r, proof_c,
                                                  int(ballot_id))
                    )
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
        cur.execute("""UPDATE ballots SET signature = ?, hash = ?
                        WHERE ballot_id = ?;""", (signature, data_hash, int(ballot_id))
                    )
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
        rows = cur.execute("""DELETE FROM ballots
                            WHERE ballot_id = ?;""", (int(ballot_id),)
                           )
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
        rows = cur.execute("""SELECT DISTINCT random_secret, voted
                            FROM ballots AS b INNER JOIN choices AS c
                            ON c.index_num = b.choice_index
                            WHERE b.ballot_id = ?;""", (int(ballot_id),)
                           ).fetchall()
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
        cur.execute("""UPDATE ballots SET was_audited = ?
                        WHERE ballot_id = ?;""", (int(audited), int(ballot_id))
                    )
        con.commit()
        return True
    except Exception as e:
        print(e)
        deleteBallot(ballot_id)
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
        cur.execute("""UPDATE ballots SET random_secret = NULL,
                        voted = NULL WHERE ballot_id = ?;""" , (int(ballot_id),)
                    )
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
        rows = cur.execute("""SELECT b.question_id, choice_index, random_secret,
                            tally_total, sum_total, voted
                            FROM ballots AS b INNER JOIN choices AS c
                            ON b.choice_index = c.index_num
                            WHERE ballot_id = ?
                            AND was_audited IS NOT NULL
                            AND was_audited = 0;""", (int(ballot_id),)
                           ).fetchall()
        if rows is None:
            return None
        for q_id, index, secret, current_tally, current_sum, voted in rows:
            if bool(voted):
                new_tally = current_tally + 1
                new_sum = hex(hexToMpz(current_sum) + hexToMpz(secret))[2:]
                cur.execute("""UPDATE choices
                            SET tally_total = ?, sum_total = ?
                            WHERE question_id = ?
                            AND index_num = ?;""", (new_tally, new_sum, q_id, index)
                            )
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
        row = cur.execute("""SELECT COUNT(question_id) AS num_qs
                            FROM election_questions WHERE election_id = ?;""", (election_id,)
                          ).fetchone()
        if row is None:
            return None
        return int(row['num_qs'])
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def nextQuestion(voter_id: str, next_question: int) -> Optional[bool]:
    """Given a voter's ID, increments their question in the database and
returns it."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        cur.execute("""UPDATE voters SET current_question = ?
                        WHERE voter_id = ?;""", (next_question, voter_id)
                    )
        con.commit()
        return True
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
        cur.execute("""UPDATE voters SET finished_voting = 1
                        WHERE voter_id = ?;""", (voter_id,)
                    )
        con.commit()
        return True
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def getBallots(election: Election) -> Optional[List[dict]]:
    """
    Given an election ID, returns all of the audited and confirmed receipts
    in a list in ascending order of ballot ID.
    """
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        ballots = []
        b_rows = cur.execute("""SELECT DISTINCT ballot_id, signature, hash,
                                question_id, num_r, num_c, was_audited
                                FROM ballots
                                WHERE was_audited IS NOT NULL
                                AND election_id = ?
                                ORDER BY ballot_id ASC;""", (election.election_id,)
                             ).fetchall()

        if b_rows is None:
            return None
        for b_id, sign, hash, q_id, num_r, num_c, audited in b_rows:
            audited = bool(audited)
            if audited:
                ballot = {
                    "ballot_id": int(b_id),
                    "question_id": q_id,
                    "num_proof_c": truncHash(num_c),
                    "num_proof_r": truncHash(num_r),
                    "state": "AUDITED",
                    "choices": []
                    }
            else:
                ballot = {
                    "ballot_id": int(b_id),
                    "question_id": q_id,
                    "num_proof_c": truncHash(num_c),
                    "num_proof_r": truncHash(num_r),
                    "state": "CONFIRMED",
                    "choices": []
                    }
            rows = cur.execute("""SELECT voted, choice_index, 
                            random_receipt, vote_receipt, random_secret,
                            r_1, r_2, c_1, c_2 FROM ballots
                            WHERE was_audited IS NOT NULL
                            AND ballot_id = ?
                            ORDER BY choice_index ASC;""", (int(b_id),)
                               ).fetchall()
            if rows is None:
                return None
            question = election.getQuestion(q_id)
            for voted, index, R, Z, r, r_1, r_2, c_1, c_2 in rows:
                if audited:   
                    ballot['choices'].append({
                        "choice":question.choices[int(index)],
                        "Z": truncHash(Z),
                        "R": truncHash(R),
                        "c_1": truncHash(c_1),
                        "c_2": truncHash(c_2),
                        "r_1": truncHash(r_1),
                        "r_2": truncHash(r_2),
                        "r": truncHash(r),
                        "voted":str(bool(voted)).upper()
                        })
                else:
                    ballot['choices'].append({
                        "choice":question.choices[int(index)],
                        "Z": truncHash(Z),
                        "R": truncHash(R),
                        "c_1": truncHash(c_1),
                        "c_2": truncHash(c_2),
                        "r_1": truncHash(r_1),
                        "r_2": truncHash(r_2),
                        "r":"DELETED",
                        "voted":"DELETED"
                        })
            ballots.append(ballot)
        return ballots
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
        rows = cur.execute("""SELECT text, tally_total, sum_total FROM choices
                            WHERE question_id = ? ORDER BY index_num ASC;""", (question_id,)
                           ).fetchall()
        if rows is None:
            return None
        return rows
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

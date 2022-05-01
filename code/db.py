import sqlite3
import os
import json
from typing import Optional, List, Tuple, Dict, Any
from ast import literal_eval
from base64 import b64decode

from helpers import (validateHash, bytestrToPoint, pointToBytestr,
                     generateSession, parseTime, bytestrToSKey, sKeyToBytestr,
                     hexToMpz, truncHash, hexToString, prettyReceipt)
from Election import Election
from Voter import Voter
from Status import Status, checkStatus
from Question import Question
from crypto import generateKeyPair, g1

import click
from gmpy2 import mpz
from ecdsa import SigningKey
from ecdsa.ellipticcurve import Point
from flask import Flask, current_app, g, flash, Markup
from flask.cli import with_appcontext

def getDBConnection() -> Optional[sqlite3.Connection]:
    """
    Creates a Connection object that is reused via the special 'g' variable. If
    for whatever reason we are unsuccessful then we print the error message and
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
    """Closes the database gracefully when Flask finishes."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

@click.command('init-db')
@with_appcontext
def initDB() -> Optional[bool]:
    """
    Code to run our schema for the database. This is executed with the 'init-db'
    command which we automatically run when the setup script is run. If you
    would like to re-initialise the database then you can run this again but it
    will CLEAR ALL DATA in the database so use it carefully.
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
    """
    Code to generate and store a public-private key pair in the database.
    Note: running this command will overwrite the previous key pair!
    """
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
    """
    Add the database Flask commands, as well as the method to close the
    database on Flask exit.
    """
    main.teardown_appcontext(closeDB)
    main.cli.add_command(initDB)
    main.cli.add_command(initKeys)

def insertElection(election: Election, voters: List[Voter]) -> Optional[bool]:
    """
    Takes an Election object, inserts all of its questions, choices and other
    data into the database. Returns None if we encounter an error and True
    otherwise.
    """

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
                        (question_id, election_id, text, question_num,
                        num_answers, gen_2)
                        VALUES (?, ?, ?, ?, ?, ?);""", election.sql_questions)

        # insert choices
        for question in election.questions:
            cur.executemany("""INSERT INTO choices 
                            (question_id, index_num, text, tally_total, sum_total) 
                            VALUES (?, ?, ?, 0, 0);""", question.sql_choices)

        # insert voters
        for voter in voters:
            cur.execute("""INSERT INTO voters
                        (voter_id, election_id, pass_hash, full_name, dob,
                        postcode, uname, finished_voting, current_question)
                        VALUES (?, ?, ?, ?, ?, ?, ?, 0, 1);""",
                        (voter.voter_id, election_id, voter.hash, voter.name,
                         voter.dob, voter.postcode, voter.uname)
                        )
        con.commit()
        return True
    except Exception as e:
        print(f"Could not insert election: {e}")
        return None
    finally:
        cur.close()

def getElectionFromDb(election_id: str) -> Optional[Election]:
    """
    Tries to find the Election in the database from an ID and return it. If not
    found then returns None.
    """
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        row = cur.execute("""SELECT title, start_time, end_time, contact
                            FROM elections
                            WHERE election_id = ? LIMIT 1;""", (election_id,)
                          ).fetchone()
        if row is None:
            flash("No elections found with that ID. Double check that you have typed it in correctly and try again.", "error")
            raise Exception

        # parse time data
        title, start_time, end_time, contact = row
        start_time = parseTime(start_time)
        end_time = parseTime(end_time)
        if start_time is None:
            print("The start time could not be parsed into a datetime object.")
            raise Exception
        if end_time is None:
            print("The end time could not be parsed into a datetime object.")
            raise Exception
        
        # fetch questions
        rows = cur.execute("""SELECT question_id
                            FROM questions
                            WHERE election_id = ?
                            ORDER BY question_num ASC;""", (election_id,)
                           ).fetchall()
        if rows is None:
            flash("No questions found for that election ID. Double check that you have typed it in correctly and try again.", "error")
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
    Given a question's ID, returns a constructed Question object from the
    database if possible; otherwise return None.
    """
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        row = cur.execute("""SELECT question_id, text, num_answers, gen_2
                            FROM questions
                            WHERE (election_id = ?) AND (question_num = ?)
                            LIMIT 1;""", (election_id, question_num)
                          ).fetchone()
        if not row:
            return None
        question_id, query, num_answers, g2 = row
        rows = cur.execute("""SELECT text FROM choices
                            WHERE question_id = ?
                            ORDER BY index_num ASC;""", (question_id,)
                           ).fetchall()
        if not rows:
            return None
        return Question(question_id, election_id, query, num_answers,
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
    Given a question's ID, returns a constructed Question object from the
    database if possible; otherwise return None.
    """
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        row = cur.execute("""SELECT election_id, text, num_answers, gen_2
                            FROM questions WHERE (question_id = ?)
                            LIMIT 1;""", (question_id,)
                          ).fetchone()
        if not row:
            return None
        election_id, query, num_answers, g2 = row
        rows = cur.execute("""SELECT text FROM choices WHERE question_id = ?
                            ORDER BY index_num ASC;""", (question_id,)
                           ).fetchall()
        if not rows:
            return None
        return Question(question_id, election_id, query, num_answers,
                        [choice['text'] for choice in rows],
                        bytestrToPoint(g2)
                        )
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()
        
def isElectionInDb(election_id: str) -> bool:
    """
    Given an election ID, check whether an election exists with that ID in the
    database.
    """
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
    """
    Given an election ID, returns its corresponding election Status if it exists,
    otherwise return None.
    """
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

def getElectionContact(election_id: str) -> Optional[str]:
    """Given an election ID, returns the contact for it."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        row = cur.execute("""SELECT contact FROM elections
                            WHERE election_id = ? LIMIT 1;""", (election_id,)
                          ).fetchone()
        if row is None:
            return None
        return row['contact']
    except Exception as e:
        print(e)
        return None
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
    """
    Given a voter ID, returns the corresponding voter or None if there is
    no voter with that ID. Note that the 'hash' attribute is not assigned as
    it is not needed and is purely a security risk to include in the object now.
    """
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        row = cur.execute("""SELECT voter_id, election_id, full_name, dob,
                            postcode, finished_voting, uname, current_question
                            FROM voters WHERE voter_id = ?
                            LIMIT 1;""", (voter_id,)
                          ).fetchone()
        if not row:
            return None
        return Voter(row['voter_id'], row['election_id'], row['name'],
                     row['postcode'], row['uname'], row['dob'], "",
                     bool(row['finished']), int(row['q_num']))
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
            return 1
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

def insertReceipt(ballot_id: int, r: str, R: Point, Z: Point, r_1: str,
                  r_2: str, c_1: str, c_2: str, index: int, voted: bool) \
                 -> Optional[bool]:
    """
    Inserts a receipt for a given question choice with its cryptograms and proof.
    """
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        cur.execute("""INSERT INTO receipts (ballot_id, voted, choice_index,
                    random_receipt, vote_receipt, random_secret, r_1, r_2, c_1,
                    c_2) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);""",
                    (ballot_id, voted, index, pointToBytestr(R),
                     pointToBytestr(Z), r, r_1, r_2, c_1, c_2)
                    )
        con.commit()
        return True
    except Exception as e:
        print(e)
        deleteBallot(ballot_id)
        return None
    finally:
        cur.close()


def insertNewBallot(ballot_id: str, question_id: str, election_id: str) \
                 -> Optional[bool]:
    """Inserts a new record for a ballot for a given question and election."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        cur.execute("""INSERT INTO ballots (ballot_id, election_id, question_id,
                    was_audited, num_r, num_c, hash_1, sign_1, hash_2, sign_2,
                    json_1, json_2)
                    VALUES (?, ?, ?, NULL, NULL, NULL, NULL, NULL, NULL, NULL,
                    NULL, NULL);""",
                    (ballot_id, election_id, question_id)
                    )
        con.commit()
        return True
    except Exception as e:
        print(e)
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
                        WHERE ballot_id = ?;""", (proof_r, proof_c, ballot_id)
                    )
        con.commit()
        return True
    except Exception as e:
        print(e)
        deleteBallot(ballot_id)
        return None
    finally:
        cur.close()

def updateVoteReceipt(signature: str, data_hash: str, ballot_id: int, json_str: str,
                      first_stage: bool) \
    -> Optional[bool]:
    """
    Updates a ballot with its signature and hash for the first/second stage
    in the database.
    """
    con = getDBConnection()
    if con is None:
        deleteBallot(ballot_id)
        return None
    try:
        cur = con.cursor()
        if first_stage:
            cur.execute("""UPDATE ballots
                            SET sign_1 = ?, hash_1 = ?, json_1 = ?
                            WHERE ballot_id = ?;""", (signature, data_hash,
                                                      json_str, ballot_id)
                        )
        else:
            cur.execute("""UPDATE ballots
                            SET sign_2 = ?, hash_2 = ?, json_2 = ?
                            WHERE ballot_id = ?;""", (signature, data_hash,
                                                      json_str, ballot_id)
                        )
        con.commit()
        return True
    except Exception as e:
        print(e)
        deleteBallot(ballot_id)
        return None
    finally:
        cur.close()

def deleteBallot(ballot_id: int) -> Optional[bool]:
    """
    Deletes the ballot with the given ID. Used if an error occurs during ballot
    operations.
    """
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        rows = cur.execute("""DELETE FROM ballots
                            WHERE ballot_id = ?;""", (ballot_id,)
                           )
        con.commit()
        return True
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()
    
def getBallotData(ballot_id: str) -> Optional[List[Tuple]]:
    """Returns the secrets for a given ballot."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        rows = cur.execute("""SELECT DISTINCT random_secret, voted
                            FROM receipts AS b INNER JOIN choices AS c
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

def updateAuditBallot(ballot_id: int, audited: bool) -> Optional[bool]:
    """
    Marks a ballot with was_audited=True/False depending on if it was audited
    or not.
    """
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        cur.execute("""UPDATE ballots SET was_audited = ?
                        WHERE ballot_id = ?;""", (int(audited), ballot_id)
                    )
        con.commit()
        return True
    except Exception as e:
        print(e)
        deleteBallot(ballot_id)
        return None
    finally:
        cur.close()

def deleteSecrets(ballot_id: int) -> Optional[bool]:
    """Deletes the vote and random secret from a confirmed ballot."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        cur.execute("""UPDATE receipts SET random_secret = NULL,
                        voted = NULL WHERE ballot_id = ?;""" , (ballot_id,)
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
        rows = cur.execute("""SELECT b.question_id, r.choice_index, r.random_secret,
                            r.voted, c.tally_total, c.sum_total
                            FROM ((ballots AS b
                            INNER JOIN receipts AS r
                                ON b.ballot_id = r.ballot_id)
                            INNER JOIN choices AS c
                                ON r.choice_index = c.index_num
                                AND b.question_id = c.question_id)
                            WHERE b.ballot_id = ?
                            AND was_audited IS NOT NULL
                            AND was_audited = 0;""", (ballot_id,)
                           ).fetchall()
        if rows is None:
            return None
        for q_id, index, secret, voted, current_tally, current_sum in rows:
            # only increment for choices the user actually voted for
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
    """
    Given a voter's ID, increments their question in the database and returns
    it.
    """
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

def getQuestionTallies(question_id: str) -> Optional[List[Tuple]]:
    """Given a question, returns the tallies and sums for all its choices."""
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        rows = cur.execute("""SELECT text, tally_total, sum_total
                            FROM choices
                            WHERE question_id = ?
                            ORDER BY index_num ASC;""", (question_id,)
                           ).fetchall()
        if rows is None:
            return None
        return rows
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def getBallots(election: Election) -> Optional[dict]:
    """
    Returns a dictionary containing truncated ballot data for the bulletin
    board.
    """
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        rows = cur.execute("""SELECT ballot_id, question_id, was_audited, hash_1
                            FROM ballots WHERE was_audited IS NOT NULL
                            AND election_id = ?
                            ORDER BY ballot_id;""", (election.election_id,)
                           ).fetchall()
        if rows is None:
            flash("Could not get ballots", "error")
            return None
        ballots = []
        for b_id, q_id, audited, hash_1 in rows:
            ballot = {
                    "ballot_id": int(b_id),
                    "question_id": q_id,
                    "audited": bool(audited),
                    "pretty": Markup(prettyReceipt(truncHash(hash_1))),
                    "choices": ""
                    }

            choices = cur.execute("""SELECT text
                                    FROM ((ballots AS b
                                    INNER JOIN receipts AS r
                                            ON b.ballot_id = r.ballot_id)
                                    INNER JOIN choices AS c
                                        ON r.choice_index = c.index_num
                                            AND b.question_id = c.question_id)
                                    WHERE b.ballot_id = ?
                                    AND (was_audited = 1 AND voted = 1)
                                    ORDER BY c.index_num ASC;""", (int(b_id),)
                                  ).fetchall()
            if choices is None:
                return None

            # get choices in a pretty pretty print format
            for choice in choices:
                ballot['choices'] += f"{choice['text']};<br>"
            ballot['choices'] = Markup(ballot['choices'][:-5])
            ballots.append(ballot)
        return ballots
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def getJSONBallots(election: Election) -> Optional[dict]:
    """
    Returns a dictionary containing the non-truncated ballot data and signatures
    for a given election.
    """
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        rows = cur.execute("""SELECT hash_1, sign_1, hash_2, sign_2, json_1,
                            json_2
                            FROM ballots AS b INNER JOIN questions AS q
                            ON b.question_id = q.question_id
                            WHERE was_audited IS NOT NULL
                            AND b.election_id = ?
                            ORDER BY ballot_id;""", (election.election_id,)
                           ).fetchall()
        if rows is None:
            flash("Could not get ballots", "error")
            return None
        ballots = []
        for b_id, q_id, audited, hash_1, sign_1, hash_2, sign_2, json_1, json_2, gen_2 \
            in rows:
            audited = bool(audited)
            ballot = {
                    "stage_1": {
                        "hash": hash_1,
                        "sign": sign_1,
                        "data": json.loads(hexToString(json_1))
                        },
                    "stage_2": {
                        "hash": hash_2,
                        "sign": sign_2,
                        "data": json.loads(hexToString(json_2))
                        }
                    }
            ballots.append(ballot)
        return ballots
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

def getChoiceTallies(election: Election) -> Optional[dict]:
    """
    Returns a dictionary containing the tally data for all question choices
    in an election with the given ID.
    """
    con = getDBConnection()
    if con is None:
        return None
    try:
        cur = con.cursor()
        rows = cur.execute("""SELECT c.question_id, c.index_num, c.text,
                            c.tally_total, c.sum_total
                            FROM questions AS q INNER JOIN choices AS c
                            ON q.question_id = c.question_id
                            WHERE q.election_id = ?;""", (election.election_id,)
                           ).fetchall()
        if rows is None:
            flash("Could not get choice data")
            return None
        choices = {question.question_id:{} for question in election.questions}
        for q_id, index, choice, tally, sum in rows:
            index = str(index)
            choices[q_id][index]['text'] = choice
            choices[q_id][index]['s'] = sum
            choices[q_id][index]['t'] = tally
        return choices
    except Exception as e:
        print(e)
        return None
    finally:
        cur.close()

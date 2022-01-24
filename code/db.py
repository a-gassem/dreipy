import sqlite3
import os
from typing import Optional, List, Tuple, Dict, Any

from helpers import _getVoters, validateHash
from Election import Election
from Question import Question
from helpers import generateSession

import click
from flask import Flask, current_app, g
from flask.cli import with_appcontext

# Define SQL queries in global scope as they are reused many times

# insert an election with these
choiceSql = """INSERT INTO choices
(question_id, index_num, text) VALUES (?, ?, ?);"""
questionSql = """INSERT INTO questions
(question_id, text, question_num, num_answers) VALUES (?, ?, ?, ?);"""
electionSql = """INSERT INTO elections
(election_id, title, start_time, end_time) VALUES (?, ?, ?, ?);"""
electionQuestionSql = """INSERT INTO election_questions
(election_id, question_id) VALUES (?, ?);"""
inVoterSql = """INSERT INTO voters
(voter_id, session_id, election_id, pass_hash, full_name, dob, postcode, email,
finished_voting, current_question) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?);"""

# reconstruct an election with these
fetchElection = """SELECT (title, start_time, end_time)
FROM elections
WHERE election_id = ? LIMIT 1;"""

fetchQuestions = """SELECT (question_id, text, question_num, num_answers)
FROM questions NATURAL JOIN election_questions
WHERE election_id = ? ORDER BY index_num ASC;"""

fetchChoices = """SELECT (text)
FROM choices
WHERE question_id = ? ORDER BY index_num ASC;"""

# get voter info with these
fetchVoter = """SELECT (voter_id, election_id, pass_hash, session_id,
finished_voting, current_question)
FROM voters NATURAL JOIN sessions
WHERE election_id = ? AND email = ? LIMIT 1;"""

def getDBConnection() -> Optional[sqlite3.Connection]:
    """Creates a Connection object that is reused on multiple requests with the
special 'g' variable. If for whatever reason we are unsuccessful then we print
the error message and return None.
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

def initApp(main: Flask) -> None:
    main.teardown_appcontext(closeDB)
    # 'flask init-db' now initialises the DB
    main.cli.add_command(initDB)

def insertVoters(election_id: str, filepath: str, delim: str,
                 cur: sqlite3.Cursor) -> Optional[bool]:
    """Given a valid voter CSV file, inserts all voters into the database."""
    voterList = _getVoters(election_id, filepath, delim)
    try:
        for voter in voterList:
            cur.execute(inVoterSql, (voter.voter_id, generateSession(),
                                     election_id, voter.hash, voter.name,
                                     voter.dob, voter.postcode, voter.email,
                                     False, 1))
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
        con.close()

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
        electionMatch = cur.execute(fetchElection, (election_id,))
        if not electionMatch:
            errors.append(f"No elections found with ID: {election_id}. Double \
check that you have typed it in correctly and try again.")
            raise Exception
        # then parse main metadata
        title, start_time, end_time = electionMatch[0]
        start_time = parseTime(start_time)
        end_time = parseTime(end_time)
        if start_time is None:
            errors.append("The start time could not be parsed into a datetime object.")
            raise Exception
        if end_time is None:
            errors.append("The end time could not be parsed into a datetime object.")
            raise Exception
        # fetch its questions
        questions = cur.execute(fetchQuestions, (election_id,))
        if not questions:
            errors.append(f"No questions found for election ID: {election_id}. Double \
check that you have typed it in correctly and try again.")
            raise Exception
        election_questions = []
        for question_id, query, index_num, max_answers in questions:
            choices = cur.execute(fetchChoices, (question_id,))
            if not choices:
                errors.append(f"No choices found for question: {index_num} in\
election {election_id}.")
                raise Exception
            # CHECK IF IT'S A 1-TUPLE OR LIST OF STRINGS
            print(choices)
            election_questions.append(Question(question_id, query, max_answers, choices))
        new_election = Election(election_id, title, election_questions,
                                start_time, end_time)
        return new_election, errors
    except Exception as e:
        print(e)
        return None, errors
    finally:
        con.close()
        
def isElectionInDb(election_id: str) -> bool:
    """Given an election ID, check whether an election exists with that ID
in the database."""
    con = getDBConnection()
    if con is None:
        return False
    try:
        pass
    except Exception as e:
        print(e)
        return False
    finally:
        con.close()

def getVoterFromDb(email: str, code: str, election_id: str) \
    -> Optional[Dict[str, Any]]:
    """Given an email, login code and election id, attempts to fetch the
corresponding voter data from the database; returns all None if unsuccessful."""
    con = getDBConnection()
    if con is None:
        return None

    try:
        cur = con.cursor()
        voter = cur.execute(fetchVoter, (election_id, email))
        if not voter:
            return None
        voter_id, db_election_id, db_hash, session_id, q_num, finished = voter
        if election_id != db_election_id or \
           not validateHash(code, db_hash):
            return None
        return {'voter_id':voter_id,
                'session_id':session_id,
                'question':int(question_num),
                'finished':bool(finished)}
    except Exception as e:
        print(e)
        return None
    finally:
        con.close()

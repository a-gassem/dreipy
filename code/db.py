import sqlite3
import os
from typing import Union, List

from helpers import _getVoters
from Election import Election

import click
from flask import current_app
from flask.cli import with_appcontext



# Define SQL queries in global scope as they are reused many times
choiceSql = "INSERT INTO choices(choice_id, text, index_num) VALUES (?, ?, ?)"
questionSql = "INSERT INTO questions(question_id, text, index_num, \
max_answers) VALUES (?, ?, ?, ?)"
questionChoiceSql = "INSERT INTO question_choices(question_id, choice_id)\
VALUES (?, ?)"
electionSql = "INSERT INTO elections(election_id, start_time, end_time)\
VALUES (?, ?, ?)"
electionQuestionSql = "INSERT INTO election_questions(election_id,\
question_id) VALUES (?, ?)"

def getDBConnection():
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

def closeDB():
    """Closes the database gracefully when Flask exits."""
    db = g.pop('db', None)
    if db is not None:
        db.close()

@click.command('init-db')
@with_appcontext
def initDB():
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
            con.executescript(f.read())
            con.commit()
            click.echo("Database initialised successfully.")
            return True
    except Exception as e:
        click.echo(f"Could not initialise database: {e}")
        return None
    finally:
        con.close()

def init_app(main):
    main.teardown_appcontext(closeDB)
    # 'flask init-db' now initialises the DB
    main.cli.add_command(initDB)

def mapTups(sql_list, index, constant):
    """Helper function to go from [(..., val_0,...), (..., val_1,...)] and some
CONSTANT to -> [(CONSTANT, val_0), (CONSTANT, val_1), ...] which is better
for Cursor.executemany()"""
    return list(map(lambda tups, val: (val, tups[index]),
                    sql_list, [constant]*len(sql_list)))

def insertElection(election: Election, csvPath: str, delim: str) \
    -> Union[List[str], None]:
    """Takes an Election object, inserts all of its Questions, Choices and other
data into the database. Returns None if we encounter an error -- True otherwise."""

    voters = _getVoters(election.election_id, csvPath, delim)
    con = getDBConnection()
    if con is None:
        return None
    
    try:
        cur = con.cursor()
        # insert the election whose questions we are about to iterate through
        cur.execute(electionSql, (election.election_id, election.title,
                                  election.start_time, election.end_time))
        
        # insert all the questions for this election into the 'questions' table
        sql_questions = election.sql_questions
        cur.executemany(questionSql, sql_questions)

        # link all the questions with this given election
        cur.executemany(electionQuestionSql, mapTups(sql_questions, index=0,
                                                     constant=election.election_id))
        for q_index, question in election.questions:
            # insert all the choices for this question into the 'choices' table
            cur.executemany(choiceSql, question.sql_choices)

            # link all the choices with this given question
            cur.executemany(questionChoiceSql, mapTups(sql_choices, index=0,
                                                       constant=question.getQuestionId()))
        con.commit()
        return True
    except Exception as e:
        print(e)
        return None
    finally:
        con.close()
        



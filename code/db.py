import sqlite3

DB_NAME = "database.db"

## Creates a Connection object, then return a Cursor object for the database
# -- configure this to include any passwords, credentials and the like.
def getDBConnection():
    return sqlite3.connect(DB_NAME)

## Takes a Question object and Election object, inserts into the database
# by inserting it into the 'questions' table, then the 'election_questions'
# table. Also put the Question choices into the 'question_choices' table.
def insertElectionQ(question, election):
    con = getDBConnection()
    cur = con.cursor()

    try:
        cur.execute()

        con.commit()
    except:

    finally:
        con.close()

    

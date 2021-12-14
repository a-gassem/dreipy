import sqlite3

DB_NAME = "database.db"

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
    """Creates a Connection object, then return a Cursor object for the database
-- configure this to include any passwords, credentials and the like. If for
whatever reason we are unsuccessful then print the error message and return None"""
    try:
        return sqlite3.connect(DB_NAME)
    except Error as e:
        print(e)
        return None

def mapTups(sql_list, index, constant):
    """Helper function to go from [(..., val_0,...), (..., val_1,...)] and some
CONSTANT to -> [(CONSTANT, val_0), (CONSTANT, val_1), ...] which is better
for Cursor.executemany()"""
    return list(map(lambda tups, val: (val, tups[index]),
                    sql_list, [constant]*len(sql_list)))

def insertElection(election):
    """Takes an Election object, inserts all of its Questions, Choices and other
data into the database. Returns None if we encounter an error -- True otherwise."""
    con = getDBConnection()
    if (con is None):
        return None
    
    try:
        cur = con.cursor()
        # insert the election whose questions we are about to iterate through
        eID = election.getElectionId()
        cur.execute(electionSql, (eID, election.getStartTime(),
                                  election.getEndTime()))
        questions = election.getQuestions()

        # insert all the questions for this election into the 'questions' table
        sql_questions = election.getSqlQuestions()
        cur.executemany(questionSql, sql_questions)

        # link all the questions with this given election
        cur.executemany(electionQuestionSql, mapTups(sql_questions,
                                                     index=0, constant=eID))
        for q_index, question in questions:
            # insert all the choices for this question into the 'choices' table
            cur.executemany(choiceSql, question.getSqlChoices())

            # link all the choices with this given question
            cur.executemany(questionChoiceSql, mapTups(sql_choices, index=0,
                                                       constant=question.getQuestionId()))
        con.commit()
        con.close()
        return True
    except Error as e:
        print(e)
        con.close()
        return None
        



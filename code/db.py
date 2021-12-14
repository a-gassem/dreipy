import sqlite3

DB_NAME = "database.db"

# Define SQL queries in global scope as they are reused many times
choiceSql = "INSERT INTO choices(choice_id, text, index_num) VALUES (?, ?, ?)"
questionSql = "INSERT INTO questions(question_id, text, index_num, \
max_answers) VALUES (?, ?, ?, ?)"
questionChoiceSql = "INSERT INTO question_choices(choice_id, question_id)\
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
        for q_index, question in questions:
            # insert all the choices for this question into the 'choices' table
            sql_choices = question.getSqlChoices()
            cur.executemany(choiceSql, sql_choices)

            # link all the choices with this given question
            qID = question.getQuestionId()
            # go from [(choice_id_0,...), (choice_id_1,...)], question_id
            # to -> [(choice_id_0, question_id), (choice_id_1, question_id), ...]
            questionChoices = list(map(lambda tups, ids: (tups[0], ids),
                                       sql_choices, [qID]*len(xList)))
            cur.executemany(questionChoiceSql, questionChoices)
                
            # link this question to the election
            cur.execute(electionQuestionSql, (eID, qID))
        con.commit()
        con.close()
        return True
    except Error as e:
        print(e)
        con.close()
        return None
        



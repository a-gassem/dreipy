from flask import (Flask, render_template, redirect, session, url_for,
                   request, g)
from flask_wtf.csrf import CSRFProtect

from helpers import (parseTime, mergeTime, makeID, clearSession,
                     checkCsv, _makeFolder)

from forms import (ElectionForm, SubmitForm, ViewElectionForm, LoginForm,
                   validateDates, validateQuestions, validateUpload)
from db import (initApp, insertElection, getElectionFromDb, getVoterFromDb,
                isElectionInDb, getElectionStatus, validSessionData)

from datetime import datetime
from markupsafe import escape
import jsonpickle
import os

DB_NAME = "dreipy.sqlite"
UPLOAD_FOLDER = "uploads/"

# maximum size of the uploaded CSV file (MiB)
MAX_FILE_SIZE_LIMIT = 5
# maximum length of the uploaded CSV filename (number of characters)
MAX_FILENAME_LENGTH = 50

## THINGS TO DO BEFORE PRESENTATION:
# TODO: secure session ID generation
# TODO: secure CSRF token generation
# TODO: CSS so it's  p r e t t y
# TODO: proper hashing/validation of stuff
# TODO:

## general QoL improvements
# TODO: logging

## CAN WE NEATEN THIS UP??
main = Flask(__name__)

dbPath = os.path.join(main.instance_path, DB_NAME)
uploadPath = os.path.join(main.instance_path, UPLOAD_FOLDER)

# TODO: make sure we securely generate these -- maybe environment variable?
main.secret_key = b'_5#y2L"F4Q8z\n\xec]/'
main.config.from_mapping(
    SECRET_KEY = "TODO",
    DATABASE = dbPath,
    UPLOAD_FOLDER = uploadPath,
    MAX_CONTENT_LENGTH = MAX_FILE_SIZE_LIMIT * 1024 * 1024,
    SESSION_COOKIE_SECURE = False   # we're not using HTTPS
)

CSRFProtect(main)

# create all the relevant folders (note permissions -- are permissions
# for the files in the folder or the folder itself?)
_makeFolder(main.instance_path, permissions=750)
_makeFolder(uploadPath, permissions=750)
    
initApp(main)

@main.errorhandler(404)
def not_found(error):
    print(error)
    return render_template("not_found.html", error=error)

@main.errorhandler(413)
def file_too_large(error):
    print(error)
    sizeInMib = main.config['MAX_CONTENT_LENGTH'] // (1024**2)
    session["errors"] = [f"You tried to upload a file that was too large. Please\
 only upload files with size up to {sizeInMib}MiB."]
    return redirect(url_for("create"))

@main.route("/")
def splash():
    # clear any session variables that we should not keep for this page
    clearSession(session)
    session['errors'] = []
    return render_template("splash.html")

@main.route("/about")
def about():
    clearSession(session)
    session['errors'] = []
    return render_template("faq.html")

@main.route("/view", methods=['GET', 'POST'])
def view():
    errors = session.pop('errors', [])
    clearSession(session)
    form = ViewElectionForm(request.form)
    election = None
    if request.method == 'POST':
        election, errors = getElectionFromDb(escape(form.election_id.data))
    return render_template("view.html", form=form, errors=errors,
                           election=election)

@main.route("/create", methods=['GET', 'POST'])
def create():
    # store any errors before we clear the session variable
    errors = session.pop('errors', [])
    clearSession(session)
    session['errors'] = []
    form = ElectionForm(request.form)
    if ((not errors) and (request.method == 'POST')):
        # validate the date part of the form
        start_time, end_time, dateErrors = validateDates(form.data)        
        if not dateErrors:
            # validate the question part of the form
            election, questionErrors = validateQuestions(form.data, start_time,
                                                         end_time)            
            if not questionErrors:
                # validate the file upload part of the form
                filepath, delim, uploadErrors = validateUpload(
                    form.data, request.files, MAX_FILENAME_LENGTH,
                    main.config["UPLOAD_FOLDER"])
                if not uploadErrors:
                    # go to the confirm page after assigning values to session
                    sample, warnEmails, csvErrors = checkCsv(filepath, delim)
                    if not csvErrors:
                        session['new_election'] = jsonpickle.encode(election)
                        session['delim'] = delim
                        session['filename'] = filepath
                        session['warn'] = warnEmails
                        session['sample'] = sample
                        return redirect(url_for("confirmElection"))
                    errors += csvEerrors
                else:
                    errors += uploadErrors
            else:
                errors += questionErrors
        else:
            errors += dateErrors
    return render_template("create.html", form=form, errors=errors)
    

# TODO: make it so that after a POST, if the request fails, the form
# on the webpage maintains the choices, questions etc. ALSO display the errors
# lmao
@main.route("/confirm-election", methods=["GET", "POST"])
def confirmElection():
    warnEmails = session.pop('warn', None)
    session['errors'] = []
    
    # ensure the user has filled out the form properly
    if (not 'new_election' in session):
        session['errors'].append("Election incomplete, ensure that you \
correctly filled out the election details here.")
        return redirect(url_for("create"))
    if ((not 'delim' in session) or (not 'filename' in session)):
        session['errors'].append("Election incomplete, ensure that you \
have uploaded the voter CSV file after filling out the election details.")
        return redirect(url_for("create"))
    if not 'sample' in session:
        session['errors'].append("Empty voter file uploaded. Please ensure \
that you have uploaded a valid, non-empty voter CSV file before trying to \
confirm the election.")
        return redirect(url_for("create"))
    
    if (request.method == 'POST'):
        # if we get a POST with all the checks passed at this point, then insert
        # into the DB
        inserted = insertElection(jsonpickle.decode(session['new_election']),
                                  session.pop('filename'), session.pop('delim'))
        if inserted is None:
            print("Election was not inserted successfully")
        else:
            print("Election inserted successfully!")
            session.pop('new_election', None)
            session.pop('sample', None)
            return redirect(url_for("splash"))
    election = jsonpickle.decode(session['new_election'])
    return render_template("confirm_election.html", form=SubmitForm(),
                           election=election, questions=election.questions,
                           samples=session['sample'], warnings=warnEmails)


@main.route("/login", methods=["GET", "POST"])
def voteLogin():
    # use GET request to parse and check the election ID we're trying to login with
    clearSession(session)
    election_id = escape(request.args.get("election_id", ""))
    if not election_id:
        session['errors'] = ["No election ID given, please pass an election ID \
and try again."]
        return redirect(url_for("view"))

    status = getElectionStatus(election_id)
    
    if status is None:
        session['errors'] = [f"Invalid election ID passed: No election found \
with that ID."]
        return redirect(url_for("view"))
    
    if status.name == "PENDING":
        session['errors'] = [f"Election ID {election_id} has not started yet! Come back after\
{election.str_start_time}."]
        return redirect(url_for("view"))
    if status.name == "CLOSED":
        session['errors'] = [f"Election ID {election_id} has closed! Check out its results."]
        return redirect(url_for("view"))

    # check login details on login
    form = LoginForm(request.form)
    errors = []
    if form.validate_on_submit():
        voter_data = getVoterFromDb(escape(form.email.data), escape(form.code.data),
                                    election_id)
        if voter_data is not None:
            if voter_data['finished']:
                errors.append("You have already completed voting in this election. \
If you would like to see the results, please wait until the election completes \
and then navigate to the View Election page.")
            else:
                session['id'] = voter_data['session_id']
                return redirect(url_for("voting", election_id=election_id,
                                        question_num=voter_data['question']))
        else:
            errors.append("Your email address and/or election code are incorrect.")
    return render_template("login.html", form=form, election_id=election_id,
                           errors=errors)

@main.route("/<string:election_id>/vote/<int:question_num>", methods=["GET", "POST"])
def voting(election_id: str, question_num: int):
    clean_id = escape(election_id)
    clean_num = int(escape(question_num))
    # check session data
    if 'id' not in session:
        session['errors'] = ['Please login before trying to vote.']
        return redirect(url_for("voteLogin"))
    if not validSessionData(session['id'], clean_id, clean_num):
        session['errors'] = ['Invalid session data passed.']
        return redirect(url_for("view"))
    # make a Form from the Question object
    question = getElectionQuestion(election_id, clean_num)
    if question is None:
        session['errors'] = ['Something went wrong when trying to fetch that question']
        return redirect(url_for("voteLogin"))
    form = QuestionForm(question)
    errors = []
    return render_template("voting.html", form=form, errors=errors)


@main.route("/<string:election_id>/results", methods=["GET", "POST"])
def results(election_id: str):
    pass

from flask import Flask, render_template, redirect, session, url_for, request, g
from helpers import (parseTime, mergeTime, makeID, clearSession,
                     checkCsv, _makeFolder, getElection)

from forms import (ElectionForm, SubmitForm, ViewElectionForm,
                   validateDates, validateQuestions, validateUpload)
from db import initApp, insertElection, getElectionFromDb, getVoterFromDb

from datetime import datetime
import jsonpickle
import os

DB_NAME = "dreipy.sqlite"
UPLOAD_FOLDER = "uploads/"

# maximum size of the uploaded CSV file (MiB)
MAX_FILE_SIZE_LIMIT = 5
# maximum length of the uploaded CSV filename (number of characters)
MAX_FILENAME_LENGTH = 50

# TODO: we need to log ALL THE THINGS!

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
    )

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
    clearSession(session)
    session['errors'] = []
    election = None
    form = ViewElectionForm(request.form)
    if (request.method == 'POST' and form.validate()):
        # first search for the election in memory
        election_id = form.election_id.data
        election = getElection(election_id)
        # if not there, then look in database and add to memory
        if election is None:
            election, errors = getElectionFromDb(election_id)
            if not errors:
                g.elections[election_id] = jsonpickle.encode(election)
        if not election is None and not errors:
            # set the election ID of the election we found in the session
            # we will pass this to the GET request to view/vote in an election
            session["election_id"] = election_id
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
    # get election_id from the session, or failing that from the GET header
    election_id = session.pop('election_id', None)
    clearSession(session)
    if election_id is None and "election_id" in request:
        election_id = request.election_id
    else:
        session['errors'] = ["No election ID given, please specify a valid ID\
and try again."]
        return redirect(url_for("view"))
    # don't trust the election ID automatically, test that it's in memory
    # (it should be!)
    if election_id not in g.elections:
        session['errors'] = ["Invalid election ID passed: No election found\
with the given ID."]
        return redirect(url_for("view"))
    session['errors'] = []
    errors = []
    form = LoginForm(request.form)
    if (request.method == "POST" and form.validate()):
        voter_data = getVoterFromDb(form.email.data, form.code.data,
                                    election_id)
        if voter_data is not None:
            if voter_data['finished']:
                errors.append("You have already completed voting in this election.\
If you would like to see the results, please wait until the election completes\
and then navigate to the View Election page.")
            else:
                session['voter'] = voter_data['voter_id']
                session['id'] = voter_data['session_id']
                session['question'] = voter_data['question']
                return redirect(url_for("voting"))
        else:
            errors.append("Your email address and/or election code are incorrect.")
    return render_template("login.html", form=form, election_id=election_id,
                           errors=errors)

@main.route("/election/ELECTION_ID/vote/QUESTION_NUM", methods=["GET", "POST"])
def voting():
    # check session data is valid and present
    voter_id = session.pop('voter', None)
    session_id = session.pop('id', None)
    question_num = session.pop('question', None)
    
    form = None
    errors = []
    return render_template("voting.html", form=form, errors=errors)

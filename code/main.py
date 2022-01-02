from flask import Flask, render_template, redirect, session, url_for, request
from helpers import longTime, parseTime, mergeTime, makeID, clearSession, checkCsv
from datetime import datetime
from forms import ElectionForm, validateDates, validateQuestions, validateUpload
import jsonpickle
import os

main = Flask(__name__)

UPLOAD_FOLDER = "uploads/"
# maximum size of the uploaded CSV file (MiB)
MAX_FILE_SIZE_LIMIT = 5
# maximum length of the uploaded CSV filename (number of characters)
MAX_FILENAME_LENGTH = 50

# make sure we securely generate these -- maybe environment variable?
main.secret_key = b'_5#y2L"F4Q8z\n\xec]/'
main.config["SECRET_KEY"] = "TODO"

main.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
main.config["MAX_CONTENT_LENGTH"] = MAX_FILE_SIZE_LIMIT * 1024 * 1024


# TODO: we need to log ALL THE THINGS!

@main.errorhandler(404)
def not_found(error):
    print(error)
    return render_template("not_found.html", error=error)

@main.errorhandler(413)
def file_too_large(error):
    print(error)
    session["errors"] = [f"You tried to upload a file that was too large. Please\
 only upload files with size up to {MAX_FILE_SIZE_LIMIT}MiB."]
    return redirect(url_for("create"))

@main.route("/")
def splash():
    # clear any session variables that we should not keep for this page
    clearSession(session, ['new_election', 'start_time', 'end_time',
                           'delim', 'filename'])
    session['errors'] = []
    return render_template("splash.html")

@main.route("/about")
def about():
    clearSession(session, ['new_election', 'start_time', 'end_time',
                           'delim', 'filename'])
    session['errors'] = []
    return render_template("faq.html")

@main.route("/vote")
def vote():
    clearSession(session, ['new_election', 'start_time', 'end_time',
                           'delim', 'filename'])
    # copy the session errors into a local variable, then clear the session
    # errors so that they do not continue to future requests
    errors = session['errors']
    session['errors'] = []
    return render_template("vote.html", errors=errors)

@main.route("/create", methods=['GET', 'POST'])
def create():
    clearSession(session, ['new_election', 'start_time', 'end_time',
                           'delim', 'filename'])
    form = ElectionForm()
    errors = session['errors']
    session['errors'] = []
    if ((not errors) and (request.method == 'POST')):
        form = request.form
        # validate the date part of the form
        start_time, end_time, dateErrors = validateDates(form)        
        if not dateErrors:
            # validate the question part of the form
            election, questionErrors = validateQuestions(form, start_time,
                                                         end_time)            
            if not questionErrors:
                filepath, delim, uploadErrors = validateUpload(form, request.files,
                                                               MAX_FILENAME_LENGTH,
                                                               main.config["UPLOAD_FOLDER"])
                if not uploadErrors:
                    # go to the confirm page after assigning values to session
                    session['start_time'] = start_time
                    session['end_time'] = end_time
                    session['new_election'] = jsonpickle.encode(election)
                    session['delim'] = delim
                    session['filename'] = filepath
                    return redirect(url_for("parseFile"))
                else:
                    errors += uploadErrors
            else:
                errors += questionErrors
        else:
            errors += dateErrors
    return render_template("create.html", form=form, errors=errors)

@main.route("/parse-file", methods=["GET"])
def parseFile():
    # ensure the user has filled out the form properly
    if ((not 'start_time' in session) or (not 'end_time' in session)):
        session['errors'].append("Election incomplete, ensure that the \
start and end times have been defined before trying to parse the CSV file.")
        return redirect(url_for("create"))
    if (not 'new_election' in session):
        session['errors'].append("Election incomplete, ensure that its \
questions have been defined before trying to parse the CSV file.")
        return redirect(url_for("create"))
    if ((not 'delim' in session) or (not 'filename' in session)):
        session['errors'].append("Election incomplete, ensure that you \
have uploaded the voter CSV file before trying to parse the CSV file.")
        return redirect(url_for("create"))

    sample, errors = checkCsv(session['filename'], session['delimiter'])
    if not errors:
        session['sample'] = sample
        return redirect(url_for("confirmElection"))
    

# TODO: make it so that after a POST, if the request fails, the form
# on the webpage maintains the choices, questions etc. ALSO display the errors
# lmao
@main.route("/confirm-election", methods=["GET", "POST"])
def confirmElection():
    samples = session.pop('sample', None)
    session['errors'] = []
    
    # ensure the user has filled out the form properly
    if ((not 'start_time' in session) or (not 'end_time' in session)):
        session['errors'].append("Election incomplete, ensure that the \
start and end times have been defined before trying to confirm it.")
        return redirect(url_for("create"))
    if (not 'new_election' in session):
        session['errors'].append("Election incomplete, ensure that its \
questions have been defined before trying to confirm it.")
        return redirect(url_for("create"))
    if ((not 'delim' in session) or (not 'filename' in session)):
        session['errors'].append("Election incomplete, ensure that you \
have uploaded the voter CSV file before trying to confirm it.")
        return redirect(url_for("create"))
    if (not 'sample' in session):
        session['errors'].append("Voter file not parsed, ensure that you \
have uploaded a valid voter CSV file before trying to confirm the election.")
        return redirect(url_for("create"))
    election = jsonpickle.decode['new_election']
    sample = []
    return render_template("confirm_election.html", election=election,
                           questions=election.questions, samples=samples)

@main.route("/view", methods=["GET"])
def view():
    clearSession(session, ['new_election', 'start_time', 'end_time',
                           'delim', 'filename'])
    session['errors'] = []
    return render_template("view.html")

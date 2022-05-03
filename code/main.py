from flask import (Flask, render_template, redirect, session, url_for, Markup,
                   request, g, abort, flash, make_response, send_from_directory)
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, login_user, current_user, login_required

from wtforms.validators import ValidationError
from werkzeug.datastructures import CombinedMultiDict
from markupsafe import escape

from Voter import Voter
from helpers import (parseTime, mergeTime, makeID, clearSession, firstReceipt,
                     checkCsv, makeFolder, bytestrToVKey, sKeyToBytestr,
                     auditBallot, prettyReceipt, parseElection, truncHash,
                     confirmBallot, electionTotals, makeElectionJson,
                     stringToHex, makeElectionGraph)
from forms import (ElectionForm, SubmitForm, ViewElectionForm, LoginForm,
                   QuestionForm, AuditForm)
from db import (initApp, insertElection, getElectionFromDb, getVoterFromDb,
                isElectionInDb, getElectionStatus,
                getQuestionByNum, getNewBallotID, getPrivateKey,
                updateVoteReceipt, deleteBallot, getElectionContact,
                updateAuditBallot, incrementTallies, deleteSecrets,
                getVoterById, nextQuestion, completeVoting, getBallots,
                totalQuestions, getQuestionTallies)
from crypto import signData, hashString, verifyData

from typing import Optional
from datetime import datetime

from secrets import token_bytes, token_hex
from socket import gethostname, gethostbyname
import json
import jsonpickle
import os

# file/directory names and paths
DB_NAME = "dreipy.sqlite"
UPLOAD_FOLDER = "uploads/"
GRAPH_FOLDER = "static/graphs/"
DOWNLOAD_FOLDER = "json/"

# maximum size of the uploaded Voter CSV file (MiB)
MAX_FILE_SIZE_LIMIT = 5

# number of bytes to use when generating secrets
# https://docs.python.org/3/library/secrets.html#how-many-bytes-should-tokens-use
SECRET_BYTES = 32

# for launch
#my_host = f"http://{gethostbyname(gethostname())}"

# for development on localhost
my_host = f"http://127.0.0.1:5000"

## FLASK APP SETUP
main = Flask(__name__)

dbPath = os.path.join(main.instance_path, DB_NAME)
uploadPath = os.path.join(main.instance_path, UPLOAD_FOLDER)
downloadPath = os.path.join(main.instance_path, DOWNLOAD_FOLDER)
graphPath = os.path.join(os.path.dirname(__file__), GRAPH_FOLDER)

# randomly generate a new secret key
main.secret_key = token_bytes(SECRET_BYTES)
main.config.from_mapping(
    SECRET_KEY = token_hex(SECRET_BYTES),
    DATABASE = dbPath,
    UPLOAD_FOLDER = uploadPath,
    JSON_FOLDER = downloadPath,
    GRAPH_FOLDER = graphPath,
    MAX_CONTENT_LENGTH = MAX_FILE_SIZE_LIMIT * 1024 * 1024,
    SESSION_COOKIE_SECURE = False,   # we're not using HTTPS yet
    SESSION_COOKIE_HTTPONLY = True,  # cookies cannot be read with JS
    SESSION_COOKIE_SAMESITE = 'Strict'  # don't send cookies with any external requests
)

# force the use of CSRF tokens in forms
CSRFProtect(main)

# create all the relevant folders
makeFolder(main.instance_path, permissions=750)
makeFolder(uploadPath, permissions=750)
makeFolder(downloadPath, permissions=750)
makeFolder(graphPath, permissions=750)

# start the app and add the login manager
initApp(main)
login_manager = LoginManager()
login_manager.init_app(main)

@main.after_request
def after_request(response):
    """Run after all requests to add key security headers."""
    # forces Content-Type headers to be followed and not changed
    # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Content-Type-Options
    response.headers['X-Content-Type-Options'] = 'nosniff'

    # stop clickjacking attacks
    # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/X-Frame-Options
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'

    # CSP: only allow the user agent to load resources from 'self' apart
    # from scripts which can come from jQuery source AND our form.js file
    # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Content-Security-Policy
    response.headers['Content-Security-Policy'] = f"default-src 'self'; \
script-src https://ajax.googleapis.com/ajax/libs/jquery/3.5.1/jquery.min.js \
{my_host}{url_for('static', filename='form.js')}"
    
    return response

@login_manager.user_loader
def load_voter(voter_id: str) -> Optional[Voter]:
    """
    Callback used to reload the Voter object from their ID stored in the
    session by making call to database.
    """
    return getVoterById(voter_id)

@login_manager.unauthorized_handler
def unauthorised():
    """
    Callback for attempting to access endpoints that require authentication
    when the user is not authenticated (and hence unauthorised).
    """
    flash("Unauthorised! Please login before trying to vote in an election.", "error")
    return redirect(url_for('view'))

@main.errorhandler(404)
def not_found(error):
    """
    Callback for attempting to access endpoints that do not exist (HTTP 404).
    """
    return render_template("not_found.html")

@main.errorhandler(413)
def file_too_large(error):
    """
    Callback for attempting to upload a file that is larger than the defined
    file size limit.
    """
    sizeInMib = main.config['MAX_CONTENT_LENGTH'] // (1024**2)
    flash(f"You tried to upload a file that was too large. Please only upload files with size up to {sizeInMib}MiB.", "error")
    return redirect(url_for("create"))

@main.route("/")
def splash():
    """Landing page."""
    return render_template("splash.html")

@main.route("/view", methods=['GET', 'POST'])
def view():
    """
    Page where users can find elections to vote in or view bulletin boards for.
    """
    form = ViewElectionForm(request.form)
    election = None
    if form.validate_on_submit():
        election = getElectionFromDb(escape(form.election_id.data.upper()))
    return render_template("view.html", form=form, election=election)

@main.route("/create", methods=['GET', 'POST'])
def create():
    """Election creation page."""
    form = ElectionForm(CombinedMultiDict((request.files, request.form)))
    if form.validate_on_submit():
        request_list = request.form.to_dict()
        title = form.title.data
        contact = form.contact.data
        delim = form.delimiter.data
        
        # validate the dates part of the form and construct datetimes
        time_tup = ElectionForm.validateDates(form)
        
        # validate the questions and choices in the form and construct the
        # question dictionary
        questions = ElectionForm.validateQuestions(request_list)
        
        # validate the uploaded file and construct the new file location
        filepath = ElectionForm.validateFile(form)
        election_id = makeID()
        voters = checkCsv(election_id, filepath, delim)

        # check that all validation passed
        if time_tup is not None and questions is not None \
           and filepath is not None and voters is not None:
            # create election and redirect to confirmation
            start_time, end_time = time_tup
            election = parseElection(election_id, questions, start_time, end_time,
                                     title, contact)
            session['new_election'] = jsonpickle.encode(election)
            session['voters'] = jsonpickle.encode(voters)
            session['filepath'] = filepath
            return redirect(url_for("confirmElection"))
    return render_template("create.html", form=form, errors=form.errors)
    
@main.route("/confirm-election", methods=["GET", "POST"])
def confirmElection():
    """Election creation confirmation page."""
    if not 'new_election' in session:
        flash("Election incomplete, ensure that you correctly filled out the election details here.",
              "error")
        return redirect(url_for("create"))
    
    if not 'filepath' in session:
        flash("Election incomplete, ensure that you have uploaded the voter CSV file after filling out the election details.",
              "error")
        return redirect(url_for("create"))

    if not 'voters' in session:
        flash("Election incomplete, ensure that you uploaded a non-empty file for voters.",
              "error")
        return redirect(url_for("create"))

    election = jsonpickle.decode(session['new_election'])
    filepath = session['filepath']
    voters = jsonpickle.decode(session['voters'])

    form = SubmitForm(request.form)

    # if valid submission then insert into database
    if form.validate_on_submit():
        inserted = insertElection(election, voters)
        if inserted is None:
            flash("Election was not inserted successfully", "error")
        else:
            # delete user file after inserting voters
            os.remove(filepath)
            flash("Election inserted successfully!", "info")

            # clear session
            session.pop('new_election')
            session.pop('filepath')
            session.pop('voters')
            return redirect(url_for("splash"))    
    return render_template("confirm_election.html", form=SubmitForm(),
                           election=election, questions=election.questions)


@main.route("/login", methods=["GET", "POST"])
def voteLogin():
    """Page to log into an election for voting."""
    election_id = escape(request.args.get("election_id", ""))
    if not election_id:
        flash("No election ID given, please pass an election ID and try again.", 'error')
        return redirect(url_for("view"))

    # ensure users only login during an ONGOING election
    status = getElectionStatus(election_id)
    if status is None:
        flash(f"Invalid election ID passed: No election found with that ID.", 'error')
        return redirect(url_for("view"))
    
    if status.name == "PENDING":
        flash(f"Election has not started yet! Come back after {election.str_start_time}.", 'error')
        return redirect(url_for("view"))
    
    if status.name == "CLOSED":
        flash(f"Election has closed! Check out its results.", 'error')
        return redirect(url_for("results"), election_id=election_id)

    # if user is already logged in then send to voting
    if current_user.is_authenticated:
        return redirect(url_for("voting", election_id=election_id,
                                    question_num=current_user.current))

    form = LoginForm(request.form)
    if form.validate_on_submit():
        # validate login data
        voter = getVoterFromDb(escape(form.email.data), escape(form.code.data),
                                    election_id)
        if voter is not None:
            # log user into session and send to voting page
            login_user(voter)
            return redirect(url_for("voting", election_id=election_id,
                                    question_num=current_user.current))
        else:
            flash("Your email address and/or election code are incorrect.", 'error')
    contact = getElectionContact(election_id)
    return render_template("login.html", form=form, election_id=election_id,
                           contact=contact)

@main.route("/vote/<string:election_id>/<int:question_num>", methods=["GET", "POST"])
@login_required
def voting(election_id: str, question_num: int):
    """Page to vote for some question in an election."""
    clean_id = escape(election_id)
    clean_num = int(escape(question_num))

    # make sure that this user is for the correct election!
    if current_user.election_id != clean_id:
        flash("Wrong election. Please log into the correct election before trying to vote!", "error")
        return redirect(url_for("voting", election_id=clean_id,
                                    question_num=current_user.current))
    
    # for users that have finished voting, send them to the results page
    if current_user.voted:
        flash("You've already voted! Look at the election bulletin board below", "info")
        return redirect(url_for("results", election_id=clean_id))

    # make sure that the question number in the request matches the backend
    if current_user.current != clean_num:
        flash("Redirected to the correct question number.", "info")
        return redirect(url_for("voting", election_id=clean_id,
                                    question_num=current_user.current))

    # sanity check on the election status
    status = getElectionStatus(clean_id)
    if status is None:
        flash("Bad election ID passed, please try again!", "error")
        return redirect(url_for("view"))
    
    if status == "PENDING":
        flash("That election has not started yet!", 'error')
        return redirect(url_for("view"))

    if status == "CLOSED":
        flash("That election has closed! Check out its results below.", 'error')
        return redirect(url_for("results"), election_id=clean_id)
    
    # make a Form from the Question object (and request if POST)
    question = getQuestionByNum(clean_id, clean_num)
    if question is None:
        flash('Something went wrong when trying to fetch that question', 'error')
        return redirect(url_for("voteLogin", election_id=clean_id))
    form = QuestionForm(question, request.form)
    if form.validate_on_submit():
        if question.is_multi:
            choice = form.q_multi_choice.data
        else:
            choice = [form.q_single_choice.data]

        # do proofs and make the receipt
        receipt = firstReceipt(question, clean_id, current_user.voter_id, choice)
        if receipt is not None:
            # sign the SHA-256 hash of the receipt dumped as a JSON string,
            # and add to session with the public key so we can verify it on
            # the next page
            json_str = json.dumps(receipt)
            hex_json = stringToHex(json_str)
            session['hash_1'] = hashString(json_str)
            session['sign_1'] = signData(session['hash_1'], getPrivateKey())
            session['receipt'] = receipt  
            
            if updateVoteReceipt(session['sign_1'], session['hash_1'], receipt['ballot_id'],
                                 hex_json, first_stage=True) is None:
                flash("Could not sign your ballot, please try again.", 'error')
            else:
                return redirect(url_for("auditOrConfirm", election_id=clean_id,
                                        question_num=clean_num))
    contact = getElectionContact(clean_id)
    return render_template("voting.html", form=form, election_id=clean_id,
                           errors=form.errors, contact=contact)

@main.route("/audit/<string:election_id>/<int:question_num>", methods=["GET", "POST"])
@login_required
def auditOrConfirm(election_id: str, question_num: int):
    """
    Page where users are shown their stage one ballot and can choose to
    either audit or confirm it.
    """
    clean_id = escape(election_id)
    clean_num = int(escape(question_num))

    # election status and user checks
    if current_user.election_id != clean_id:
        flash("Wrong election. Please log into the correct election before trying to vote!", "error")
        return redirect(url_for("voting", election_id=clean_id,
                                    question_num=current_user.current))
    if current_user.voted:
        flash("You've already voted! Look at the election bulletin board below", "info")
        return redirect(url_for("results", election_id=clean_id))
    if current_user.current != clean_num:
        flash("Redirected to the correct question number.", "info")
        return redirect(url_for("voting", election_id=clean_id,
                                    question_num=current_user.current))
    
    status = getElectionStatus(clean_id)
    if status is None:
        flash("Bad election ID passed, please try again!", "error")
        return redirect(url_for("view"))
    if status == "PENDING":
        flash("That election has not started yet!", 'error')
        return redirect(url_for("view"))
    if status == "CLOSED":
        flash("That election has closed! Check out its results below.", 'error')
        return redirect(url_for("results"), election_id=clean_id)

    # check session contains the expected data
    if 'sign_1' not in session or 'hash_1' not in session \
        or 'receipt' not in session:
        flash('Bad session data, please try again.', 'error')
        clearSession(session)
        return redirect(url_for('voting', election_id=clean_id,
                                question_num=clean_num))

    # verify session data signature
    public_key = getPrivateKey().verifying_key
    if not verifyData(session['hash_1'], public_key, session['sign_1']):
        flash('Could not verify vote receipt, please try again.', 'error')
        clearSession(session)
        return redirect(url_for('voting', election_id=clean_id,
                                question_num=clean_num))
    
    form = AuditForm(request.form)
    if form.validate_on_submit():
        ballot_id = session['receipt']['ballot_id']
        # if AUDIT button is clicked, do auditing operations
        if form.audit.data and not form.confirm.data:
            receipt = auditBallot(ballot_id)
            if receipt is None:
                flash('Could not fetch ballot data, try again.', 'error')
            else:
                json_str = json.dumps(receipt)
                hex_json = stringToHex(json_str)
                session['hash_2'] = hashString(json_str)
                session['receipt_2'] = receipt
                session['sign_2'] = signData(session['hash_2'], getPrivateKey())
                if updateVoteReceipt(session['sign_2'], session['hash_2'], receipt['ballot_id'],
                                     hex_json, first_stage=False) \
                                     is None:
                    flash("Could not sign your ballot, please try again.", 'error')
                    return redirect(url_for('voting', election_id=clean_id,
                                            question_num=clean_num))

                # gets the choices in an easy to print way.
                choices = ""
                for choice_dict in receipt['choices']:
                    if choice_dict['voted']:
                        choices += f"{choice_dict['choice']}; "
                session['choices'] = choices[:-2]
                return redirect(url_for('showBallot', election_id=clean_id,
                                        question_num=clean_num))
        # if CONFIRM button is clicked, do confirmation operations   
        elif not form.audit.data and form.confirm.data:
            receipt = confirmBallot(ballot_id, len(session['receipt']['choices']))
            incrementTallies(ballot_id)
            deleteSecrets(ballot_id)
            
            # increment the question counter for the voter
            current_user.nextQuestion()
            nextQuestion(current_user.voter_id, current_user.current)
            
            json_str = json.dumps(receipt)
            hex_json = stringToHex(json_str)
            session['hash_2'] = hashString(json_str)
            session['sign_2'] = signData(session['hash_2'], getPrivateKey())
            session['receipt_2'] = receipt
            if updateVoteReceipt(session['sign_2'], session['hash_2'], receipt['ballot_id'],
                                 hex_json, first_stage=False) \
                                 is None:
                flash("Could not sign your ballot, please try again.", 'error')
                return redirect(url_for('voting', election_id=clean_id,
                                        question_num=clean_num))
            # check if all questions have now been completed
            if current_user.current > totalQuestions(clean_id):
                current_user.completeVoting()
                completeVoting(current_user.voter_id)
            session.pop('sign_1')
            return redirect(url_for('showBallot', election_id=clean_id,
                                    question_num=current_user.current))
        else:
            flash('Please either choose to audit or confirm your ballot.', 'error')
    pretty_hash = Markup(prettyReceipt(truncHash(session['hash_1'])))
    contact = getElectionContact(clean_id)
    return render_template("audit.html", form=form, election_id=clean_id,
                           pretty_hash=pretty_hash, contact=contact)

@main.route("/ballot/<string:election_id>/<int:question_num>", methods=["GET", "POST"])
@login_required
def showBallot(election_id: str, question_num: int):
    """Page where the user is shown their final stage two ballot."""
    clean_id = escape(election_id)
    clean_num = int(escape(question_num))

    # election status and user checks
    if current_user.election_id != clean_id:
        flash("Wrong election. Please log into the correct election before trying to vote!", "error")
        return redirect(url_for("voting", election_id=clean_id,
                                    question_num=current_user.current))
    if current_user.current != clean_num:
        flash("Redirected to the correct question number.", "info")
        return redirect(url_for("voting", election_id=clean_id,
                                    question_num=current_user.current))
    
    status = getElectionStatus(clean_id)
    if status is None:
        flash("Bad election ID passed, please try again!", "error")
        return redirect(url_for("view"))
    if status == "PENDING":
        flash("That election has not started yet!", 'error')
        return redirect(url_for("view"))

    # note we do not check for CLOSED elections since at this point their
    # ballot must have been completed before the election has closed and hence
    # the page should continue to load

    # check session data exists
    if 'hash_2' not in session or 'sign_2' not in session \
       or 'hash_1' not in session or 'receipt' not in session \
       or 'receipt_2' not in session:
        flash('Bad session data, please try again.', 'error')
        clearSession(session)
        return redirect(url_for('voting', election_id=clean_id,
                                question_num=clean_num))

    # verify session data
    public_key = getPrivateKey().verifying_key
    if not verifyData(session['hash_2'], public_key, session['sign_2']):
        flash('Could not verify vote receipt, please try again.', 'error')
        clearSession(session)
        return redirect(url_for('voting', election_id=clean_id,
                                question_num=clean_num))
    
    audited = session['receipt_2']['state'] == 'AUDITED'
    form = SubmitForm(request.form)
    if form.validate_on_submit():
        session.pop('receipt')
        session.pop('receipt_2')
        session.pop('hash_1')
        session.pop('sign_2')
        session.pop('hash_2')
        # only audited ballots have this, so provide the second argument
        session.pop('choices', None)
        return redirect(url_for('voting', election_id=clean_id,
                                question_num=clean_num))
    pretty_hash = Markup(prettyReceipt(truncHash(session['hash_1'])))
    contact = getElectionContact(clean_id)
    return render_template("ballot.html", election_id=clean_id, form=form,
                           audited=audited, pretty_hash=pretty_hash, contact=contact)

@main.route("/results/<string:election_id>", methods=["GET"])
def results(election_id: str):
    """Bulletin board page."""
    clean_id = escape(election_id)
    election = getElectionFromDb(clean_id)
    if election is None:
        flash("Could not find an election with that ID!", "error")
        return redirect(url_for("view"))

    if election.status.name == "PENDING":
        flash("The election has not started yet, come back after {election.str_start_time}", "error")
        return redirect(url_for("view"))

    # only get the results if the election has finished
    if election.status.name == "CLOSED":
        totals = electionTotals(election)
        graph_dict = makeElectionGraph(totals)
    else:
        totals = None
        graph_dict = None

    # fetch all the ballots to display
    receipts = getBallots(election)
    
    return render_template("bulletin.html", receipt_list=receipts, contact=election.contact,
                           trunc=truncHash, election=election, totals=totals,
                           graph_dict=graph_dict)

@main.route("/download_json/<string:election_id>", methods=["GET"])
def download(election_id: str):
    clean_id = escape(election_id)
    election = getElectionFromDb(clean_id)
    if election is None:
        flash("Could not find an election with that ID!", "error")
        return redirect(url_for("view"))

    if election.status.name != "CLOSED":
        flash("The election has not finished yet so you cannot download the JSON file yet.", "error")
        return redirect(url_for("view"))

    filename = f"{clean_id}.json"

    if makeElectionJson(election) is None:
        flash("Could not create JSON file for verification.", "error")
        return redirect(url_for("view"))
    
    return send_from_directory(main.config['JSON_FOLDER'], filename,
                               as_attachment=True)

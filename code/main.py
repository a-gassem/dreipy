from flask import (Flask, render_template, redirect, session, url_for,
                   request, g, abort, flash)
from flask_wtf.csrf import CSRFProtect
from flask_login import LoginManager, login_user, current_user, login_required

from wtforms.validators import ValidationError
from werkzeug.datastructures import CombinedMultiDict

from Voter import Voter
from helpers import (parseTime, mergeTime, makeID, clearSession, firstReceipt,
                     checkCsv, makeFolder, bytestrToVKey, sKeyToBytestr,
                     auditBallot, prettyReceipt, isSafeUrl, parseElection,
                     confirmBallot, electionTotals)
from forms import (ElectionForm, SubmitForm, ViewElectionForm, LoginForm,
                   QuestionForm, AuditForm)
from db import (initApp, insertElection, getElectionFromDb, getVoterFromDb,
                isElectionInDb, getElectionStatus, validVoterData,
                getQuestionByNum, getNewBallotID, getPrivateKey,
                updateVoteReceipt, deleteBallot,
                updateAuditBallot, incrementTallies, deleteSecrets,
                getVoterById, nextQuestion, completeVoting, getBallots,
                totalQuestions, getQuestionTallies)
from crypto import signData, hashString, verifyData

from typing import Optional
from datetime import datetime
from markupsafe import escape
from secrets import token_bytes, token_hex
import json
import jsonpickle
import os

DB_NAME = "dreipy.sqlite"
UPLOAD_FOLDER = "uploads/"

# maximum size of the uploaded CSV file (MiB)
MAX_FILE_SIZE_LIMIT = 5

# number of bytes to use when generating secrets
SECRET_BYTES = 32

## THINGS TO DO BEFORE DRAFT:
# TODO: graph of results for candidates;
# TODO: contact in case of bad verification
# TODO: multi-vote shit
# TODO: CSS so it's  p r e t t y

# TODO: unit tests?

## general QoL improvements
# TODO: logging

## FLASK APP SETUP
main = Flask(__name__)

dbPath = os.path.join(main.instance_path, DB_NAME)
uploadPath = os.path.join(main.instance_path, UPLOAD_FOLDER)

# randomly generate a new secret key 
main.secret_key = token_bytes(SECRET_BYTES)
main.config.from_mapping(
    SECRET_KEY = token_hex(SECRET_BYTES),
    DATABASE = dbPath,
    UPLOAD_FOLDER = uploadPath,
    MAX_CONTENT_LENGTH = MAX_FILE_SIZE_LIMIT * 1024 * 1024,
    SESSION_COOKIE_SECURE = False   # we're not using HTTPS
)

# force the use of CSRF tokens in forms
CSRFProtect(main)

# create all the relevant folders
makeFolder(main.instance_path, permissions=750)
makeFolder(uploadPath, permissions=750)

# start the app and add the login manager
initApp(main)
login_manager = LoginManager()
login_manager.init_app(main)

@login_manager.user_loader
def load_voter(voter_id: str) -> Optional[Voter]:
    return getVoterById(voter_id)

@login_manager.unauthorized_handler
def unauthorised():
    flash("Unauthorised! Please login before trying to vote in an election.")
    return redirect(url_for('view'))

@main.errorhandler(404)
def not_found(error):
    return render_template("not_found.html", error=error)

@main.errorhandler(413)
def file_too_large(error):
    print(error)
    sizeInMib = main.config['MAX_CONTENT_LENGTH'] // (1024**2)
    flash(f"You tried to upload a file that was too large. Please only upload files with size up to {sizeInMib}MiB.", "error")
    return redirect(url_for("create"))

@main.route("/")
def splash():
    return render_template("splash.html")

@main.route("/about")
def about():
    return render_template("faq.html")

@main.route("/view", methods=['GET', 'POST'])
def view():
    form = ViewElectionForm(request.form)
    election = None
    if request.method == 'POST':
        election = getElectionFromDb(escape(form.election_id.data))
    return render_template("view.html", form=form, election=election)

@main.route("/create", methods=['GET', 'POST'])
def create():
    form = ElectionForm(CombinedMultiDict((request.files, request.form)))
    if form.validate_on_submit():
        request_list = request.form.to_dict()
        title = form.title.data
        contact = form.contact.data
        delim = form.delimiter.data
        # validate the dates part of the form and construct datetimes
        time_tup = ElectionForm.validateDates(form)
        # validate the questions and choices in the form and construct
        # question dictionary FROM THE REQUEST MULTIDICT
        questions = ElectionForm.validateQuestions(request_list)
        # validate the uploaded file and construct the new file location
        filepath = ElectionForm.validateFile(form)
        election_id = makeID()
        voters = checkCsv(election_id, filepath, delim)
        if time_tup is not None \
           and questions is not None \
           and filepath is not None \
           and voters is not None:
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
    # ensure the user has filled out the form properly
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
    if request.method == 'POST':
        # if we get a POST with all the checks passed at this point, then insert
        # into the DB
        inserted = insertElection(election, voters)
        if inserted is None:
            flash("Election was not inserted successfully", "error")
        else:
            # delete user file after inserting voters
            os.remove(filepath)
            flash("Election inserted successfully!", "info")
            session.pop('new_election')
            session.pop('filepath')
            session.pop('voters')
            return redirect(url_for("splash"))
    
    return render_template("confirm_election.html", form=SubmitForm(),
                           election=election, questions=election.questions)


@main.route("/login", methods=["GET", "POST"])
def voteLogin():
    # use GET request to parse and check the election ID we're trying to login with
    election_id = escape(request.args.get("election_id", ""))
    if not election_id:
        flash("No election ID given, please pass an election ID and try again.", 'error')
        return redirect(url_for("view"))

    status = getElectionStatus(election_id)
    
    if status is None:
        flash(f"Invalid election ID passed: No election found with that ID.", 'error')
        return redirect(url_for("view"))
    
    if status.name == "PENDING":
        flash(f"Election ID {election_id} has not started yet! Come back after {election.str_start_time}.", 'error')
        return redirect(url_for("view"))
    
    if status.name == "CLOSED":
        flash(f"Election ID {election_id} has closed! Check out its results.", 'error')
        return redirect(url_for("view"))

    # if user is already logged in then send to next page
    if current_user.is_authenticated:
        return redirect(url_for("voting", election_id=election_id,
                                    question_num=current_user.current))

    # check login details on login
    form = LoginForm(request.form)
    if form.validate_on_submit():
        voter = getVoterFromDb(escape(form.email.data), escape(form.code.data),
                                    election_id)
        if voter is not None:
            # log user in after authentication
            login_user(voter)

            # protect against open redirects
            
            #next_endpoint = request.args.get('next')
            #if not isSafeUrl(next_endpoint):
            #    return abort(400)

            # if the user has finished voting, send to results page
            return redirect(url_for("voting", election_id=election_id,
                                    question_num=current_user.current))
        else:
            flash("Your email address and/or election code are incorrect.", 'error')
    return render_template("login.html", form=form, election_id=election_id)

@main.route("/<string:election_id>/vote/<int:question_num>", methods=["GET", "POST"])
@login_required
def voting(election_id: str, question_num: int):
    clean_id = escape(election_id)
    clean_num = int(escape(question_num))

    # for users that have finished voting, send them to the results page
    if current_user.voted:
        return redirect(url_for("results", election_id=clean_id))
    
    # make a Form from the Question object
    question = getQuestionByNum(clean_id, clean_num)
    if question is None:
        flash('Something went wrong when trying to fetch that question', 'error')
        return redirect(url_for("voteLogin", election_id=clean_id))
    form = QuestionForm(question, request.form)
    errors = []
    if form.validate_on_submit():
        if question.is_multi:
            choice = form.q_multi_choice.data
        else:
            choice = [form.q_single_choice.data]

        # do proofs, make receipts, sign data etc. etc.
        receipt = firstReceipt(question, clean_id, current_user.voter_id, choice)
        if receipt is None:
            flash('Something went wrong with your ballot, try again.', 'error')
        else:
            
            # note we truncate the the hash to 50 hex characters for ease of
            # validation. This does not seriously affect the security of the
            # program!
            session['hash'] = hashString(json.dumps(receipt)).upper()[:50]
            session['receipt'] = receipt
            private_key = getPrivateKey()
            session['sign'] = signData(session['hash'], private_key)    
            session['public_key'] = sKeyToBytestr(private_key.verifying_key)
            if updateVoteReceipt(session['sign'], session['hash'],
                                 receipt['ballot_id']) is None:
                deleteBallot(receipt['ballot_id'])
                flash("Could not sign your ballot, please try again.", 'error')
            else:
                return redirect(url_for("auditOrConfirm", election_id=clean_id,
                                        question_num=clean_num))
    return render_template("voting.html", form=form, election_id=clean_id,
                           errors=form.errors)

@main.route("/<string:election_id>/vote/<int:question_num>/audit", methods=["GET", "POST"])
@login_required
def auditOrConfirm(election_id: str, question_num: int):
    clean_id = escape(election_id)
    clean_num = int(escape(question_num))
    if 'public_key' not in session or 'sign' not in session \
       or 'hash' not in session or 'receipt' not in session:
        flash('Bad session data, please try again.', 'error')
        clearSession(session)
        return redirect(url_for('voting', election_id=clean_id,
                                question_num=clean_num))
    
    public_key = bytestrToVKey(session['public_key'])
    if not verifyData(session['hash'], public_key, session['sign']):
        flash('Could not verify vote receipt, please try again.', 'error')
        clearSession(session)
        return redirect(url_for('voting', election_id=clean_id,
                                question_num=clean_num))
    
    form = AuditForm(request.form)
    if form.validate_on_submit():
        private = getPrivateKey()
        if form.audit.data and not form.confirm.data:
            # audit the ballot and go back to question
            receipt = auditBallot(session['receipt'])
            if receipt is None:
                flash('Could not fetch ballot data, try again.', 'error')
            else:
                # sign AUDITED ballot
                session['hash'] = hashString(json.dumps(receipt)).upper()[:50]
                session['receipt'] = receipt
                session['sign'] = signData(session['hash'], getPrivateKey())
                return redirect(url_for('showBallot', election_id=clean_id,
                                        question_num=clean_num))
            
        elif not form.audit.data and form.confirm.data:
            # confirm selection and go to next question
            receipt = confirmBallot(session['receipt'])
            incrementTallies(receipt['ballot_id'])
            deleteSecrets(receipt['ballot_id'])
            # increment the question counter for the voter
            current_user.nextQuestion()
            nextQuestion(current_user.voter_id, current_user.current)
            # sign CONFIRMED ballot
            session['hash'] = hashString(json.dumps(receipt)).upper()[:50]
            session['sign'] = signData(session['hash'], getPrivateKey())
            session['receipt'] = receipt
            # check if all questions have now been completed
            if current_user.current > totalQuestions(clean_id):
                completeVoting(current_user.voter_id)
            return redirect(url_for('showBallot', election_id=clean_id,
                                    question_num=current_user.current))
        else:
            flash('Please either choose to audit or confirm your ballot.', 'error')
    return render_template("audit.html", form=form, clean_id=clean_id,
                           num_choices=len(session['receipt']['choices']))

@main.route("/<string:election_id>/vote/<int:question_num>/ballot", methods=["GET", "POST"])
@login_required
def showBallot(election_id: str, question_num: int):
    clean_id = escape(election_id)
    clean_num = int(escape(question_num))
    if 'public_key' not in session or 'sign' not in session \
       or 'hash' not in session or 'receipt' not in session:
        flash('Bad session data, please try again.', 'error')
        clearSession(session)
        return redirect(url_for('voting', election_id=clean_id,
                                question_num=clean_num))
    
    public_key = bytestrToVKey(session['public_key'])
    if not verifyData(session['hash'], public_key, session['sign']):
        flash('Could not verify vote receipt, please try again.', 'error')
        clearSession(session)
        return redirect(url_for('voting', election_id=clean_id,
                                question_num=clean_num))
    audited = session['receipt']['state'] == 'AUDITED'
    form = SubmitForm(request.form)
    if form.validate_on_submit():
        session.pop('receipt')
        session.pop('sign')
        session.pop('hash')
        session.pop('public_key')
        return redirect(url_for('voting', election_id=clean_id,
                                question_num=clean_num))
    return render_template("ballot.html", election_id=clean_id,
                           form=form, audited=audited,
                           num_choices=len(session['receipt']['choices']))

@main.route("/<string:election_id>/results", methods=["GET"])
def results(election_id: str):
    clean_id = escape(election_id)
    election = getElectionFromDb(clean_id)
    if election is None:
        flash("Could not find an election with that ID!", "error")
        return redirect(url_for("view"))
    receipts = getBallots(election)
    totals = electionTotals(election)
    return render_template("bulletin.html", receipt_list=receipts,
                           election=election, totals=totals)

DROP TABLE IF EXISTS voters;
DROP TABLE IF EXISTS elections;
DROP TABLE IF EXISTS questions;
DROP TABLE IF EXISTS ballots;
DROP TABLE IF EXISTS bulletins;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS choices;
DROP TABLE IF EXISTS question_choices;
DROP TABLE IF EXISTS election_questions;

CREATE TABLE voters (
  voter_id VARCHAR PRIMARY KEY,
  pass_hash VARCHAR NOT NULL, 
  election_id VARCHAR NOT NULL,
  full_name VARCHAR NOT NULL,
  dob DATE NOT NULL,
  address VARCHAR NOT NULL,
  postcode VARCHAR NOT NULL,
  finished_voting boolean NOT NULL
);

CREATE TABLE elections (
  election_id VARCHAR PRIMARY KEY,
  start_time datetime NOT NULL,
  end_time datetime NOT NULL
);

CREATE TABLE questions (
  question_id VARCHAR PRIMARY KEY,
  question_string VARCHAR NOT NULL,
  question_num INT NOT NULL,
  max_answers INT NOT NULL
);

CREATE TABLE ballots (
  ballot_id INT PRIMARY KEY,
  question_id VARCHAR NOT NULL,
  was_audited BOOLEAN NOT NULL,
  vote_receipt INT NOT NULL,
  random_receipt INT NOT NULL,
  proof_wf INT NOT NULL,
  vote_secret INT,
  random_secret INT
);

CREATE TABLE bulletins (
  question_id VARCHAR PRIMARY KEY,
  election_id VARCHAR NOT NULL,
  tally_total BIGINT NOT NULL,
  sum_total BIGINT NOT NULL,
  generator_1 BIGINT NOT NULL,
  generator_2 BIGINT NOT NULL
);

CREATE TABLE sessions (
  session_id VARCHAR PRIMARY KEY,
  voter_id VARCHAR NOT NULL,
  current_question INT 
);

CREATE TABLE choices (
  choice_id VARCHAR PRIMARY KEY,
  text VARCHAR NOT NULL,
  index_num INT NOT NULL
);

CREATE TABLE question_choices (
  choice_id VARCHAR NOT NULL
  question_id VARCHAR NOT NULL
  PRIMARY KEY (choice_id, question_id)
);

CREATE TABLE election_questions (
  election_id VARCHAR NOT NULL,
  question_id VARCHAR NOT NULL
  PRIMARY KEY (election_id, question_id)
);

Ref: elections.election_id - voters.election_id
Ref: elections.election_id < election_questions.election_id
Ref: questions.question_id < election_questions.question_id
Ref: elections.election_id < bulletins.election_id
Ref: questions.question_id < question_choices.question_id
Ref: choices.choice_id < question_choices.choice_id
Ref: questions.question_id - bulletins.question_id
Ref: questions.question_id < ballots.question_id
Ref: sessions.voter_id - voters.voter_id
Ref: sessions.current_question - questions.question_id
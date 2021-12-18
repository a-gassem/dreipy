DROP TABLE IF EXISTS voters;
DROP TABLE IF EXISTS elections;
DROP TABLE IF EXISTS questions;
DROP TABLE IF EXISTS ballots;
DROP TABLE IF EXISTS sessions;
DROP TABLE IF EXISTS choices;
DROP TABLE IF EXISTS question_choices;
DROP TABLE IF EXISTS election_questions;

CREATE TABLE voters (
  voter_id VARCHAR PRIMARY KEY,
  election_id VARCHAR NOT NULL,
  pass_hash VARCHAR NOT NULL, 
  full_name VARCHAR NOT NULL,
  dob DATE NOT NULL,
  address VARCHAR NOT NULL,
  postcode VARCHAR NOT NULL,
  finished_voting BOOLEAN NOT NULL,
  FOREIGN KEY (election_id) REFERENCES elections(election_id) ON DELETE CASCADE
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
  max_answers INT NOT NULL CONSTRAINT pos_answers CHECK (max_answers > 0),
  tally_total BIGINT NOT NULL CONSTRAINT pos_tally CHECK (tally_total >= 0),
  sum_total BIGINT NOT NULL CONSTRAINT pos_sum CHECK (sum_total >= 0),
  generator_1 BIGINT NOT NULL,
  generator_2 BIGINT NOT NULL,
);

CREATE TABLE ballots (
  ballot_id INT PRIMARY KEY,
  question_id VARCHAR NOT NULL,
  was_audited BOOLEAN NOT NULL,
  vote_receipt INT NOT NULL,
  random_receipt INT NOT NULL,
  proof_wf INT NOT NULL,
  vote_secret INT,
  random_secret INT,
  FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE
);

CREATE TABLE sessions (
  session_id VARCHAR PRIMARY KEY,
  voter_id VARCHAR NOT NULL,
  current_question INT,
  FOREIGN KEY (voter_id) REFERENCES voters(voter_id) ON DELETE CASCADE
);

CREATE TABLE choices (
  choice_id VARCHAR PRIMARY KEY,
  text VARCHAR NOT NULL,
  index_num INT NOT NULL
);

CREATE TABLE question_choices (
  choice_id VARCHAR NOT NULL,
  question_id VARCHAR NOT NULL,
  PRIMARY KEY (choice_id, question_id),
  FOREIGN KEY (choice_id) REFERENCES choices(choice_id) ON DELETE CASCADE,
  FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE
);

CREATE TABLE election_questions (
  election_id VARCHAR NOT NULL,
  question_id VARCHAR NOT NULL,
  PRIMARY KEY (election_id, question_id),
  FOREIGN KEY (election_id) REFERENCES elections(election_id) ON DELETE CASCADE,
  FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE
);

CREATE TRIGGER AFTER DELETE ON elections
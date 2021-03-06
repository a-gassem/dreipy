DROP TABLE IF EXISTS voters;
DROP TABLE IF EXISTS elections;
DROP TABLE IF EXISTS questions;
DROP TABLE IF EXISTS ballots;
DROP TABLE IF EXISTS receipts;
DROP TABLE IF EXISTS choices;
DROP TABLE IF EXISTS keys;

CREATE TABLE keys (
  private_k VARCHAR NOT NULL,
  public_k VARCHAR NOT NULL
);

CREATE TABLE voters (
  voter_id VARCHAR PRIMARY KEY,
  election_id VARCHAR NOT NULL,
  pass_hash VARCHAR NOT NULL, 
  full_name VARCHAR(71) NOT NULL,
  dob DATE NOT NULL,
  postcode VARCHAR(8) NOT NULL,
  uname VARCHAR NOT NULL,
  finished_voting BOOLEAN NOT NULL,
  current_question INT,
  FOREIGN KEY (election_id) REFERENCES elections(election_id) ON DELETE CASCADE
);

CREATE TABLE elections (
  election_id VARCHAR PRIMARY KEY,
  title VARCHAR NOT NULL,
  start_time DATETIME NOT NULL,
  end_time DATETIME NOT NULL,
  contact VARCHAR NOT NULL
);

CREATE TABLE questions (
  question_id VARCHAR PRIMARY KEY,
  election_id VARCHAR NOT NULL,
  question_num INT NOT NULL,
  text VARCHAR NOT NULL,
  num_answers INT NOT NULL CONSTRAINT pos_answers CHECK (num_answers > 0),
  gen_2 VARCHAR NOT NULL
);

CREATE TABLE ballots (
  ballot_id BIGINT NOT NULL,
  election_id VARCHAR NOT NULL,
  question_id VARCHAR NOT NULL,
  was_audited BOOLEAN,
  num_r VARCHAR,
  num_c VARCHAR,
  hash_1 VARCHAR,
  sign_1 VARCHAR,
  hash_2 VARCHAR,
  sign_2 VARCHAR,
  json_1 VARCHAR,
  json_2 VARCHAR,
  FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE,
  FOREIGN KEY (election_id) REFERENCES elections(election_id) ON DELETE CASCADE
);

CREATE TABLE receipts (
  receipt_id INTEGER PRIMARY KEY,
  ballot_id BIGINT NOT NULL,
  choice_index INT NOT NULL,
  random_secret VARCHAR,
  voted BOOLEAN,
  random_receipt VARCHAR NOT NULL,
  vote_receipt VARCHAR NOT NULL,
  r_1 VARCHAR NOT NULL,
  r_2 VARCHAR NOT NULL,
  c_1 VARCHAR NOT NULL,
  c_2 VARCHAR NOT NULL,
  FOREIGN KEY (ballot_id) REFERENCES ballots(ballot_id) ON DELETE CASCADE
);

CREATE TABLE choices (
  question_id VARCHAR NOT NULL,
  index_num INT NOT NULL,
  text VARCHAR NOT NULL,
  tally_total BIGINT CONSTRAINT pos_tally CHECK (tally_total >= 0),
  sum_total VARCHAR,
  PRIMARY KEY (question_id, index_num),
  FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE
);
DROP TABLE IF EXISTS voters;
DROP TABLE IF EXISTS elections;
DROP TABLE IF EXISTS questions;
DROP TABLE IF EXISTS ballots;
DROP TABLE IF EXISTS choices;
DROP TABLE IF EXISTS election_questions;

CREATE TABLE voters (
  voter_id VARCHAR PRIMARY KEY,
  session_id VARCHAR NOT NULL,
  election_id VARCHAR NOT NULL,
  pass_hash VARCHAR NOT NULL, 
  full_name VARCHAR(71) NOT NULL,
  dob DATE NOT NULL,
  postcode VARCHAR(8) NOT NULL,
  email VARCHAR NOT NULL,
  finished_voting BOOLEAN NOT NULL,
  current_question INT,
  FOREIGN KEY (election_id) REFERENCES elections(election_id) ON DELETE CASCADE
);

CREATE TABLE elections (
  election_id VARCHAR PRIMARY KEY,
  title VARCHAR NOT NULL,
  start_time DATETIME NOT NULL,
  end_time DATETIME NOT NULL
);

CREATE TABLE questions (
  question_id VARCHAR PRIMARY KEY,
  question_num INT NOT NULL,
  text VARCHAR NOT NULL,
  num_answers INT NOT NULL CONSTRAINT pos_answers CHECK (num_answers > 0),
  tally_total BIGINT CONSTRAINT pos_tally CHECK (tally_total >= 0),
  sum_total BIGINT CONSTRAINT pos_sum CHECK (sum_total >= 0),
  generator_1 BIGINT CONSTRAINT pos_gen1 CHECK (generator_1 > 0),
  generator_2 BIGINT CONSTRAINT pos_gen2 CHECK (generator_2 > 0)
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

CREATE TABLE choices (
  question_id VARCHAR NOT NULL,
  index_num INT NOT NULL,
  text VARCHAR NOT NULL,
  PRIMARY KEY (question_id, index_num),
  FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE
);

CREATE TABLE election_questions (
  election_id VARCHAR NOT NULL,
  question_id VARCHAR NOT NULL,
  PRIMARY KEY (election_id, question_id),
  FOREIGN KEY (election_id) REFERENCES elections(election_id) ON DELETE CASCADE,
  FOREIGN KEY (question_id) REFERENCES questions(question_id) ON DELETE CASCADE
);
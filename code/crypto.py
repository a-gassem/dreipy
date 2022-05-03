import gmpy2
from gmpy2 import mpz, powmod, divexact
from ecdsa import NIST256p, SigningKey, VerifyingKey
from ecdsa.ellipticcurve import Point, INFINITY
from cryptography.hazmat.primitives import hashes

import json
from secrets import randbelow
from base64 import b64encode
from typing import Tuple, List, Optional

# first generator, g, instantiated with domain parameters of NIST
# ecdsa.ellipticcurve.PointJacobi
g1 = NIST256p.generator

# ecdsa.ellipticcurve.CurveFp
curve = NIST256p.curve

# curve.a() was returning -3 which is incorrect???
a = mpz(int("ffffffff00000001000000000000000000000000fffffffffffffffffffffffc",
            16))
b = mpz(curve.b())
q = mpz(curve.p())
cofactor = mpz(curve.cofactor())
n = mpz(g1.order())

def hashString(string: str) -> str:
    """Returns hex representation of input string hashes with SHA-512"""
    digest = hashes.Hash(hashes.SHA512())
    digest.update(bytes(string, 'utf-8'))
    return digest.finalize().hex()

def signData(string: str, private: SigningKey) -> str:
    """
    Signs the passed string with the stored private key, return as hex string.
    """
    return private.sign(bytes(string, 'utf-8')).hex()

def verifyData(data: str, key: VerifyingKey, signature: str) -> bool:
    """
    Verifies that some given data was signed with the SigningKey paired with
    the passed VerifyingKey based on a signature in hex form.
    """
    return key.verify(bytes.fromhex(signature), bytes(data, 'utf-8'))

def generateKeyPair() -> Tuple[mpz, mpz]:
    """Generates a public/private key pair for the current curve."""
    private = SigningKey.generate(curve=NIST256p)
    public = private.verifying_key
    return private, public

def hashElectionString(election_string: str, count: int = None) -> mpz:
    """
    Returns a large integer derived from a SHA-256 hash of the election id,
    the current iteration of the parent loop, and the generator for the curve
    being used.
    """
    digest = hashes.Hash(hashes.SHA256())
    digest.update(bytes.fromhex(hex(a)[2:]))
    digest.update(bytes.fromhex(hex(b)[2:]))
    digest.update(bytes(str(cofactor), 'utf-8'))
    digest.update(bytes.fromhex(hex(q)[2:]))
    digest.update(bytes.fromhex(hex(n)[2:]))
    
    # use generator, election ID and current iteration for digest
    digest.update(g1._compressed_encode())
    digest.update(bytes(election_string, 'utf-8'))
    if count is not None:
        digest.update(bytes(str(count), 'utf-8'))
    return mpz(int.from_bytes(digest.finalize(), byteorder="big"))

def eulerCriterion(num: mpz) -> bool:
    """Euler's criterion. q is an odd prime > 2. https://en.wikipedia.org/wiki/Euler%27s_criterion"""
    return powmod(num, divexact(q-1, 2), q)

def generatePair(election_string: str) -> Tuple[Point, Point]:
    """Returns a pair of EC points using the NIST256p field (length 256b)."""
    
    # manually create second generator according to Prof. Hao's algorithm
    count = 0
    while True:
        x = hashElectionString(election_string, count)
        # Compute z = x^3 + ax + b
        z = (powmod(x, 3, q) + (a*x + b)) % q

        # Check if z has a square root, i.e., the Lengendre symbol = 1
        if eulerCriterion(z) == 1:

            # We can use Shanks' algorithm to compute a square root of z mod q
            # But since q = 3 mod 4, we can do it in a simpler way:
            # sqr(z) = z^((q+1)/4) mod q
            y = powmod(z, divexact(q+1, 4), q)

            # check the point is actually on the curve (i.e. in the group
            # we defined)
            g2 = Point(curve, x, y)
            
            if (g2 != INFINITY) and ((g2 * cofactor) != INFINITY):
                return g1, g2
        count += 1

def generateRandSecret() -> mpz:
    """Returns an mpz object in the range [1, n-1]"""
    r = 0
    while r == 0:
        r = randbelow(n)
    return mpz(r)

def generateR(g2: Point, r: mpz) -> Point:
    """Returns a Point p = g2^rand"""
    return g2 * r

def generateZ(r: mpz, v: int) -> Point:
    """Returns a Point p = g1^r * g1^v"""
    return g1 * (r + v)

def generateZKProof(question_id: str, g2: Point, R: Point, Z: Point, r: mpz) \
    -> Tuple[str, str, str, str]:
    """
    Zero-knowledge proof of knowledge and equality of the following discrete
    logarithms:
    P_K{r: ((R = g2^r) AND ((Z div g1) = g1^r)) OR ((R = g2^r) AND (Z = g1^r))}

    We are proving that either we didn't vote for this (v = 0) or we did (v = 1)

    We generate an R and Z for each of the m choices. We need to do a proof of
    well-formedness for each of these R and Z results so this is run for each
    R, Z, r tuple.
    """     
    w = generateRandSecret()
    r_2 = generateRandSecret()
    c_2 = generateRandSecret()

    # Calculate the two halves of the disjunctive proof (G_1, G_2) and (G_3, G_4)
    G_1 = Z + (-g1)
    G_2 = R
    G_3 = Z
    G_4 = R

    # note that we repeat the same generators
    g3 = g1
    g4 = g2
    
    t_1 = g1 * w
    t_2 = g2 * w
    t_3 = (g1 * r_2) + (G_3 * c_2)
    t_4 = (g2 * r_2) + (G_4 * c_2)

    # calculate proof hash
    c = proofZKHash(question_id, g1, G_1, g2, G_2, g3, G_3, g4, G_4, t_1, t_2,
                    t_3, t_4)

    # calculate remaining secrets and return hashes as hex
    c_1 = abs(c - c_2)
    return (hex(c_1)[2:], hex(c_2)[2:], hex(abs(w - (c_1 * r)))[2:],
            hex(r_2)[2:])

def verifyZKProof(question_id: str, g1: Point, g2: Point, R: Point, Z: Point, 
                  proof_c1: mpz, proof_c2: mpz, proof_r1: mpz, proof_r2: mpz) \
                  -> bool:
    """
    Verifier for the zero-knowledge proof of wellformedness of a choice in a
    ballot produced by generateZKProof().
    """
    G_1 = Z + (-g1)
    G_2 = R
    G_3 = Z
    G_4 = R

    g3 = g1
    g4 = g2

    t_1 = (g1 * proof_r1) + (G_1 * proof_c1)
    t_2 = (g2 * proof_r1) + (G_2 * proof_c1)
    t_3 = (g1 * proof_r2) + (G_1 * proof_c2)
    t_4 = (g2 * proof_r2) + (G_2 * proof_c2)

    c_prime = proofZKHash(question_id, g1, G_1, g2, G_2, g3, G_3, g4, G_4, t_1,
                          t_2, t_3, t_4)

    return (proof_c1 + proof_c2) == c_prime

## can probs to some kwargs** shenanigans here...
def proofNumHash(proof_id: str, g1: Point, G_1: Point, g2: Point, G_2: Point,
                 t_1: Point, t_2: Point) -> mpz:
    """Returns a hash calculated by a tuple of arguments and passed through."""
    from helpers import pointToBytestr
    tup = (proof_id, pointToBytestr(g1), pointToBytestr(G_1), pointToBytestr(g2),
           pointToBytestr(G_2), pointToBytestr(t_1), pointToBytestr(t_2))
    return mpz(int.from_bytes(bytes.fromhex(hashString(str(tup))),
                              byteorder="big")
               )

def proofZKHash(proof_id: str, g1: Point, G_1: Point, g2: Point, G_2: Point,
                g3: Point, G_3: Point, g4: Point, G_4: Point, t_1: Point,
                t_2: Point, t_3: Point, t_4: Point) -> mpz:
    """Returns a hash calculated by a tuple of arguments and passed through."""
    from helpers import pointToBytestr
    tup = (proof_id, pointToBytestr(g1), pointToBytestr(G_1), pointToBytestr(g2),
           pointToBytestr(G_2), pointToBytestr(g3), pointToBytestr(G_3),
           pointToBytestr(g4), pointToBytestr(G_4), pointToBytestr(t_1),
           pointToBytestr(t_2), pointToBytestr(t_3), pointToBytestr(t_4))
    return mpz(int.from_bytes(bytes.fromhex(hashString(str(tup))),
                              byteorder="big")
               )

def pointSum(point_list: List[Point]) -> Point:
    """
    Given a list of Points, successively adds them together and returns the
    result. If the list is empty then returns the point at infinity."""
    curr_point = INFINITY
    for point in point_list:
        curr_point = curr_point + point

    return curr_point

def generateNumProof(question_id: str, g2: Point,  R_list: List[Point],
                     Z_list: List[Point], r_list: List[mpz], num_choices: int) \
                     -> Tuple[str, str]:
    """
    Zero-knowledge proof of knowledge and equality of form:
    P_K{r_sum: ((PROD{Z} div g1^k = g1^r_sum) AND (PROD{R} = g2^r_sum))}

    where exactly k votes in the ballot are 1.
    """
    # choose random w in group Z order q
    w = generateRandSecret()

    # calculate exponentiations with our random value
    t_1 = g1 * w
    t_2 = g2 * w

    # Calculate products (note that in elliptic curve settings multiplication
    # is done successively adding points on the curve)
    
    G_1 = pointSum(Z_list) + (-g1 * num_choices)
    G_2 = pointSum(R_list)

    # calculate proof hash
    c = proofNumHash(question_id, g1, G_1, g2, G_2, t_1, t_2)

    # if difference < 0 then must make positive to account for the '-' sign
    return (hex(c)[2:], hex(abs(w - (c * sum(r_list))))[2:])

def verifyNumProof(question_id: str, g1: Point, g2: Point, R_list: List[Point],
                   Z_list: List[Point], proof_c: mpz, proof_r: mpz,
                   num_choices: int) -> bool:
    """
    Verifier for the zero-knowledge proof of wellformedness of the number of
    votes in a ballot produced by generateNumProof().
    """

    # calculate known products
    G_1 = pointSum(Z_list) + (-g1 * num_choices)
    G_2 = pointSum(R_list)

    # calculate exponentiations with proofs and bases
    t_1 = (g1 * proof_r) + (G_1 * proof_c)
    t_2 = (g2 * proof_r) + (G_2 * proof_c)

    # compare hashes
    return proof_c == proofNumHash(question_id, g1, G_1, g2, G_2, t1, t2)

def verifyElectionJson(filepath: str, election_id: str) -> bool:
    """
    Given a filepath to a JSON file containing the data for a DRE-ipy election,
    returns True if all checks are passed, returns False otherwise.
    """
    from helpers import bytestrToVKey, bytestrToPoint

    with open(filepath) as f:
        json_data = json.load(f)

    valid = True
    has_key = True
    good_points = True

    questions = json_data['election_data']['questions']

    try:
        public_key = bytestrToVKey(json_data['public_key'])
    except:
        print("ERROR: Public key could not be reformed from bytestring!")
        print("Skipping all hash checks due to bad key...")
        valid = False
        has_key = False
    
    # first verify hash of ALL election data (have any entries been
    # tampered with? has the sender changed?)
    total_hash = hashString(json.dumps(json_data['election_data']))
    if total_hash != json_data['hash']:
        print("ERROR: Total hash does not match! Election data has been tampered with...")
        valid = False

    if has_key and not verifyData(json_data['hash'], public_key,
                                  json_data['sign']):
        print("ERROR: Total hash was not signed by that public key's private key! Sender is not authentic...")
        valid = False

    # sanity check that the right election is being verified
    if election_id != json_data['election_data']['election_id']:
        print(f"ERROR: Election ID in JSON file is {json_data['election_data']['election_id']} when {election_id} was expected.")
        valid = False

    # total_receipts[question_id][i]['R'] = partial product of R for choice i in
    #                                       question with ID = question_id
    tally_dict = {question_id:[{'R':INFINITY, 'Z':INFINITY}] \
                  for question_id in questions.keys()}

    # then iterate over each ballot
    for ballot in json_data['election_data']['ballots']:

        has_gens = True

        question_id = ballot['stage_1']['question_id']
        
        # make sure the ballot was either AUDITED or CONFIRMED
        if ballot['state'] == "AUDITED":
            audited = True
        elif ballot['state'] == "CONFIRMED":
            audited = False
        else:
            audited = None
            print(f"ERROR: Invalid state for ballot ID {ballot['ballot_id']}")
            valid = False

        # verify stage 1 hash
        first_hash = hashString(ballot['stage_1']['data'])
        stage_1 = json.dumps(ballot['stage_1']['data'])
        
        if first_hash != ballot['stage_1']['hash']:
            print(f"ERROR: Non-matching first-stage ballot hash. Ballot ID {ballot['ballot_id']} has been tampered with.")
            valid = False
        
        if has_key and not verifyData(ballot['stage_1']['hash'], public_key,
                                      ballot['stage_1']['sign']):
            print(f"ERROR: Ballot ID {ballot['ballot_id']} has a (first) hash that was not not signed by the attached public key!")
            valid = False

        # verify stage 2 hash
        second_hash = hashString(ballot['stage_2']['data'])
        stage_2 = json.dumps(ballot['stage_2']['data'])
        
        if second_hash != ballot['stage_2']['hash']:
            print(f"ERROR: Non-matching second-stage ballot hash. Ballot ID {ballot['ballot_id']} has been tampered with.")
            valid = False

        if has_key and not verifyData(ballot['stage_2']['hash'], public_key,
                                      ballot['stage_2']['sign']):
            print(f"ERROR: Ballot ID {ballot['ballot_id']} has a (second) hash that was not not signed by the attached public key!")
            valid = False

        R_list = []
        Z_list = []

        # verify the proofs for each choice
        for choice, receipt in ballot['choices']:
            try:
                c_1 = hexToMpz(stage_1['c_1'])
                c_2 = hexToMpz(stage_1['c_2'])
                r_1 = hexToMpz(stage_1['r_1'])
                r_2 = hexToMpz(stage_1['r_2'])
                num_c = hexToMpz(stage_1['num_proof_c'])
                num_r = hexToMpz(stage_1['num_proof_r'])

                R = bytestrToPoint(stage_1['R'])
                Z = bytestrToPoint(stage_1['Z'])

                if audited:
                    r = hexToMpz(stage_2['r'])
                    voted = int(stage_2['voted'])
                else:
                    old_R = total_receipts[question_id][str(stage_1['index'])]['R']
                    old_Z = total_receipts[question_id][str(stage_1['index'])]['Z']
                    total_receipts[question_id][str(stage_1['index'])]['R'] = old_R + R
                    total_receipts[question_id][str(stage_1['index'])]['Z'] = old_Z + Z

                gen_1 = bytestrToPoint(current_question['gen_1'])
                gen_2 = bytestrToPoint(current_question['gen_2'])
                
                R_list.append(R)
                Z_list.append(Z)
                
            except ValueError:
                print("ERROR: Could not parse some proofs for ballot: {ballot['ballot_id']} into 'mpz'")
                valid = False
                has_gens = False
                good_points = False

            # if audited, check that R and Z in stage 1 match
            # the vote_secret and choice revealed in stage 2
            if audited:
                try:
                    if (gen_2 * r) != R:
                        print("ERROR: Bad secret found for ballot ID: {ballot['ballot_id']}")
                        valid = False
                    
                    if (gen_1 * (r + voted)) != Z:
                        print("ERROR: Bad secret OR vote value found for ballot ID: {ballot['ballot_id']}")
                        valid = False
                except ValueError:
                    print("ERROR: Could not parse some secrets for ballot: {ballot['ballot_id']} into Points")
                    valid = False
                    good_points = False
                
            # verify well-formedness proof
            if has_gens and not verifyZKProof(ballot['question_id'], gen_1, gen_2,
                                              R, Z, c_1, c_2,
                                              r_1, r_2):
                print("ERROR: Could not verify a zero-knowledge proof for ballot: {ballot['ballot_id']}")
                valid = False
            
        # verify overall extra number proof
        if good_points and not verifyNumProof(ballot['question_id'], gen_1, gen_2,
                                              R_list, Z_list, num_c, num_r,
                                              int(ballot['max_answers'])):
            print("ERROR: Could not verify the total number proof for ballot: {ballot['ballot_id']}")
            valid = False


    # once all ballots iterated through, verify final tallies and sums
    for question_id, question_dict in questions.items():
        gen_1 = bytestrToPoint(question_dict['gen_1'])
        gen_2 = bytestrToPoint(question_dict['gen_2'])
        
        for choice_id, choice_dict in question_dict['choices'].items():
            s = hexToMpz(choice_dict['s'])
            t = hexToMpz(choice_dict['t'])
            if s * gen_2 != total_receipts[question_id][choice_id]['R']:
                print(f"ERROR: Could not verify the secret sum for choice {choice_id} ({choice_dict['text']}) in question {question_id}.")
                valid = False
                
            if (s + t) * gen_1 != total_receipts[question_id][choice_id]['Z']:
                print(f"ERROR: Could not verify the tally for choice {choice_id} ({choice_dict['text']}) in question {question_id}.")
                valid = False
                
    if valid:
        print("###############################")
        print("Election has been verified!")
        print("###############################")
        return True
    
    print("###############################")
    print("Election is **NOT** verified! Please contact the election organiser.")
    print("###############################")
    return False        

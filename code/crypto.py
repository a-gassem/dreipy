"""
A **multiplicative cyclic** group G is one where EVERY ELEMENT IS THE
POWER OF A PARTICULAR ELEMENT IN THE GROUP (g). I.e. g is a generator
if for all y in G, there exists k: y = g^k.

**additive cyclic** groups are those where g is a generator if:
for all y in G, there exists k such that y = gk

This is the same as G = <g>

Note that groups can have multiple generators.

A subgroup S is simply a subset of a group, G.

The order of a group, G is denoted |G| and is defined as:
The smallest positive integer n such that a^n = e (where e = identity,
usually 0)

If G is a finite cyclic group of order n, all elements in G have order,
t, such that t | n

Generators of Z

Subgroup G_q of group Z_p means:
- 

We pick two large primes where q | (p-1) --> p = rq + 1

For a cyclic group G_n (order n)

Elliptic curves:
1. Choose two initial points, A and B on curve of form y^2 = x^3 + ax + b
    reflect from the third point on the curve on that line
    to other side of x-axis. Let this new point be A'. Repeat n times between
    A' and A. Just having first and last point means it's hard to know n
    without doing the whole series.

2. choose values that are in a multiplicative cyclic group with a large prime
    as the maximum, curve equation, public point on the curve.

3. privately select a number, n, that is the number of times we dot on the
    curve

Recommended prime field elliptic curves:
https://nvlpubs.nist.gov/nistpubs/FIPS/NIST.FIPS.186-4.pdf
"""

import gmpy2
from gmpy2 import mpz, powmod, divexact
from ecdsa import NIST256p, SigningKey, VerifyingKey
from ecdsa.ellipticcurve import Point, INFINITY
from cryptography.hazmat.primitives import hashes

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
    """Signs the passed string with the stored private key, return as hex string."""
    return private.sign(bytes(string, 'utf-8')).hex()

def verifyData(data: str, key: VerifyingKey, signature: str) -> bool:
    """Verifies that some given data was signed with the SigningKey paired
with the passed VerifyingKey based on a signature in hex form."""
    return key.verify(bytes.fromhex(signature), bytes(data, 'utf-8'))

def generateKeyPair() -> Tuple[mpz, mpz]:
    """Generates a public/private key pair for the current curve"""
    private = SigningKey.generate(curve=NIST256p)
    public = private.verifying_key
    return private, public

def hashElectionString(election_string: str, count: int = None) -> mpz:
    """Returns a large integer derived from a SHA-256 hash of the election
id, current iteration of the parent loop, and the generator for the EC being
used."""
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
    
    # manually create second generator according to supervisor's algorithm
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
    return (g1 * r) + (g1 * v)

def generateZKProof(question_id: str, g2: Point, R: Point, Z: Point, r: mpz) \
    -> Tuple[str, str, str, str]:
    """Zero-knowledge proof of knowledge and equality of the following discrete
logarithms:
P_K{S: (G_1 = g_1^S AND G_2 = g_2^S) OR (G_3 = g_3^S AND G_3 = g_3^S)}

((R = g2^r) AND ((Z div g1) = g1^r)) OR ((R = g2^r) AND (Z = g1^r))

We are proving that either we didn't vote for this (v = 0) or we did (v = 1)

We generate an R and Z for each of the m choices. We need to do a proof of
well-formedness for each of these R and Z results and then an aggregate proof
to show that exactly k of the votes are 1.

This method needs to therefore be run for each R, Z, r tuple.
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
    return (hex(c_1)[2:], hex(c_2)[2:], hex(abs(w - (c_1 * r)))[2:], hex(r_2)[2:])

def verifyZKProof(question_id: str, g2: Point, R: Point, Z: Point, r: mpz,
                  proof_c1: mpz, proof_c2: mpz, proof_r1: mpz, proof_r2: mpz) \
                  -> bool:
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

    c = proofZKHash(question_id, g1, G_1, g2, G_2, g3, G_3, g4, G_4, t_1, t_2,
                    t_3, t_4)

    return (proof_c1 + proof_c2) == c

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
    from helpers import pointToBytestr
    tup = (proof_id, pointToBytestr(g1), pointToBytestr(G_1), pointToBytestr(g2),
           pointToBytestr(G_2), pointToBytestr(g3), pointToBytestr(G_3),
           pointToBytestr(g4), pointToBytestr(G_4), pointToBytestr(t_1),
           pointToBytestr(t_2), pointToBytestr(t_3), pointToBytestr(t_4))
    return mpz(int.from_bytes(bytes.fromhex(hashString(str(tup))),
                              byteorder="big")
               )

def pointSum(point_list: List[Point]) -> Optional[Point]:
    """Given a list of Points, successively adds them together and returns
the result. If the list is empty then returns None."""
    if not point_list:
        return None

    curr_point = point_list[0]
    for i in range(1, len(point_list)):
        next_point = point_list[i]
        curr_point = curr_point + next_point

    return curr_point

def generateNumProof(question_id: str, g2: Point,  R_list: List[Point],
                     Z_list: List[Point], r_list: List[mpz], num_choices: int) \
                     -> Tuple[str, str]:
    """Zero-knowledge proof of knowledge and equality of form:

P_K{S: G_1 = g_1^S AND G_2 = g_2^S}

that exactly k votes in a ballot are 1:
((PROD{Z} div g1^k = g1^r_sum) AND (PROD{R} = g2^r_sum))
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

def verifyNumProof(question_id: str, g2: Point, R_list: List[Point],
                   Z_list: List[Point], proof_c: mpz, proof_r: mpz,
                   num_choices: int) -> bool:
    """Returns whether or not a given proof of knowledge and equality for the
number of votes in a tally is valid.
"""

    # calculate known products
    G_1 = pointSum(Z_list) + (-g1 * num_choices)
    G_2 = pointSum(R_list)

    # calculate exponentiations with proofs and bases
    t_1 = (g1 * proof_r) + (G_1 * proof_c)
    t_2 = (g2 * proof_r) + (G_2 * proof_c)

    # compare hashes
    return proof_c == proofNumHash(question_id, g1, G_1, g2, G_2, t1, t2)

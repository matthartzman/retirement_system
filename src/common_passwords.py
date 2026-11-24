"""A short list of passwords that are long enough to pass the length rule and still appear in every breach corpus.

SEC-06. This is not a breach database: it stops the obvious choices (keyboard walks, ``password123`` and friends,
long digit and letter runs) that an attacker tries first. Compared case-insensitively with spaces and
punctuation removed. Standard library only.
"""
from __future__ import annotations

import re

def _fold(text: str) -> str:
    """Lower case, the two substitutions everyone makes (@ for a, $ for s), then letters and digits only."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower().replace("@", "a").replace("$", "s"))


_COMMON = frozenset(_fold(w) for w in """
1234567890 0123456789 9876543210 12345678910 123456789012 1234567890123 12345678901 1q2w3e4r5t 1qaz2wsx3edc
qwertyuiop qwertyuiopasdf qwertyuiop123 qwerty1234 qwerty12345 qwerty123456 qwertyuiop1 asdfghjkl asdfghjkl123 asdfghjkl1
zxcvbnmasdf zxcvbnm123 1qazxsw2 1q2w3e4r5t6y q1w2e3r4t5 qazwsxedc qazwsxedcrfv zaq12wsxcde
password12 password123 password1234 password12345 password123456 password1! password! password01 password2024 password2025
password2026 passw0rd123 p@ssw0rd123 p@ssword123 p@ssw0rd1234 pass1234567 passwordpassword letmein123 letmein1234
welcome123 welcome1234 welcome12345 welcome2024 welcome2025 welcome2026 admin12345 admin123456 administrator adminadmin
admin1234567 changeme123 changeme1234 changemenow temp123456 temp1234567 tempPassword1 temporary123 temporary1234
iloveyou12 iloveyou123 iloveyou1234 iloveyou2 ilovemyself monkey1234 monkey12345 dragon1234 dragon12345 football123
baseball123 basketball1 superman123 batman12345 trustno1234 master12345 sunshine123 princess123 princess1234 shadow12345
michael1234 jennifer123 jordan23456 hunter12345 harley12345 ranger12345 buster12345 thomas12345 tigger12345 charlie1234
abc1234567 abcd123456 abcd1234567 abcdefghij abcdefghijk abcdefghijkl abcdefg123 abc123abc123 aaaaaaaaaa aaaaaaaaaaaa
1111111111 2222222222 3333333333 0000000000 1212121212 1231231231 1122334455 11223344556 5555555555 6666666666 7777777777
retirement retirement1 retirement12 retirement123 retirement2024 retirement2025 retirement2026 retirementplan
financial123 financial1234 insights123 planner1234 monarch1234 monarchmoney tailscale123 secret12345 secretpassword
mypassword1 mypassword12 mypassword123 myPassword123 mysecretpass yourpassword newpassword1 newpassword12 newpassword123
testtest123 test1234567 testpassword test123456 testing1234 default1234 defaultpass sample12345 example1234 guest123456
""".split())

def is_common_password(password: str) -> bool:
    """True for a listed password (compared after folding case, punctuation and the @/$ substitutions)."""
    folded = _fold(password)
    return bool(folded) and folded in _COMMON

"""Unit coverage for src/person_labels.py as pure functions.

Nicknames replacing Member_1/Member_2 (and legacy Husband/Wife) labels is a
rule the team has already had to re-derive once from workbook text diffs (see
person-label-architecture memory note). That protection today is incidental:
giant sheet/dashboard text-diff assertions happen to exercise ONE nickname
combination from the sample plan. These tests pin the module's actual
branches directly -- nickname present, absent, partial, single-filer, and the
account-id substitution regex -- so a change to the fallback chain or the
token pattern fails here first, with a precise diff, instead of surfacing as
an opaque mismatch three sheets away.

No workbook, no projection, no file I/O: these call member_nick,
display_account, and display_accounts_in_text directly as pure functions.
"""
from src.person_labels import display_account, display_accounts_in_text, member_nick


# ---------------------------------------------------------------------------
# member_nick
# ---------------------------------------------------------------------------

def test_member_nick_both_members_named_uses_nickname_over_name():
    cfg = {"h_name": "Matthew", "h_nick": "Matt", "w_name": "Patricia", "w_nick": "Patty"}
    assert member_nick(cfg, "member_1") == "Matt"
    assert member_nick(cfg, "member_2") == "Patty"


def test_member_nick_unnamed_default_config_falls_back_to_neutral_label():
    # No h_nick/h_name/w_nick/w_name keys at all -- the empty-plan default.
    cfg = {}
    assert member_nick(cfg, "member_1") == "Member 1"
    assert member_nick(cfg, "member_2") == "Member 2"


def test_member_nick_falls_back_to_stored_name_when_no_nickname_set():
    cfg = {"h_name": "Matthew", "w_name": "Patricia"}
    assert member_nick(cfg, "member_1") == "Matthew"
    assert member_nick(cfg, "member_2") == "Patricia"


def test_member_nick_single_filer_config_only_member_1_present():
    # Single-filer plans carry h_* keys and omit w_* entirely.
    cfg = {"h_name": "Matthew", "h_nick": "Matt"}
    assert member_nick(cfg, "member_1") == "Matt"
    # Member 2 still resolves to the neutral default rather than raising.
    assert member_nick(cfg, "member_2") == "Member 2"


def test_member_nick_partial_nicknames_one_named_one_not():
    cfg = {"h_name": "Matthew", "h_nick": "Matt", "w_name": "Patricia"}  # no w_nick
    assert member_nick(cfg, "member_1") == "Matt"
    assert member_nick(cfg, "member_2") == "Patricia"


def test_member_nick_empty_string_nickname_falls_through_to_name():
    # An empty string is falsy, so the 'or' chain skips it just like a
    # missing key -- distinct from a whitespace-only string (see below).
    cfg = {"h_nick": "", "h_name": "Matthew"}
    assert member_nick(cfg, "member_1") == "Matthew"


def test_member_nick_whitespace_only_nickname_collapses_to_empty_label():
    # WEAKNESS (documented, not fixed -- out of scope for this item): a
    # nickname that is present but whitespace-only is truthy in Python, so
    # the 'or' fallback chain never reaches h_name/the neutral default. The
    # module strips it only *after* selecting it, producing an empty label
    # instead of falling back to the stored name or 'Member 1'.
    cfg = {"h_nick": "   ", "h_name": "Matthew"}
    assert member_nick(cfg, "member_1") == ""


def test_member_nick_recognizes_h_and_m1_role_aliases_for_member_1():
    cfg = {"h_nick": "Matt", "w_nick": "Patty"}
    assert member_nick(cfg, "h") == "Matt"
    assert member_nick(cfg, "m1") == "Matt"


def test_member_nick_unrecognized_role_string_falls_through_to_member_2():
    # Only the exact strings 'member_1'/'m1'/'h' route to member 1; anything
    # else -- including plausible-looking variants -- hits the else branch.
    # No case-folding or alias table beyond the three literals.
    cfg = {"h_nick": "Matt", "w_nick": "Patty"}
    assert member_nick(cfg, "member_2") == "Patty"
    assert member_nick(cfg, "w") == "Patty"
    assert member_nick(cfg, "H") == "Patty"  # wrong case is NOT 'h'
    assert member_nick(cfg, "member_1 ") == "Patty"  # trailing space breaks match
    assert member_nick(cfg, "") == "Patty"


def test_member_nick_strips_surrounding_whitespace_from_resolved_label():
    cfg = {"h_nick": "  Matt  "}
    assert member_nick(cfg, "member_1") == "Matt"


# ---------------------------------------------------------------------------
# display_account
# ---------------------------------------------------------------------------

def test_display_account_member_1_and_member_2_prefixes():
    cfg = {"h_nick": "Matt", "w_nick": "Patty"}
    assert display_account("Member_1_IRA", cfg) == "Matt IRA"
    assert display_account("Member_2_Roth", cfg) == "Patty Roth"


def test_display_account_non_member_prefixed_id_just_gets_underscores_spaced():
    cfg = {"h_nick": "Matt", "w_nick": "Patty"}
    assert display_account("Family_Checking", cfg) == "Family Checking"


def test_display_account_falls_back_to_neutral_labels_in_default_config():
    assert display_account("Member_1_IRA", {}) == "Member 1 IRA"
    assert display_account("Member_2_401k", {}) == "Member 2 401k"


def test_display_account_blank_and_none_input_returns_empty_string():
    cfg = {"h_nick": "Matt"}
    assert display_account("", cfg) == ""
    assert display_account(None, cfg) == ""
    assert display_account("   ", cfg) == ""


def test_display_account_prefix_with_no_suffix_strips_to_bare_nickname():
    # 'Member_1_' with nothing after the trailing underscore: the f-string
    # leaves a trailing space ("Matt "), which the final .strip() removes.
    cfg = {"h_nick": "Matt"}
    assert display_account("Member_1_", cfg) == "Matt"


def test_display_account_underscores_inside_the_nickname_are_also_spaced():
    # WEAKNESS (documented, not fixed): the final `.replace('_', ' ')` runs
    # over the WHOLE composed label, including the nickname itself. A
    # nickname that legitimately contains an underscore gets mangled along
    # with the account-id underscores.
    cfg = {"h_nick": "Mom_and_Dad"}
    assert display_account("Member_1_IRA", cfg) == "Mom and Dad IRA"


def test_display_account_digit_outside_1_or_2_is_not_treated_as_a_member_prefix():
    # Only literal 'Member_1_' / 'Member_2_' prefixes are special-cased;
    # 'Member_3_' (or any other digit) falls through to the generic
    # underscore-to-space pass instead of nickname substitution.
    cfg = {"h_nick": "Matt", "w_nick": "Patty"}
    assert display_account("Member_3_IRA", cfg) == "Member 3 IRA"


# ---------------------------------------------------------------------------
# display_accounts_in_text
# ---------------------------------------------------------------------------

def test_display_accounts_in_text_substitutes_embedded_account_tokens():
    cfg = {"h_nick": "Matt"}
    text = "Roth conversion: Member_1_IRA $108,908→Member_1_Roth"
    assert (display_accounts_in_text(text, cfg)
            == "Roth conversion: Matt IRA $108,908→Matt Roth")


def test_display_accounts_in_text_with_no_account_tokens_passes_through_unchanged():
    cfg = {"h_nick": "Matt"}
    text = "No account references here, just a plain sentence."
    assert display_accounts_in_text(text, cfg) == text


def test_display_accounts_in_text_empty_and_none_pass_through_unchanged():
    cfg = {"h_nick": "Matt"}
    assert display_accounts_in_text("", cfg) == ""
    assert display_accounts_in_text(None, cfg) is None


def test_display_accounts_in_text_nickname_substring_of_another_word_is_not_mangled():
    # The regex matches only literal Member_1_*/Member_2_* tokens -- it never
    # does a blind string.replace() using the nickname -- so a nickname that
    # happens to be a substring of an unrelated word in the surrounding text
    # is left untouched. E.g. nickname 'Ann' must not turn 'Annual' into
    # 'AnnualRoth'-style garbage just because 'Ann' appears inside it.
    cfg = {"h_nick": "Ann"}
    text = "Annual review of Member_1_IRA occurs each January."
    assert (display_accounts_in_text(text, cfg)
            == "Annual review of Ann IRA occurs each January.")


def test_display_accounts_in_text_two_digit_account_number_does_not_false_match():
    # 'Member_10_Bucket' is not a valid Member_[12]_ token (the digit run
    # after Member_ is a single [12] char followed by an underscore), so it
    # must not be partially rewritten into 'Member_1' + '0_Bucket'.
    cfg = {"h_nick": "Matt"}
    text = "See Member_10_Bucket for details."
    assert display_accounts_in_text(text, cfg) == text


def test_display_accounts_in_text_multiple_distinct_tokens_in_one_string():
    cfg = {"h_nick": "Matt", "w_nick": "Patty"}
    text = "Transferred from Member_1_401k to Member_2_IRA and back to Member_1_Roth."
    assert (display_accounts_in_text(text, cfg)
            == "Transferred from Matt 401k to Patty IRA and back to Matt Roth.")


def test_display_accounts_in_text_coerces_non_string_input_to_string():
    # `str(text)` is applied before the regex, so a non-string value with no
    # matching pattern round-trips as its string form rather than raising.
    cfg = {"h_nick": "Matt"}
    assert display_accounts_in_text(12345, {"h_nick": "Matt"}) == "12345"

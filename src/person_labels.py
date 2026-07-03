"""Person and account display labels.

Every user-facing surface (workbook sheets, HTML dashboard, results explorer,
PDF) labels people by their household nickname instead of Member_1/Member_2 or
Husband/Wife. These helpers centralize that mapping so a nickname change in
Plan Data flows through every report without touching account identifiers,
which stay stable as data keys (client_holdings.csv, YTD imports).
"""


def member_nick(c, role):
    """Return the display nickname for 'member_1' / 'member_2'.

    Falls back to the stored name, then to a neutral 'Member N' label so
    reports never render blank where a person label is expected.
    """
    if role in ('member_1', 'm1', 'h'):
        return str(c.get('h_nick') or c.get('h_name') or 'Member 1').strip()
    return str(c.get('w_nick') or c.get('w_name') or 'Member 2').strip()


def display_account(acct, c):
    """Human label for an internal account id.

    'Member_1_IRA' -> '<nick> IRA', 'Family_Checking' -> 'Family Checking'.
    The raw id remains the join key everywhere; this is display-only.
    """
    raw = str(acct or '').strip()
    if not raw:
        return raw
    label = raw
    if raw.startswith('Member_1_'):
        label = f"{member_nick(c, 'member_1')} {raw[len('Member_1_'):]}"
    elif raw.startswith('Member_2_'):
        label = f"{member_nick(c, 'member_2')} {raw[len('Member_2_'):]}"
    return label.replace('_', ' ').strip()

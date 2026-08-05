from pathlib import Path


def test_ytd_account_setup_currency_fields_render_as_dollars():
    js = Path('frontend/js/dashboard.js').read_text(encoding='utf-8')
    assert 'function ytdAccountMoneyDisplay' in js
    assert 'value="${esc(ytdAccountMoneyDisplay(r["Prior Year End Balance"]))}"' in js
    assert 'value="${esc(ytdAccountMoneyDisplay(r["Current Value"]))}"' in js
    assert "updateYtdAccountMoney(${i},'Prior Year End Balance',this)" in js
    assert "blurYtdAccountMoney(${i},'Current Value',this)" in js
    assert 'placeholder=\"$0\"' in js


def test_ytd_account_currency_inputs_are_right_aligned():
    css = Path('frontend/css/dashboard.css').read_text(encoding='utf-8')
    assert '.ytd-account-table .ytd-money-input' in css
    assert 'text-align:right' in css
    assert 'font-variant-numeric:tabular-nums' in css

from types import SimpleNamespace

from src.core import TaxLot
from src.reporting.sheets_summary import _estimate_taxable_sale, _lot_guidance_summary


def test_taxable_sale_returns_specific_lot_guidance_loss_first():
    c = {
        'plan_start': 2026,
        'state': 'PA',
        'rebalance_lots_by_account': {
            'Taxable': {
                'ABC': [
                    TaxLot('ABC', 10, 1200, '2024-01-01'),  # loss at $100 price
                    TaxLot('ABC', 10, 500, '2020-01-01'),   # gain at $100 price
                ]
            }
        },
    }
    est = _estimate_taxable_sale(c, 'Taxable', 'ABC', 1000, 100)

    lots = est['selected_lots']
    assert lots
    assert lots[0]['purchase_date'] == '2024-01-01'
    assert lots[0]['gain_loss'] < 0
    assert lots[0]['proceeds'] == 1000
    assert est['tax_cost'] < 0
    assert 'Tax-loss-harvest candidate' in est['note']


def test_lot_guidance_summary_is_actionable_and_concise():
    rows = [
        {'purchase_date': '2024-01-01', 'shares': 10.0, 'term': 'LT', 'gain_loss': -200},
        {'purchase_date': '2020-01-01', 'shares': 5.0, 'term': 'LT', 'gain_loss': 250},
        {'purchase_date': '2021-01-01', 'shares': 2.0, 'term': 'LT', 'gain_loss': 50},
        {'purchase_date': '2022-01-01', 'shares': 1.0, 'term': 'LT', 'gain_loss': 10},
    ]
    text = _lot_guidance_summary(rows)
    assert text.startswith('Suggested lots:')
    assert '2024-01-01: 10.00 sh' in text
    assert '+1 more lot' in text

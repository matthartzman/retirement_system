"""Wave 4 item 4.7 (system review P8): account-level beneficiary/titling
capture, driving basis step-up per account instead of one household
property_regime, plus an audit sheet of review prompts (not verdicts).
"""
from __future__ import annotations

import unittest

from src.planning_engines import (
    _account_basis_step_fraction,
    _survivor_bonus_step_fraction,
    apply_death_transition,
    beneficiary_titling_audit,
)


def _minimal_config(**overrides):
    c = {
        'household_size': 2,
        'members': [{'name': 'Alex'}, {'name': 'Blair'}],
        'h_nick': 'Alex', 'w_nick': 'Blair',
        'h_death_yr': 2040, 'w_death_yr': 9999,
        'basis_step_up_at_death': True,
        'basis_step_up_property_regime': 'COMMON_LAW',
        'account_registry': [
            {'id': 'H_Taxable', 'owner_idx': 0, 'tax': 'taxable', 'acct_type': 'trust'},
            {'id': 'W_Taxable', 'owner_idx': 1, 'tax': 'taxable', 'acct_type': 'trust'},
        ],
        'account_titling': {},
    }
    c.update(overrides)
    return c


class BasisStepFractionTests(unittest.TestCase):
    def test_no_titling_falls_back_to_household_default(self):
        c = _minimal_config()
        self.assertEqual(_account_basis_step_fraction(c, 'H_Taxable', first_death=True), 1.0)
        c['basis_step_up_property_regime'] = 'HALF_STEP_UP'
        self.assertEqual(_account_basis_step_fraction(c, 'H_Taxable', first_death=True), 0.5)

    def test_community_property_titling_overrides_common_law_household(self):
        c = _minimal_config(account_titling={'H_Taxable': {'titling': 'COMMUNITY_PROPERTY'}})
        self.assertEqual(_account_basis_step_fraction(c, 'H_Taxable', first_death=True), 1.0)

    def test_jtwros_gives_half_step_up_regardless_of_household_regime(self):
        c = _minimal_config(account_titling={'H_Taxable': {'titling': 'JTWROS'}})
        self.assertEqual(_account_basis_step_fraction(c, 'H_Taxable', first_death=True), 0.5)
        c['basis_step_up_property_regime'] = 'COMMUNITY_PROPERTY'
        self.assertEqual(_account_basis_step_fraction(c, 'H_Taxable', first_death=True), 0.5)

    def test_separate_property_titling_still_fully_steps_up_the_decedents_own_share(self):
        c = _minimal_config(account_titling={'H_Taxable': {'titling': 'SEPARATE_PROPERTY'}},
                             basis_step_up_property_regime='COMMUNITY_PROPERTY')
        self.assertEqual(_account_basis_step_fraction(c, 'H_Taxable', first_death=True), 1.0)

    def test_survivor_bonus_follows_household_default_with_no_titling(self):
        c = _minimal_config()
        self.assertEqual(_survivor_bonus_step_fraction(c, 'W_Taxable'), 0.0)
        c['basis_step_up_property_regime'] = 'COMMUNITY_PROPERTY'
        self.assertEqual(_survivor_bonus_step_fraction(c, 'W_Taxable'), 1.0)

    def test_survivor_bonus_separate_property_opts_out_of_community_default(self):
        c = _minimal_config(account_titling={'W_Taxable': {'titling': 'SEPARATE_PROPERTY'}},
                             basis_step_up_property_regime='COMMUNITY_PROPERTY')
        self.assertEqual(_survivor_bonus_step_fraction(c, 'W_Taxable'), 0.0)

    def test_survivor_bonus_community_property_titling_overrides_common_law_default(self):
        c = _minimal_config(account_titling={'W_Taxable': {'titling': 'COMMUNITY_PROPERTY'}})
        self.assertEqual(_survivor_bonus_step_fraction(c, 'W_Taxable'), 1.0)


class DeathTransitionIntegrationTests(unittest.TestCase):
    def test_jtwros_account_gets_only_half_stepped_up_at_first_death(self):
        c = _minimal_config(account_titling={'H_Taxable': {'titling': 'JTWROS'}})
        balance = {'H_Taxable': 200_000.0, 'W_Taxable': 50_000.0}
        basis_free = {}
        apply_death_transition(c, balance, 2040, h_alive=False, w_alive=True, basis_free=basis_free)
        # H_Taxable rolled into W_Taxable (no matching survivor account of the
        # same type exists here other than W_Taxable itself), so the stepped
        # basis-free dollars land on whatever account absorbed the balance.
        total_basis_free = sum(basis_free.values())
        self.assertAlmostEqual(total_basis_free, 100_000.0, places=2)

    def test_no_titling_on_file_steps_up_the_whole_account_unchanged(self):
        c = _minimal_config()
        balance = {'H_Taxable': 200_000.0, 'W_Taxable': 50_000.0}
        basis_free = {}
        apply_death_transition(c, balance, 2040, h_alive=False, w_alive=True, basis_free=basis_free)
        total_basis_free = sum(basis_free.values())
        self.assertAlmostEqual(total_basis_free, 200_000.0, places=2)

    def test_survivors_community_property_account_also_gets_stepped_up(self):
        c = _minimal_config(account_titling={'W_Taxable': {'titling': 'COMMUNITY_PROPERTY'}})
        balance = {'H_Taxable': 200_000.0, 'W_Taxable': 50_000.0}
        basis_free = {}
        apply_death_transition(c, balance, 2040, h_alive=False, w_alive=True, basis_free=basis_free)
        # W_Taxable's own balance (50k, community property survivor bonus)
        # plus H_Taxable's full 200k (no titling override, household default
        # steps it up in full) both land here once H_Taxable rolls in.
        self.assertAlmostEqual(basis_free.get('W_Taxable', 0.0), 250_000.0, places=2)


class BeneficiaryTitlingAuditTests(unittest.TestCase):
    def _config_with_titling(self, titling_map, **overrides):
        c = {
            'account_registry': [
                {'id': 'H_IRA', 'owner_idx': 0, 'tax': 'pre_tax', 'acct_type': 'traditional_ira', 'label': "Alex's IRA"},
                {'id': 'H_Taxable', 'owner_idx': 0, 'tax': 'taxable', 'acct_type': 'trust', 'label': "Alex's Trust"},
            ],
            'account_titling': titling_map,
            'basis_step_up_property_regime': 'COMMON_LAW',
            'estate_tax_objective_mode': 'BALANCED',
            'former_spouse_name': '',
            'state': 'Illinois',
        }
        c.update(overrides)
        return c

    def test_no_titling_data_produces_no_findings(self):
        c = self._config_with_titling({})
        self.assertEqual(beneficiary_titling_audit(c), [])

    def test_retirement_account_with_no_primary_beneficiary_flags_estate_default(self):
        c = self._config_with_titling({'H_IRA': {'primary_beneficiary': '', 'contingent_beneficiary': ''}})
        flags = [f[2] for f in beneficiary_titling_audit(c)]
        self.assertIn('estate_named_by_default', flags)

    def test_primary_without_contingent_flags(self):
        c = self._config_with_titling({'H_IRA': {'primary_beneficiary': 'Jordan', 'contingent_beneficiary': ''}})
        flags = [f[2] for f in beneficiary_titling_audit(c)]
        self.assertIn('no_contingent', flags)

    def test_former_spouse_still_named_flags(self):
        c = self._config_with_titling(
            {'H_IRA': {'primary_beneficiary': 'Pat Jones', 'contingent_beneficiary': 'Jordan'}},
            former_spouse_name='Pat Jones',
        )
        flags = [f[2] for f in beneficiary_titling_audit(c)]
        self.assertIn('ex_spouse_named', flags)

    def test_minor_named_outright_flags_without_a_wrapper(self):
        c = self._config_with_titling({'H_IRA': {'primary_beneficiary': 'Sam (minor)', 'contingent_beneficiary': 'Jordan'}})
        flags = [f[2] for f in beneficiary_titling_audit(c)]
        self.assertIn('minor_named_outright', flags)

    def test_minor_named_with_utma_wrapper_does_not_flag(self):
        c = self._config_with_titling({'H_IRA': {'primary_beneficiary': 'Sam (minor) UTMA', 'contingent_beneficiary': 'Jordan'}})
        flags = [f[2] for f in beneficiary_titling_audit(c)]
        self.assertNotIn('minor_named_outright', flags)

    def test_trust_beneficiary_without_see_through_flags_on_a_retirement_account(self):
        c = self._config_with_titling({'H_IRA': {'primary_beneficiary': 'The Alex Family Trust', 'contingent_beneficiary': 'Jordan',
                                                  'trust_see_through': False}})
        flags = [f[2] for f in beneficiary_titling_audit(c)]
        self.assertIn('trust_no_see_through', flags)

    def test_trust_beneficiary_with_see_through_marked_true_does_not_flag(self):
        c = self._config_with_titling({'H_IRA': {'primary_beneficiary': 'The Alex Family Trust', 'contingent_beneficiary': 'Jordan',
                                                  'trust_see_through': True}})
        flags = [f[2] for f in beneficiary_titling_audit(c)]
        self.assertNotIn('trust_no_see_through', flags)

    def test_jtwros_titling_flags_when_estate_tax_objective_is_active(self):
        c = self._config_with_titling({'H_Taxable': {'titling': 'JTWROS'}}, estate_tax_objective_mode='STRONG')
        flags = [f[2] for f in beneficiary_titling_audit(c)]
        self.assertIn('jtwros_defeats_credit_shelter', flags)

    def test_jtwros_titling_does_not_flag_when_estate_tax_objective_is_off(self):
        c = self._config_with_titling({'H_Taxable': {'titling': 'JTWROS'}}, estate_tax_objective_mode='OFF')
        flags = [f[2] for f in beneficiary_titling_audit(c)]
        self.assertNotIn('jtwros_defeats_credit_shelter', flags)

    def test_separate_property_in_a_community_property_state_flags(self):
        c = self._config_with_titling({'H_Taxable': {'titling': 'SEPARATE_PROPERTY'}}, state='California')
        flags = [f[2] for f in beneficiary_titling_audit(c)]
        self.assertIn('community_property_defeated', flags)

    def test_separate_property_in_a_common_law_state_does_not_flag(self):
        c = self._config_with_titling({'H_Taxable': {'titling': 'SEPARATE_PROPERTY'}}, state='Illinois')
        flags = [f[2] for f in beneficiary_titling_audit(c)]
        self.assertNotIn('community_property_defeated', flags)


class DataIoAndBackfillWiringTests(unittest.TestCase):
    def test_parse_advanced_modules_reads_account_titling_section(self):
        from src.data_io import parse_advanced_modules
        data = {
            'Account Titling': {
                'Member_1_IRA': {
                    'primary_beneficiary': 'Jordan',
                    'contingent_beneficiary': 'Sam',
                    'titling': 'jtwros',
                    'trust_see_through': 'TRUE',
                }
            }
        }
        result = parse_advanced_modules(data)
        entry = result['account_titling']['Member_1_IRA']
        self.assertEqual(entry['primary_beneficiary'], 'Jordan')
        self.assertEqual(entry['contingent_beneficiary'], 'Sam')
        self.assertEqual(entry['titling'], 'JTWROS')
        self.assertTrue(entry['trust_see_through'])

    def test_former_spouse_name_backfill_entry_wired_to_estate_csv(self):
        import src.server.app_core as app_core
        entry = next(e for e in app_core.PLAN_DATA_BACKFILL_ENTRIES if e.rows is app_core.FORMER_SPOUSE_UI_PLAN_DATA_ROWS)
        self.assertEqual(entry.file_name, "client_insurance_estate.csv")

    def test_account_titling_backfill_entry_wired_to_estate_csv(self):
        import src.server.app_core as app_core
        entry = next(e for e in app_core.PLAN_DATA_BACKFILL_ENTRIES if e.rows is app_core._account_titling_ui_plan_data_rows)
        self.assertEqual(entry.file_name, "client_insurance_estate.csv")

    def test_account_titling_rows_generated_per_holdings_account(self):
        import src.server.app_core as app_core
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as d:
            target_dir = Path(d)
            (target_dir / "client_holdings.csv").write_text(
                "account,symbol,purchase_date,shares,purchase_price,lot_type\n"
                "Member_1_IRA,VTI,2020-01-01,10,100,long\n"
                "Family_Checking,CASH,2020-01-01,1000,1,\n",
                encoding="utf-8",
            )
            generated = app_core._account_titling_ui_plan_data_rows(target_dir)
        by_account = {}
        for section, sub, label, value, units, notes in generated:
            self.assertEqual(section, "Account Titling")
            by_account.setdefault(sub, {})[label] = (value, units)
        self.assertEqual(set(by_account.keys()), {"Member_1_IRA", "Family_Checking"})
        for sub, fields in by_account.items():
            self.assertEqual(set(fields.keys()), {
                "primary_beneficiary", "contingent_beneficiary", "titling", "trust_see_through",
            })
            self.assertEqual(fields["titling"][1], "choice")
            self.assertEqual(fields["trust_see_through"], ("FALSE", "bool"))


if __name__ == "__main__":
    unittest.main()

# Comprehensive Guide: Configuring Roth Conversion Financial Models

## Executive Summary

Roth conversion modeling is a quantitative financial planning technique used to determine whether—and to what extent—converting pre-tax retirement assets (Traditional IRA / 401(k)) into post-tax Roth assets is wealth-maximizing over a client's multi-decade horizon. 

This guide consolidates core concepts, mathematical principles, model parameter recommendations, heir tax mechanics, and additional influential financial variables into a unified reference document.

---

## 1. Conceptual Framework & Tax Rate Arbitrage

The foundation of any Roth conversion analysis rests on three core economic mechanisms:

### A. Tax Rate Arbitrage Delta
The primary mathematical driver of conversion benefit is the differential between the marginal tax rate paid today on the converted amount versus the expected marginal tax rate paid on future distributions in retirement:

$$\text{Tax Arbitrage Delta} = \text{Current Marginal Rate} - \text{Expected Retirement Marginal Rate}$$

* **Delta > 0 (Current Rate > Future Rate):** Traditional pre-tax growth is generally mathematically superior.
* **Delta < 0 (Current Rate < Future Rate):** Roth conversion is mathematically superior.
* **Delta = 0 (Current Rate = Future Rate):** Roth and Traditional yield identical after-tax terminal wealth **if conversion taxes are paid from the IRA**. However, if taxes are paid from **taxable cash**, Roth wins due to the expansion of tax-sheltered capacity.

### B. Tax Discount Rate Mechanics
The **Tax Discount Rate** adjusts or discounts future tax liabilities and tax savings back to present value. It accounts for:
1. **Time Value of Money & Opportunity Cost:** The rate of return foregone by paying tax dollars to the IRS today rather than keeping them invested.
2. **Legislative & Policy Risk:** Potential future changes in tax law, means-testing, or new surcharges.

### C. General Discount Rate Rules of Thumb
* **10%–12% Current Federal Bracket:** **0% Discount Needed.** Roth is almost universally optimal due to historically low tax brackets.
* **22%–24% Current Federal Bracket:** **5%–10% Policy Haircut / Hurdle.** Neutral zone requiring detailed multi-year income modeling.
* **32%+ Current Federal Bracket:** **10%+ Discount on Roth Value.** Pre-tax deductions are preferred unless tactical conversions occur in gap years (e.g., early retirement prior to Social Security / RMDs).

---

## 2. Model Parameter Recommendations

For a baseline profile with a **22%–24% current tax bracket**, **equal or higher expected future tax brackets**, a **long time horizon (15+ years)**, a **policy-neutral stance**, and a **balanced legacy goal**, the following configuration parameters should be used:

| Model Parameter | Recommended Value / Setting | Operational Meaning in Financial Model |
| :--- | :--- | :--- |
| **Tax Discount Rate** | **6.5% – 7.0% Nominal** *(or 4.0% – 5.0% Real)* | Set equal to expected long-term portfolio return ($g$). Ensures that when $T_{\text{current}} \le T_{\text{future}}$, the model recognizes the compounding value of locking in current rates. |
| **Optimize Lifetime Tax Rate** | **24.0% Marginal Rate Ceiling** *(Weight: 0.80 – 1.00)* | Directs the solver to "fill up" the 22% and 24% marginal federal brackets each year prior to RMD onset (e.g., ages 60–75) to prevent future spike into 32%+ brackets. |
| **Optimize Terminal Rate** | **0.50 Weight** *(Moderate Priority)* | Balances lifetime retirement consumption with maximizing tax-free terminal net worth passed to heirs (factoring in the SECURE Act 10-Year Rule). |

### Parameter Rationale & Mathematical Justification
1. **Tax Discount Rate = Portfolio Growth Rate ($g$):** When future tax rates are expected to be equal or higher, discounting future tax savings at a rate higher than portfolio growth would artificially underestimate Roth value. Setting the discount rate equal to expected portfolio return correctly captures tax-free compounding.
2. **Smoothing Lifetime Tax Rates:** Pre-tax accounts are subject to Required Minimum Distributions (RMDs) starting at age 73/75. Unplanned RMDs combined with Social Security can push retirees into significantly higher effective tax brackets. Converting aggressively up to the 24% bracket ceiling flattens the lifetime tax curve.
3. **Terminal Net Worth Weighting:** Roth dollars left in an estate carry a tax premium over Traditional IRA dollars because heirs inherit them 100% tax-free.

---

## 3. Heir Tax Mechanics & Inherited Account Rules

 Roth conversion decisions must factor in how inherited accounts are treated under tax law.

### Income Tax Rules for Beneficiaries
* **100% Tax-Free Withdrawals:** Heirs pay **$0 in federal or state income tax** on qualified distributions from an inherited Roth account.
* **The 5-Year Requirement:** The original account owner must have established and funded their first Roth IRA at least **5 years prior** to any distribution for earnings to be distributed tax-free. (Principal/contributions are always distributed tax-free).
* **Estate Tax vs. Income Tax:** While exempt from income tax, the total value of a Roth account is included in the deceased owner's gross estate for estate tax evaluation (though federal estate tax exemptions remain high).

### Distribution Timelines (SECURE Act)

| Beneficiary Category | Mandatory Distribution Rules | Strategic Implication |
| :--- | :--- | :--- |
| **Spouse Beneficiary** | Can roll inherited Roth directly into their own Roth IRA. Exempt from RMDs. | Account continues compounding tax-free for the surviving spouse's lifetime. |
| **Non-Spouse Heirs** *(Children, relatives)* | Subject to the **SECURE Act 10-Year Rule**. Must fully liquidate the account by Dec 31 of the 10th year post-death. | **No required annual distributions in years 1–9.** Heirs can allow 100% of the funds to compound tax-free for 10 full years before taking a single tax-free lump sum in Year 10. |
| **Eligible Designated Beneficiaries** *(Minor children, disabled, chronically ill)* | Exempt from 10-Year Rule. Allowed to stretch distributions over their life expectancy. | Maximizes multi-generational tax-free compounding. |

---

## 4. Influential Model Variables & Recommendations

To build a robust, institutional-grade Roth conversion model, several additional influential variables should be integrated into the planning engine:

### Variable 1: Conversion Tax Payment Source (Taxable Cash vs. IRA Withholding)
* **Impact:** **Critical Multiplier.**
* **Mechanism:** Paying conversion taxes using funds from a taxable brokerage account preserves 100% of the converted IRA capital inside the Roth tax shield. Furthermore, it reduces the taxable brokerage account (which would otherwise generate ongoing drag from dividends and capital gains). Paying taxes out of the IRA itself severely diminishes conversion benefits and may trigger early withdrawal penalties if under age 59½.
* **Recommendation:** Set the model constraint to **pay conversion taxes exclusively from cash or taxable brokerage assets**.

### Variable 2: Medicare Part B & D IRMAA Surcharges
* **Impact:** **High (2-Year Lookback Surcharge).**
* **Mechanism:** Income generated by a Roth conversion increases Modified Adjusted Gross Income (MAGI). Crossing Income-Related Monthly Adjustment Amount (IRMAA) thresholds increases Medicare Part B and Part D premiums for both spouses two years later.
* **Recommendation:** Map exact IRMAA tier brackets into the model and establish "bumpers" so that conversion amounts stop just below the next IRMAA cliff (e.g., $206,000 or $258,000 MAGI for married filing jointly) unless the tax bracket savings far outweigh the surcharge.

### Variable 3: State Income Tax & Residency Arbitrage
* **Impact:** **Moderate to High.**
* **Mechanism:** State tax rates vary dramatically (0% in FL, TX, NV, WA vs. up to 13.3%+ in CA, NY, IL). 
* **Recommendation:** If the client plans to relocate to a lower-tax state in retirement, defer conversions until after the residency change is established. If remaining in a high-tax state, factor combined state + federal marginal rates into the current conversion cost analysis.

### Variable 4: The Surviving Spouse Tax Trap (Single Filer Compression)
* **Impact:** **Very High for Married Couples.**
* **Mechanism:** Upon the death of the first spouse, the surviving spouse inherits the entire pre-tax IRA portfolio but must file taxes as a **Single Filer**. Single tax brackets are half as wide, effectively doubling the marginal tax rate on the exact same RMD income stream.
* **Recommendation:** Accelerate Roth conversions during joint filing years to protect the surviving spouse from being pushed into top-tier single tax brackets later in life.

### Variable 5: Social Security Taxation ("Tax Torpedo")
* **Impact:** **Moderate.**
* **Mechanism:** Pre-tax IRA distributions increase Provisional Income, causing up to 85% of Social Security benefits to become taxable (creating effective marginal tax rates up to 1.85x the statutory rate). Roth withdrawals do not count toward Provisional Income.
* **Recommendation:** Model conversions in the gap years between retirement and Social Security claim age (e.g., ages 60–70) to shrink pre-tax balances before Social Security benefits begin.

### Variable 6: Asset Location & Sequence of Returns Optimization
* **Impact:** **Moderate to High.**
* **Mechanism:** Not all dollars in an IRA should be converted equally. Asset classes with the highest expected growth rates (e.g., equities, high-beta assets) derive the greatest lifetime benefit from being placed in a Roth account.
* **Recommendation:** Integrate asset location rules into the model: convert equity-heavy sleeves to Roth first, leaving fixed income/bonds in Traditional accounts.

---

## 5. Summary Implementation Checklist

1. **Set Baseline Tax Rates:** Input federal and state marginal tax tables (accounting for scheduled TCJA sunsets).
2. **Configure Discount Rate:** Set equal to portfolio expected return (~6.5%–7.0% nominal).
3. **Establish Conversion Ceilings:** Limit conversions to the top of the 24% bracket while capping income below major Medicare IRMAA thresholds.
4. **Source Tax Payments:** Direct conversion tax payments to come from taxable cash reserves.
5. **Optimize Asset Location:** Direct high-growth equity assets into converted Roth accounts.
6. **Account for Legacy Rules:** Factor in the tax-free 10-year compounding rule for non-spouse beneficiaries under the SECURE Act.

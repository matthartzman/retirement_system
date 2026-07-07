/**
 * Tax & Income UI Helper Functions
 *
 * Pure functions for tax calculations, income analysis, and related UI logic.
 * Extracted from dashboard.js for testability and reusability.
 */

/**
 * Estimate marginal tax rate from income level
 * @param {number} income - Annual income in dollars
 * @param {number} year - Tax year (used to look up brackets)
 * @param {boolean} mfj - Married filing jointly (true) or single (false)
 * @returns {number} Estimated marginal tax rate (0-1)
 */
export function estimateMarginalTaxRate(income, year = 2025, mfj = true) {
  if (!Number.isFinite(income) || income <= 0) {
    return 0;
  }

  // 2025 tax brackets (simplified) - ordered by limit
  const brackets = mfj
    ? [
        { limit: 23500, rate: 0.1 },
        { limit: 95375, rate: 0.12 },
        { limit: 182100, rate: 0.22 },
        { limit: 231250, rate: 0.24 },
        { limit: 578125, rate: 0.32 },
        { limit: 696000, rate: 0.35 },
        { limit: Infinity, rate: 0.37 },
      ]
    : [
        { limit: 11750, rate: 0.1 },
        { limit: 47625, rate: 0.12 },
        { limit: 100525, rate: 0.22 },
        { limit: 191950, rate: 0.24 },
        { limit: 243725, rate: 0.32 },
        { limit: 609350, rate: 0.35 },
        { limit: Infinity, rate: 0.37 },
      ];

  // Find the bracket this income falls into
  for (const bracket of brackets) {
    if (income <= bracket.limit) {
      return bracket.rate;
    }
  }

  return 0.37;
}

/**
 * Calculate IRMAA (Income-Related Monthly Adjustment Amount) impact
 * @param {number} magi - Modified Adjusted Gross Income
 * @param {number} year - Calendar year
 * @returns {object} IRMAA breakdown { tier: string, monthly_adjustment: number, percentage_increase: number }
 */
export function calculateIrmaaAdjustment(magi, year = 2025) {
  if (!Number.isFinite(magi) || magi < 0) {
    return {
      tier: "Standard",
      monthly_adjustment: 0,
      percentage_increase: 0,
    };
  }

  // 2025 IRMAA thresholds (simplified for married filing jointly)
  const thresholds = [
    { limit: 103000, tier: "Standard", adjustment: 0 },
    { limit: 129000, tier: "Tier 2", adjustment: 70 },
    { limit: 155000, tier: "Tier 3", adjustment: 175 },
    { limit: 181000, tier: "Tier 4", adjustment: 280 },
    { limit: Infinity, tier: "Tier 5", adjustment: 385 },
  ];

  for (const threshold of thresholds) {
    if (magi <= threshold.limit) {
      return {
        tier: threshold.tier,
        monthly_adjustment: threshold.adjustment,
        percentage_increase: threshold.adjustment > 0 ? 0.2 : 0,
      };
    }
  }

  return {
    tier: "Tier 5",
    monthly_adjustment: 385,
    percentage_increase: 0.2,
  };
}

/**
 * Calculate Social Security taxation threshold impact
 * @param {number} income - Provisional income
 * @param {number} ssIncome - Social Security income
 * @returns {number} Percentage of SS income subject to taxation (0-0.85)
 */
export function calculateSocialSecurityTaxablePercent(income, ssIncome) {
  if (!Number.isFinite(income) || !Number.isFinite(ssIncome) || ssIncome <= 0) {
    return 0;
  }

  // Simplified: combines base amount + 50% of excess over first threshold
  const baseThreshold = 25000; // Single filer
  const secondThreshold = 34000;

  let taxable = 0;

  if (income > baseThreshold) {
    taxable += Math.min((income - baseThreshold) * 0.5, ssIncome * 0.5);
  }

  if (income > secondThreshold) {
    const secondTierIncome = Math.min(
      (income - secondThreshold) * 0.85,
      ssIncome * 0.85 - taxable
    );
    taxable += secondTierIncome;
  }

  return Math.min(taxable / ssIncome, 0.85);
}

/**
 * Validate income stream timing
 * @param {object} incomeStream - Income stream with start_age, end_age, amount
 * @returns {object} Validation result { valid: boolean, errors: string[] }
 */
export function validateIncomeStream(incomeStream) {
  const errors = [];

  if (!incomeStream || typeof incomeStream !== "object") {
    return { valid: false, errors: ["Invalid income stream object"] };
  }

  const startAge = Number(incomeStream.start_age);
  const endAge = Number(incomeStream.end_age);
  const amount = Number(incomeStream.amount);

  // Validate age range
  if (!Number.isFinite(startAge) || startAge < 0 || startAge > 120) {
    errors.push(`Invalid start age: ${startAge}`);
  }

  if (endAge && (!Number.isFinite(endAge) || endAge < startAge || endAge > 120)) {
    errors.push(`Invalid end age: ${endAge}`);
  }

  // Validate amount
  if (!Number.isFinite(amount) || amount < 0) {
    errors.push(`Invalid amount: ${amount}`);
  }

  // Warn if amount seems too large
  if (amount > 500000) {
    errors.push(
      `Income amount ${amount.toLocaleString()} seems unusually large`
    );
  }

  return {
    valid: errors.length === 0,
    errors: errors,
  };
}

/**
 * Calculate effective tax rate
 * @param {number} income - Gross income
 * @param {number} taxes - Total taxes paid
 * @returns {number} Effective tax rate (0-1)
 */
export function calculateEffectiveTaxRate(income, taxes) {
  if (!Number.isFinite(income) || income <= 0 || !Number.isFinite(taxes)) {
    return 0;
  }

  return Math.min(1, Math.max(0, taxes / income));
}

/**
 * Estimate tax impact of income change
 * @param {number} currentIncome - Current annual income
 * @param {number} newIncome - Projected annual income
 * @param {number} marginalRate - Marginal tax rate (0-1)
 * @returns {number} Estimated additional tax from income change
 */
export function estimateTaxImpactOfIncomeChange(
  currentIncome,
  newIncome,
  marginalRate = 0.24
) {
  if (
    !Number.isFinite(currentIncome) ||
    !Number.isFinite(newIncome) ||
    !Number.isFinite(marginalRate)
  ) {
    return 0;
  }

  const incomeDelta = newIncome - currentIncome;
  return Math.max(0, incomeDelta * marginalRate);
}

/**
 * Determine if income triggers Medicare IRMAA surcharges
 * @param {number} magi - Modified Adjusted Gross Income
 * @param {string} filingStatus - Filing status (MFJ, Single, etc.)
 * @returns {boolean} True if IRMAA surcharges apply
 */
export function triggersMedicareSurcharge(magi, filingStatus = "MFJ") {
  if (!Number.isFinite(magi)) {
    return false;
  }

  // 2025 thresholds for Medicare surcharges
  const thresholds = {
    MFJ: 103000,
    Single: 87000,
    HeadOfHousehold: 87000,
  };

  const threshold = thresholds[filingStatus] || 103000;
  return magi > threshold;
}

/**
 * Format tax amount for display
 * @param {number} amount - Tax amount in dollars
 * @param {number} decimals - Decimal places (default 0)
 * @returns {string} Formatted tax string (e.g., "$5,000" or "$5,000.50")
 */
export function formatTaxAmount(amount, decimals = 0) {
  if (!Number.isFinite(amount)) {
    return "—";
  }

  const formatter = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });

  return formatter.format(amount);
}

/**
 * Calculate withdrawal sequencing tax impact
 * @param {object} allocation - Account allocation { pretax: %, roth: %, taxable: % }
 * @param {number} withdrawalAmount - Amount to withdraw
 * @param {number} taxRate - Effective tax rate on withdrawals (0-1)
 * @returns {object} Breakdown { pretaxTax: amount, rothTax: amount, taxableTax: amount, totalTax: amount }
 */
export function calculateWithdrawalSequencingTax(
  allocation,
  withdrawalAmount,
  taxRate = 0.24
) {
  if (!allocation || !Number.isFinite(withdrawalAmount) || withdrawalAmount <= 0) {
    return {
      pretaxTax: 0,
      rothTax: 0,
      taxableTax: 0,
      totalTax: 0,
    };
  }

  const pretaxPct = Number(allocation.pretax) || 0;
  const rothPct = Number(allocation.roth) || 0;
  const taxablePct = Number(allocation.taxable) || 0;

  // Roth withdrawals are tax-free
  // Pretax withdrawals are fully taxable at withdrawal
  // Taxable withdrawals taxed on gains only
  const pretaxWithdrawal = withdrawalAmount * pretaxPct;
  const rothWithdrawal = withdrawalAmount * rothPct;
  const taxableWithdrawal = withdrawalAmount * taxablePct;

  return {
    pretaxTax: pretaxWithdrawal * taxRate,
    rothTax: 0,
    taxableTax: taxableWithdrawal * taxRate * 0.5, // Assume 50% are gains
    totalTax:
      pretaxWithdrawal * taxRate +
      taxableWithdrawal * taxRate * 0.5,
  };
}

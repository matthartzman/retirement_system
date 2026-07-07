/**
 * Allocation UI Helper Functions
 *
 * Pure functions for allocation-related calculations and formatting.
 * These functions are extracted from dashboard.js for testability.
 */

/**
 * Compute allocation deviation (actual vs target) for a given asset class
 * @param {number} actual - Actual allocation percentage
 * @param {number} target - Target allocation percentage
 * @returns {number} Deviation percentage (can be positive or negative)
 */
export function computeAllocationDeviation(actual, target) {
  if (target === 0) return actual;
  return actual - target;
}

/**
 * Determine if an allocation deviation is acceptable
 * @param {number} deviation - Deviation percentage
 * @param {number} tolerance - Tolerance threshold (e.g., 5 for ±5%)
 * @returns {boolean} True if within tolerance
 */
export function isDeviationAcceptable(deviation, tolerance = 5) {
  return Math.abs(deviation) <= tolerance;
}

/**
 * Format allocation percentage for display
 * @param {number} percentage - Allocation percentage
 * @param {number} decimals - Number of decimal places (default 1)
 * @returns {string} Formatted percentage string
 */
export function formatAllocationPercent(percentage, decimals = 1) {
  if (typeof percentage !== 'number' || isNaN(percentage)) {
    return '—';
  }
  return (percentage.toFixed(decimals)) + '%';
}

/**
 * Compute total allocation (safety check that allocations sum to 100%)
 * @param {Object} allocations - Object with asset class keys and percentage values
 * @returns {number} Sum of all allocation percentages
 */
export function computeTotalAllocation(allocations) {
  if (!allocations || typeof allocations !== 'object') {
    return 0;
  }
  return Object.values(allocations).reduce((sum, val) => {
    const num = parseFloat(val);
    return sum + (isNaN(num) ? 0 : num);
  }, 0);
}

/**
 * Validate that allocation percentages are realistic
 * @param {Object} allocations - Object with asset class keys and percentage values
 * @returns {Object} Validation result { valid: boolean, errors: string[] }
 */
export function validateAllocationPercentages(allocations) {
  const errors = [];

  if (!allocations || typeof allocations !== 'object') {
    return { valid: false, errors: ['Invalid allocations object'] };
  }

  const total = computeTotalAllocation(allocations);

  // Allow small rounding tolerance
  if (Math.abs(total - 100) > 0.1) {
    errors.push(`Total allocation is ${total.toFixed(2)}%, expected 100%`);
  }

  // Check individual allocations are non-negative
  Object.entries(allocations).forEach(([key, value]) => {
    const num = parseFloat(value);
    if (!isNaN(num) && num < 0) {
      errors.push(`${key} allocation is negative: ${num}%`);
    }
    if (!isNaN(num) && num > 100) {
      errors.push(`${key} allocation exceeds 100%: ${num}%`);
    }
  });

  return {
    valid: errors.length === 0,
    errors: errors
  };
}

/**
 * Get asset classes sorted by allocation (largest first)
 * @param {Object} allocations - Object with asset class keys and percentage values
 * @returns {Array} Array of [assetClass, percentage] tuples, sorted by percentage descending
 */
export function sortAllocationsBySize(allocations) {
  if (!allocations || typeof allocations !== 'object') {
    return [];
  }

  return Object.entries(allocations)
    .map(([key, value]) => [key, parseFloat(value) || 0])
    .sort((a, b) => b[1] - a[1]);
}

/**
 * Generate pie chart labels for allocation
 * @param {Object} allocations - Object with asset class keys and percentage values
 * @param {Object} options - Formatting options
 * @param {boolean} options.showPercent - Include percentage (default true)
 * @param {number} options.minLabelPercent - Minimum allocation to show label (default 5)
 * @returns {Object} Object with pie chart labels keyed by asset class
 */
export function generateAllocationLabels(allocations, options = {}) {
  const {
    showPercent = true,
    minLabelPercent = 5
  } = options;

  const labels = {};
  const sorted = sortAllocationsBySize(allocations);

  sorted.forEach(([assetClass, percentage]) => {
    if (percentage >= minLabelPercent) {
      labels[assetClass] = showPercent
        ? `${assetClass}: ${formatAllocationPercent(percentage)}`
        : assetClass;
    }
  });

  return labels;
}

/**
 * Compare two allocation strategies
 * @param {Object} allocation1 - First allocation
 * @param {Object} allocation2 - Second allocation
 * @returns {Object} Comparison result with deviations
 */
export function compareAllocations(allocation1, allocation2) {
  const result = {
    deviations: {},
    largestDeviation: 0,
    allocationValid: true
  };

  const allKeys = new Set([
    ...Object.keys(allocation1 || {}),
    ...Object.keys(allocation2 || {})
  ]);

  let maxDeviation = 0;

  allKeys.forEach(key => {
    const val1 = parseFloat(allocation1?.[key]) || 0;
    const val2 = parseFloat(allocation2?.[key]) || 0;
    const deviation = val2 - val1;

    result.deviations[key] = deviation;
    if (Math.abs(deviation) > Math.abs(maxDeviation)) {
      maxDeviation = deviation;
    }
  });

  result.largestDeviation = maxDeviation;

  // Validate both allocations
  const val1 = validateAllocationPercentages(allocation1);
  const val2 = validateAllocationPercentages(allocation2);
  result.allocationValid = val1.valid && val2.valid;

  return result;
}

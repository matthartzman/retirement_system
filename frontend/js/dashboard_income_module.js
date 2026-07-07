/**
 * Dashboard Income Module
 *
 * Extracted module for income-related planning features:
 * - Work income configuration
 * - Social Security timing and benefits
 * - Pension and annuity income
 * - Income projection and gap analysis
 *
 * Part of Phase D Tier 3B modularization.
 * Designed for feature-based code organization without breaking existing functionality.
 */

(function() {
  'use strict';

  const IncomeModule = {
    // Income configuration selectors
    selectors: {
      workIncomeForm: '[data-section="income_work"]',
      socialSecurityForm: '[data-section="income_retirement"]',
      pensionForm: '[data-section="pension"]',
      annuityForm: '[data-section="annuity"]',
    },

    /**
     * Initialize income module listeners and handlers
     */
    init() {
      this.attachEventHandlers();
      this.validateIncomeInputs();
    },

    /**
     * Attach event handlers to income-related form elements
     */
    attachEventHandlers() {
      // Work income handlers
      const workIncomeForm = document.querySelector(this.selectors.workIncomeForm);
      if (workIncomeForm) {
        workIncomeForm.addEventListener('change', (e) => this.handleWorkIncomeChange(e));
      }

      // Social Security handlers
      const ssForm = document.querySelector(this.selectors.socialSecurityForm);
      if (ssForm) {
        ssForm.addEventListener('change', (e) => this.handleSSChange(e));
      }
    },

    /**
     * Handle work income changes (salary, contributions, 401k amounts)
     */
    handleWorkIncomeChange(event) {
      const field = event.target;
      if (!field.dataset.label) return;

      // Validate income amount is non-negative
      if (field.value < 0) {
        field.value = 0;
      }

      // Trigger dependent calculations
      this.updateProjectedWorkIncomeGap();
    },

    /**
     * Handle Social Security claiming changes
     */
    handleSSChange(event) {
      const field = event.target;
      const isBenefitAmount = field.dataset.label && field.dataset.label.includes('benefit');
      const isClaimingAge = field.dataset.label && field.dataset.label.includes('age');

      if (isBenefitAmount) {
        this.validateBenefitAmount(field);
      }
      if (isClaimingAge) {
        this.validateClaimingAge(field);
      }
    },

    /**
     * Validate benefit amount is reasonable (prevent data entry errors)
     */
    validateBenefitAmount(field) {
      const value = parseFloat(field.value) || 0;
      // SS benefits rarely exceed $3,822/month (as of 2024)
      if (value > 10000) {
        console.warn(`Social Security benefit ${value} seems unusually high. Confirm value is correct.`);
      }
    },

    /**
     * Validate claiming age is reasonable
     */
    validateClaimingAge(field) {
      const value = parseInt(field.value) || 0;
      if (value < 62 || value > 85) {
        console.warn(`Claiming age ${value} is outside typical range (62-85). Confirm value is correct.`);
      }
    },

    /**
     * Calculate income needed to close the gap between spending and other sources
     */
    updateProjectedWorkIncomeGap() {
      // This would integrate with the main projection engine
      // Placeholder for integration point
      if (window.refreshProjection) {
        window.refreshProjection();
      }
    },

    /**
     * Validate all income inputs before projection
     */
    validateIncomeInputs() {
      const workIncomeForm = document.querySelector(this.selectors.workIncomeForm);
      if (workIncomeForm) {
        const inputs = workIncomeForm.querySelectorAll('input[type="number"]');
        inputs.forEach(input => {
          if (isNaN(input.value)) {
            input.value = 0;
          }
        });
      }
    },

    /**
     * Get total projected household income from all sources
     * @returns {number} Total annual income
     */
    getTotalProjectedIncome() {
      let total = 0;
      // Work income
      const workEarned = document.querySelector('[data-label*="salary"]')?.value || 0;
      total += parseFloat(workEarned) || 0;

      // Social Security
      const hSS = document.querySelector('[data-label*="h_ss_benefit"]')?.value || 0;
      const wSS = document.querySelector('[data-label*="w_ss_benefit"]')?.value || 0;
      total += (parseFloat(hSS) + parseFloat(wSS)) * 12 || 0;

      return total;
    },
  };

  // Export for use in main dashboard or as standalone module
  if (typeof window !== 'undefined') {
    window.DashboardIncomeModule = IncomeModule;
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = IncomeModule;
  }

})();

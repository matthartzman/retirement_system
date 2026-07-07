/**
 * Dashboard Strategy Module
 *
 * Extracted module for planning strategy features:
 * - Roth conversion policy and optimization
 * - Withdrawal sequencing strategy
 * - Asset allocation and location
 * - Allocation policy settings (risk, glide path, constraints)
 * - Distribution strategy planning
 * - HELOC and home equity strategies
 * - Charitable giving and entity planning
 *
 * Part of Phase D Tier 3B modularization.
 * Manages all strategy-related planning and decision workflows.
 */

(function() {
  'use strict';

  const StrategyModule = {
    // Strategy configuration selectors
    selectors: {
      rothConversionForm: '[data-section="roth_conversion"]',
      withdrawalStrategyForm: '[data-section="withdrawal_strategy"]',
      allocationAssetsForm: '[data-section="allocation_assets"]',
      allocationPolicyForm: '[data-section="allocation_policy"]',
      distributionStrategyForm: '[data-section="distribution_strategy"]',
      helocStrategyForm: '[data-section="heloc_strategy"]',
      charityForm: '[data-section="entity_charitable"]',
      strategyControls: '[data-strategy-control]',
      allocationModeSelector: '[data-allocation-mode]',
      conversionPolicySelector: '[data-conversion-policy]',
    },

    // Conversion policy options
    conversionPolicies: {
      none: 'No conversions',
      fixed_dollar: 'Fixed annual amount',
      bracket_fill: 'Bracket-fill policy',
      max_available: 'Maximum available',
    },

    // Withdrawal sequencing order options
    withdrawalOrder: {
      taxable_first: 'Taxable accounts first',
      tax_efficient: 'Tax-efficient sequencing',
      roth_last: 'Preserve Roth (last)',
      lifo: 'LIFO (most recent first)',
    },

    /**
     * Initialize strategy module
     */
    init() {
      this.attachEventHandlers();
      this.setupConversionPolicy();
      this.setupAllocationMode();
      this.loadStrategyDefaults();
    },

    /**
     * Attach event handlers to strategy elements
     */
    attachEventHandlers() {
      // Roth conversion policy changes
      const rothForm = document.querySelector(this.selectors.rothConversionForm);
      if (rothForm) {
        rothForm.addEventListener('change', (e) => this.handleConversionChange(e));
      }

      // Withdrawal strategy changes
      const withdrawalForm = document.querySelector(this.selectors.withdrawalStrategyForm);
      if (withdrawalForm) {
        withdrawalForm.addEventListener('change', (e) => this.handleWithdrawalChange(e));
      }

      // Allocation changes
      const allocationForm = document.querySelector(this.selectors.allocationAssetsForm);
      if (allocationForm) {
        allocationForm.addEventListener('change', (e) => this.handleAllocationChange(e));
      }

      // Allocation policy changes
      const policyForm = document.querySelector(this.selectors.allocationPolicyForm);
      if (policyForm) {
        policyForm.addEventListener('change', (e) => this.handlePolicyChange(e));
      }

      // HELOC strategy changes
      const helocForm = document.querySelector(this.selectors.helocStrategyForm);
      if (helocForm) {
        helocForm.addEventListener('change', (e) => this.handleHelocChange(e));
      }

      // Charitable strategy changes
      const charityForm = document.querySelector(this.selectors.charityForm);
      if (charityForm) {
        charityForm.addEventListener('change', (e) => this.handleCharityChange(e));
      }
    },

    /**
     * Setup Roth conversion policy selector
     */
    setupConversionPolicy() {
      const selector = document.querySelector(this.selectors.conversionPolicySelector);
      if (!selector) return;

      selector.addEventListener('change', (e) => {
        const policy = e.target.value;
        this.updateConversionControls(policy);
      });
    },

    /**
     * Update visible controls based on conversion policy
     */
    updateConversionControls(policy) {
      const form = document.querySelector(this.selectors.rothConversionForm);
      if (!form) return;

      // Hide all policy-specific controls
      form.querySelectorAll('[data-conversion-control]').forEach(el => {
        el.style.display = 'none';
      });

      // Show controls for selected policy
      if (policy === 'fixed_dollar') {
        const controls = form.querySelectorAll('[data-conversion-control="fixed_dollar"]');
        controls.forEach(el => el.style.display = '');
      } else if (policy === 'bracket_fill') {
        const controls = form.querySelectorAll('[data-conversion-control="bracket_fill"]');
        controls.forEach(el => el.style.display = '');
      }
    },

    /**
     * Setup allocation mode selector (optimizer vs manual)
     */
    setupAllocationMode() {
      const selector = document.querySelector(this.selectors.allocationModeSelector);
      if (!selector) return;

      selector.addEventListener('change', (e) => {
        const mode = e.target.value;
        this.setAllocationMode(mode);
      });
    },

    /**
     * Handle Roth conversion policy changes
     */
    handleConversionChange(event) {
      const field = event.target;
      if (!field.dataset.label) return;

      // Validate conversion amounts are non-negative
      if (field.type === 'number' && field.value < 0) {
        field.value = 0;
      }

      // Validate IRMAA guardrail thresholds
      if (field.dataset.label && field.dataset.label.includes('irmaa')) {
        this.validateIrmaaThreshold(field);
      }

      // Validate Medicare income limits
      if (field.dataset.label && field.dataset.label.includes('medicare')) {
        this.validateMedicareIncome(field);
      }

      this.scheduleStrategyRefresh();
    },

    /**
     * Validate IRMAA guardrail threshold
     */
    validateIrmaaThreshold(field) {
      const value = parseFloat(field.value) || 0;
      // IRMAA thresholds typically range $176k-$500k for MFJ
      if (value > 750000) {
        console.warn(`IRMAA threshold ${value} seems unusually high. Confirm value is correct.`);
      }
    },

    /**
     * Validate Medicare income assumption
     */
    validateMedicareIncome(field) {
      const value = parseFloat(field.value) || 0;
      // Medicare income for surcharge calculation should be realistic
      if (value < 0) {
        field.value = 0;
      }
    },

    /**
     * Handle withdrawal sequencing strategy changes
     */
    handleWithdrawalChange(event) {
      const field = event.target;
      if (!field.dataset.label) return;

      // Validate priority order (1-9 range for 9 account types)
      if (field.dataset.label && field.dataset.label.includes('priority')) {
        const value = parseInt(field.value) || 0;
        if (value < 1 || value > 9) {
          console.warn(`Withdrawal priority ${value} out of range. Use 1-9.`);
          field.value = Math.max(1, Math.min(9, value));
        }
      }

      this.scheduleStrategyRefresh();
    },

    /**
     * Handle asset allocation target changes
     */
    handleAllocationChange(event) {
      const input = event.target;
      if (!input.dataset.assetClass) return;

      const value = parseFloat(input.value) || 0;

      // Validate allocation is 0-100%
      if (value < 0) {
        input.value = 0;
      } else if (value > 100) {
        input.value = 100;
      }

      // Update allocation total
      this.updateAllocationTotal();
      this.scheduleStrategyRefresh();
    },

    /**
     * Update allocation total to show sum of all allocations
     */
    updateAllocationTotal() {
      const form = document.querySelector(this.selectors.allocationAssetsForm);
      if (!form) return;

      let total = 0;
      const inputs = form.querySelectorAll('[data-asset-class]');
      inputs.forEach(input => {
        total += parseFloat(input.value) || 0;
      });

      // Show warning if total does not equal 100%
      const totalDisplay = form.querySelector('[data-metric="allocation_total"]');
      if (totalDisplay) {
        totalDisplay.textContent = total + '%';
        totalDisplay.className = Math.abs(total - 100) > 1 ? 'allocation-warning' : '';
      }
    },

    /**
     * Handle allocation policy setting changes
     */
    handlePolicyChange(event) {
      const field = event.target;
      if (!field.dataset.label) return;

      // Validate risk tolerance (typically 1-10 scale or percentage)
      if (field.dataset.label && field.dataset.label.includes('risk')) {
        const value = parseFloat(field.value) || 0;
        if (value < 0 || value > 100) {
          console.warn(`Risk tolerance ${value} out of expected range`);
        }
      }

      // Validate expected return assumptions
      if (field.dataset.label && field.dataset.label.includes('return')) {
        const value = parseFloat(field.value) || 0;
        if (value < -5 || value > 15) {
          console.warn(`Expected return ${value}% seems unusual. Confirm value is reasonable.`);
        }
      }

      // Validate volatility assumptions
      if (field.dataset.label && field.dataset.label.includes('volatility')) {
        const value = parseFloat(field.value) || 0;
        if (value < 0 || value > 50) {
          console.warn(`Volatility ${value}% seems out of range (typically 5-40%)`);
        }
      }

      this.scheduleStrategyRefresh();
    },

    /**
     * Handle HELOC strategy changes
     */
    handleHelocChange(event) {
      const field = event.target;
      if (!field.dataset.label) return;

      // Validate credit limit is positive
      if (field.dataset.label && field.dataset.label.includes('limit')) {
        const value = parseFloat(field.value) || 0;
        if (value < 0) {
          field.value = 0;
        }
      }

      // Validate interest rate is reasonable (0-15%)
      if (field.dataset.label && field.dataset.label.includes('rate')) {
        const value = parseFloat(field.value) || 0;
        if (value < 0) {
          field.value = 0;
        } else if (value > 20) {
          console.warn(`HELOC rate ${value}% seems unusually high`);
        }
      }

      // Validate last draw year is in reasonable range
      if (field.dataset.label && field.dataset.label.includes('draw_year')) {
        const value = parseInt(field.value) || 0;
        const currentYear = new Date().getFullYear();
        if (value < currentYear || value > currentYear + 50) {
          console.warn(`Last draw year ${value} seems outside normal planning horizon`);
        }
      }

      this.scheduleStrategyRefresh();
    },

    /**
     * Handle charitable giving strategy changes
     */
    handleCharityChange(event) {
      const field = event.target;
      if (!field.dataset.label) return;

      // Validate charitable giving amounts are non-negative
      if (field.type === 'number' && field.value < 0) {
        field.value = 0;
      }

      // Validate QCD age restrictions (70.5+)
      if (field.dataset.label && field.dataset.label.includes('qcd_age')) {
        const value = parseInt(field.value) || 0;
        if (value < 70 || value > 120) {
          console.warn(`QCD election age ${value} should be 70.5 or older`);
        }
      }

      this.scheduleStrategyRefresh();
    },

    /**
     * Set allocation editing mode (optimizer vs user-defined)
     */
    setAllocationMode(mode) {
      const form = document.querySelector(this.selectors.allocationAssetsForm);
      if (!form) return;

      if (mode === 'optimizer') {
        form.classList.add('mode-optimizer');
        form.classList.remove('mode-manual');
      } else {
        form.classList.add('mode-manual');
        form.classList.remove('mode-optimizer');
      }
    },

    /**
     * Load strategy defaults from plan data
     */
    loadStrategyDefaults() {
      if (!window.currentPlanData) return;

      const plan = window.currentPlanData;

      // Load Roth conversion policy
      if (plan.roth_policy) {
        const selector = document.querySelector(this.selectors.conversionPolicySelector);
        if (selector) {
          selector.value = plan.roth_policy;
          this.updateConversionControls(plan.roth_policy);
        }
      }

      // Load allocation mode
      if (plan.allocation_mode) {
        const selector = document.querySelector(this.selectors.allocationModeSelector);
        if (selector) {
          selector.value = plan.allocation_mode;
          this.setAllocationMode(plan.allocation_mode);
        }
      }
    },

    /**
     * Schedule strategy refresh with debounce
     */
    scheduleStrategyRefresh() {
      if (this._refreshTimer) {
        clearTimeout(this._refreshTimer);
      }
      this._refreshTimer = setTimeout(() => {
        if (window.refreshProjection) {
          window.refreshProjection();
        }
      }, 500);
    },

    /**
     * Get current conversion policy
     */
    getConversionPolicy() {
      const selector = document.querySelector(this.selectors.conversionPolicySelector);
      if (!selector) return 'none';
      return selector.value || 'none';
    },

    /**
     * Get conversion annual amount (if fixed policy)
     */
    getConversionAmount() {
      const form = document.querySelector(this.selectors.rothConversionForm);
      if (!form) return 0;

      const input = form.querySelector('[data-label*="annual_amount"], [data-label*="fixed_amount"]');
      if (!input) return 0;

      return parseFloat(input.value) || 0;
    },

    /**
     * Get withdrawal sequencing order
     */
    getWithdrawalOrder() {
      const form = document.querySelector(this.selectors.withdrawalStrategyForm);
      if (!form) return [];

      const order = [];
      form.querySelectorAll('[data-account-type]').forEach(row => {
        const priority = parseInt(row.dataset.priority) || 999;
        const accountType = row.dataset.accountType;
        if (accountType) {
          order.push({ accountType, priority });
        }
      });

      return order.sort((a, b) => a.priority - b.priority);
    },

    /**
     * Get current allocation targets
     */
    getAllocationTargets() {
      const form = document.querySelector(this.selectors.allocationAssetsForm);
      if (!form) return {};

      const allocation = {};
      form.querySelectorAll('[data-asset-class]').forEach(input => {
        const assetClass = input.dataset.assetClass;
        if (assetClass) {
          allocation[assetClass] = parseFloat(input.value) || 0;
        }
      });

      return allocation;
    },

    /**
     * Get allocation policy settings
     */
    getAllocationPolicy() {
      const form = document.querySelector(this.selectors.allocationPolicyForm);
      if (!form) return {};

      const policy = {};
      form.querySelectorAll('[data-label]').forEach(input => {
        const label = input.dataset.label;
        if (label) {
          policy[label] = input.type === 'number' ? parseFloat(input.value) : input.value;
        }
      });

      return policy;
    },

    /**
     * Get HELOC strategy parameters
     */
    getHelocStrategy() {
      const form = document.querySelector(this.selectors.helocStrategyForm);
      if (!form) return null;

      const creditLimit = form.querySelector('[data-label*="credit_limit"]')?.value || 0;
      const rate = form.querySelector('[data-label*="rate"]')?.value || 0;
      const lastDrawYear = form.querySelector('[data-label*="last_draw"]')?.value || 0;

      if (!creditLimit || creditLimit <= 0) return null;

      return {
        creditLimit: parseFloat(creditLimit),
        rate: parseFloat(rate),
        lastDrawYear: parseInt(lastDrawYear),
      };
    },

    /**
     * Get charitable giving strategy
     */
    getCharitableStrategy() {
      const form = document.querySelector(this.selectors.charityForm);
      if (!form) return null;

      const vehicle = form.querySelector('[data-label*="vehicle"]')?.value || '';
      const annualAmount = form.querySelector('[data-label*="annual"]')?.value || 0;

      if (!vehicle || annualAmount <= 0) return null;

      return {
        vehicle,
        annualAmount: parseFloat(annualAmount),
      };
    },
  };

  // Export for use
  if (typeof window !== 'undefined') {
    window.DashboardStrategyModule = StrategyModule;
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = StrategyModule;
  }

})();

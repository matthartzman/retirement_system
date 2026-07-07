/**
 * Dashboard Assets Module
 *
 * Extracted module for asset and allocation planning features:
 * - Investment holdings and accounts
 * - Asset allocation targets
 * - Account balance tracking
 * - Special assets (HSA, 529, DAF, collectibles, etc.)
 * - Allocation optimization and rebalancing
 *
 * Part of Phase D Tier 3B modularization.
 * Manages all asset-related planning and display.
 */

(function() {
  'use strict';

  const AssetsModule = {
    // Asset management selectors
    selectors: {
      holdingsTable: '[data-holdings-table]',
      allocationTable: '[data-allocation-table]',
      accountBalancesForm: '[data-section="assets_home_cash"]',
      specialAssetsForm: '[data-section="assets_special"]',
      allocationSelectors: '[data-allocation-selector]',
    },

    // Account types for organization
    accountTypes: {
      taxable: ['brokerage', 'taxable_account'],
      pretax: ['traditional_ira', '401k', '403b', 'sep_ira', 'solo_401k'],
      roth: ['roth_ira', 'roth_401k', 'roth_conversion_ira'],
      other: ['hsa', '529', 'daf', 'trust', 'note_receivable'],
    },

    /**
     * Initialize assets module
     */
    init() {
      this.attachEventHandlers();
      this.loadHoldingsData();
      this.setupAllocationEditor();
    },

    /**
     * Attach event handlers to asset elements
     */
    attachEventHandlers() {
      // Holdings table changes
      const holdingsTable = document.querySelector(this.selectors.holdingsTable);
      if (holdingsTable) {
        holdingsTable.addEventListener('change', (e) => this.handleHoldingChange(e));
        holdingsTable.addEventListener('click', (e) => this.handleHoldingAction(e));
      }

      // Allocation changes
      const allocationTable = document.querySelector(this.selectors.allocationTable);
      if (allocationTable) {
        allocationTable.addEventListener('change', (e) => this.handleAllocationChange(e));
      }

      // Account balance updates
      const accountBalances = document.querySelector(this.selectors.accountBalancesForm);
      if (accountBalances) {
        accountBalances.addEventListener('change', (e) => this.handleAccountBalanceChange(e));
      }
    },

    /**
     * Handle holding amount or details change
     */
    handleHoldingChange(event) {
      const row = event.target.closest('[data-holding-id]');
      if (!row) return;

      const holdingId = row.dataset.holdingId;
      const fieldChanged = event.target.dataset.field;

      // Validate common fields
      if (fieldChanged === 'shares') {
        const value = parseFloat(event.target.value) || 0;
        if (value < 0) {
          event.target.value = 0;
        }
      }

      if (fieldChanged === 'cost_basis') {
        this.validateCostBasis(event.target);
      }

      // Update derived calculations
      this.recalculateHoldingMetrics(holdingId);
      this.updatePortfolioTotals();
      this.scheduleRefresh();
    },

    /**
     * Handle holding actions (delete, edit details, etc.)
     */
    handleHoldingAction(event) {
      const action = event.target.dataset.action;
      const row = event.target.closest('[data-holding-id]');
      if (!row) return;

      const holdingId = row.dataset.holdingId;

      switch (action) {
        case 'delete':
          this.deleteHolding(holdingId);
          break;
        case 'edit_details':
          this.editHoldingDetails(holdingId);
          break;
        case 'export':
          this.exportHolding(holdingId);
          break;
      }
    },

    /**
     * Validate cost basis input
     */
    validateCostBasis(input) {
      const value = parseFloat(input.value) || 0;
      if (value < 0) {
        input.value = 0;
        console.warn('Cost basis cannot be negative');
      }
    },

    /**
     * Recalculate holding metrics (current value, gain/loss, etc.)
     */
    recalculateHoldingMetrics(holdingId) {
      const row = document.querySelector(`[data-holding-id="${holdingId}"]`);
      if (!row) return;

      const shares = parseFloat(row.querySelector('[data-field="shares"]')?.value) || 0;
      const price = parseFloat(row.querySelector('[data-field="price"]')?.value) || 0;
      const costBasis = parseFloat(row.querySelector('[data-field="cost_basis"]')?.value) || 0;

      const currentValue = shares * price;
      const gain = currentValue - costBasis;
      const gainPercent = costBasis > 0 ? (gain / costBasis) * 100 : 0;

      // Update display
      const currentValueCell = row.querySelector('[data-metric="current_value"]');
      if (currentValueCell) {
        currentValueCell.textContent = currentValue.toLocaleString('en-US', {
          style: 'currency',
          currency: 'USD',
        });
      }

      const gainCell = row.querySelector('[data-metric="gain"]');
      if (gainCell) {
        gainCell.textContent = gain.toLocaleString('en-US', {
          style: 'currency',
          currency: 'USD',
        });
        gainCell.className = gain >= 0 ? 'gain' : 'loss';
      }
    },

    /**
     * Update portfolio totals (by account, by account type, by asset class)
     */
    updatePortfolioTotals() {
      const table = document.querySelector(this.selectors.holdingsTable);
      if (!table) return;

      let totalValue = 0;
      const typeValues = {};

      Object.keys(this.accountTypes).forEach(type => {
        typeValues[type] = 0;
      });

      // Sum across all holdings
      table.querySelectorAll('[data-holding-id]').forEach(row => {
        const shares = parseFloat(row.querySelector('[data-field="shares"]')?.value) || 0;
        const price = parseFloat(row.querySelector('[data-field="price"]')?.value) || 0;
        const value = shares * price;
        totalValue += value;

        const accountType = row.dataset.accountType;
        if (typeValues.hasOwnProperty(accountType)) {
          typeValues[accountType] += value;
        }
      });

      // Update totals display
      const totalDisplay = document.querySelector('[data-metric="portfolio_total"]');
      if (totalDisplay) {
        totalDisplay.textContent = totalValue.toLocaleString('en-US', {
          style: 'currency',
          currency: 'USD',
        });
      }

      // Update type breakdowns
      Object.entries(typeValues).forEach(([type, value]) => {
        const typeDisplay = document.querySelector(`[data-metric="total_${type}"]`);
        if (typeDisplay) {
          typeDisplay.textContent = value.toLocaleString('en-US', {
            style: 'currency',
            currency: 'USD',
          });
        }
      });
    },

    /**
     * Load holdings data into table
     */
    loadHoldingsData() {
      const table = document.querySelector(this.selectors.holdingsTable);
      if (!table || !window.currentPlanData) return;

      const holdings = window.currentPlanData.holdings || [];
      holdings.forEach(holding => {
        // This would integrate with actual data loading
        // Placeholder for integration
      });
    },

    /**
     * Setup allocation editor mode
     */
    setupAllocationEditor() {
      const selectors = document.querySelectorAll(this.selectors.allocationSelectors);
      selectors.forEach(selector => {
        selector.addEventListener('change', (e) => {
          const mode = e.target.value;
          this.setAllocationMode(mode);
        });
      });
    },

    /**
     * Handle allocation target percentage change
     */
    handleAllocationChange(event) {
      const input = event.target;
      if (!input.dataset.assetClass) return;

      const value = parseFloat(input.value) || 0;

      // Validate percentage is 0-100
      if (value < 0) {
        input.value = 0;
      } else if (value > 100) {
        input.value = 100;
      }

      // Rebalance other allocations if needed
      this.rebalanceAllocations();
    },

    /**
     * Rebalance allocation percentages to sum to 100%
     */
    rebalanceAllocations() {
      const table = document.querySelector(this.selectors.allocationTable);
      if (!table) return;

      const inputs = table.querySelectorAll('[data-asset-class]');
      let total = 0;
      const values = [];

      inputs.forEach(input => {
        const value = parseFloat(input.value) || 0;
        values.push(value);
        total += value;
      });

      if (total > 0 && total !== 100) {
        // Normalize to 100%
        const scale = 100 / total;
        inputs.forEach((input, idx) => {
          input.value = Math.round(values[idx] * scale);
        });
      }
    },

    /**
     * Handle account balance change
     */
    handleAccountBalanceChange(event) {
      const field = event.target;
      const value = parseFloat(field.value) || 0;

      if (value < 0) {
        field.value = 0;
      }

      this.scheduleRefresh();
    },

    /**
     * Set allocation editing mode (optimizer vs. user-defined)
     */
    setAllocationMode(mode) {
      const table = document.querySelector(this.selectors.allocationTable);
      if (!table) return;

      if (mode === 'optimizer') {
        table.classList.add('mode-optimizer');
        table.classList.remove('mode-manual');
      } else {
        table.classList.add('mode-manual');
        table.classList.remove('mode-optimizer');
      }
    },

    /**
     * Delete a holding from portfolio
     */
    deleteHolding(holdingId) {
      if (!confirm('Remove this holding from your portfolio?')) return;

      const row = document.querySelector(`[data-holding-id="${holdingId}"]`);
      if (row) {
        row.remove();
        this.updatePortfolioTotals();
        this.scheduleRefresh();
      }
    },

    /**
     * Open detailed editor for holding
     */
    editHoldingDetails(holdingId) {
      if (window.editHoldingDetails) {
        window.editHoldingDetails(holdingId);
      }
    },

    /**
     * Export holding data
     */
    exportHolding(holdingId) {
      const row = document.querySelector(`[data-holding-id="${holdingId}"]`);
      if (!row) return;

      const data = {
        account: row.dataset.account,
        ticker: row.dataset.ticker,
        shares: row.querySelector('[data-field="shares"]')?.value,
        price: row.querySelector('[data-field="price"]')?.value,
        costBasis: row.querySelector('[data-field="cost_basis"]')?.value,
      };

      console.log('Export holding:', data);
    },

    /**
     * Schedule refresh with debounce
     */
    scheduleRefresh() {
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
     * Get total portfolio value
     */
    getTotalPortfolioValue() {
      const display = document.querySelector('[data-metric="portfolio_total"]');
      if (!display) return 0;

      const text = display.textContent.replace(/[^0-9.-]/g, '');
      return parseFloat(text) || 0;
    },

    /**
     * Get allocation by account type
     */
    getAllocationByType() {
      const result = {};
      Object.keys(this.accountTypes).forEach(type => {
        const display = document.querySelector(`[data-metric="total_${type}"]`);
        if (display) {
          const text = display.textContent.replace(/[^0-9.-]/g, '');
          result[type] = parseFloat(text) || 0;
        }
      });
      return result;
    },
  };

  // Export for use
  if (typeof window !== 'undefined') {
    window.DashboardAssetsModule = AssetsModule;
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = AssetsModule;
  }

})();

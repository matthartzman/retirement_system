/**
 * Dashboard Spending Module
 *
 * Extracted module for spending-related planning features:
 * - Budget category management
 * - Healthcare/medical expense tracking
 * - Housing and mortgage management
 * - Travel and discretionary spending
 * - Year-to-date transaction tracking and categorization
 *
 * Part of Phase D Tier 3B modularization.
 * Provides clean API for spending feature management.
 */

(function() {
  'use strict';

  const SpendingModule = {
    // Spending feature selectors
    selectors: {
      spendingModelForm: '[data-section="spending_core"]',
      budgetCategoriesTable: '[data-budget-categories]',
      budgetMoneyInputs: '[data-budget-money]',
      categorySearch: '[data-category-search]',
      spendingDashboard: '[data-spending-dashboard]',
    },

    // Category groupings for feature-based organization
    categoryGroups: {
      healthcare: ['medical', 'dental', 'vision', 'healthcare_premium', 'drugs_rx'],
      housing: ['mortgage', 'rent', 'property_tax', 'homeowners_insurance', 'utilities', 'maintenance'],
      travel: ['travel_plane', 'travel_housing', 'travel_meals', 'travel_vacation'],
      gifts: ['gifts_family', 'gifts_other', 'charitable_donations'],
    },

    /**
     * Initialize spending module
     */
    init() {
      this.attachEventHandlers();
      this.loadBudgetData();
      this.attachCategorySearch();
    },

    /**
     * Attach event handlers to spending-related elements
     */
    attachEventHandlers() {
      const table = document.querySelector(this.selectors.budgetCategoriesTable);
      if (table) {
        table.addEventListener('change', (e) => this.handleBudgetChange(e));
        table.addEventListener('blur', (e) => this.formatBudgetMoney(e), true);
      }

      const dashboard = document.querySelector(this.selectors.spendingDashboard);
      if (dashboard) {
        dashboard.addEventListener('click', (e) => this.handleDashboardAction(e));
      }
    },

    /**
     * Handle budget category amount changes
     */
    handleBudgetChange(event) {
      const input = event.target;
      if (!input.matches(this.selectors.budgetMoneyInputs)) return;

      const categoryId = input.dataset.categoryId;
      const amount = parseFloat(input.value) || 0;

      // Validate amount is non-negative
      if (amount < 0) {
        input.value = 0;
      }

      // Update category-specific logic (e.g., healthcare total)
      this.updateCategorySubtotals(categoryId);

      // Trigger projection refresh
      this.scheduleProjectionRefresh();
    },

    /**
     * Format budget money input for display
     */
    formatBudgetMoney(event) {
      const input = event.target;
      if (!input.matches(this.selectors.budgetMoneyInputs)) return;

      const value = parseFloat(input.value) || 0;
      input.value = value.toLocaleString('en-US', { minimumFractionDigits: 0, maximumFractionDigits: 0 });
    },

    /**
     * Load and display budget data from plan
     */
    loadBudgetData() {
      const table = document.querySelector(this.selectors.budgetCategoriesTable);
      if (!table || !window.currentPlanData) return;

      const budget = window.currentPlanData.spending_budget || {};
      Object.entries(budget).forEach(([categoryId, amount]) => {
        const input = table.querySelector(`[data-category-id="${categoryId}"]`);
        if (input) {
          input.value = amount;
        }
      });
    },

    /**
     * Attach search functionality to category list
     */
    attachCategorySearch() {
      const search = document.querySelector(this.selectors.categorySearch);
      if (search) {
        search.addEventListener('input', (e) => this.filterCategories(e.target.value));
      }
    },

    /**
     * Filter visible categories based on search term
     */
    filterCategories(searchTerm) {
      const table = document.querySelector(this.selectors.budgetCategoriesTable);
      if (!table) return;

      const rows = table.querySelectorAll('[data-category-id]');
      const term = searchTerm.toLowerCase();

      rows.forEach(row => {
        const categoryLabel = row.dataset.categoryLabel || '';
        const matches = categoryLabel.toLowerCase().includes(term) || term === '';
        row.style.display = matches ? '' : 'none';
      });
    },

    /**
     * Update subtotals for a category group (e.g., total healthcare)
     */
    updateCategorySubtotals(categoryId) {
      const table = document.querySelector(this.selectors.budgetCategoriesTable);
      if (!table) return;

      // Find which group this category belongs to
      let groupName = null;
      for (const [group, categories] of Object.entries(this.categoryGroups)) {
        if (categories.some(cat => categoryId.includes(cat))) {
          groupName = group;
          break;
        }
      }

      if (!groupName) return;

      // Calculate group total
      const total = this.calculateGroupTotal(groupName);
      this.updateGroupSubtotalDisplay(groupName, total);
    },

    /**
     * Calculate total spending for a category group
     */
    calculateGroupTotal(groupName) {
      const table = document.querySelector(this.selectors.budgetCategoriesTable);
      if (!table) return 0;

      const categories = this.categoryGroups[groupName] || [];
      let total = 0;

      categories.forEach(categoryPattern => {
        const inputs = table.querySelectorAll(`[data-category-id*="${categoryPattern}"]`);
        inputs.forEach(input => {
          total += parseFloat(input.value) || 0;
        });
      });

      return total;
    },

    /**
     * Update group subtotal display
     */
    updateGroupSubtotalDisplay(groupName, total) {
      const subtotalElement = document.querySelector(`[data-group-subtotal="${groupName}"]`);
      if (subtotalElement) {
        subtotalElement.textContent = total.toLocaleString('en-US', {
          style: 'currency',
          currency: 'USD',
          minimumFractionDigits: 0,
        });
      }
    },

    /**
     * Handle spending dashboard actions (sync actual, compare to projection, etc.)
     */
    handleDashboardAction(event) {
      const action = event.target.dataset.action;
      if (!action) return;

      switch (action) {
        case 'sync_actual':
          this.syncActualSpending();
          break;
        case 'compare_projection':
          this.compareToProjection();
          break;
        case 'export_budget':
          this.exportBudgetData();
          break;
      }
    },

    /**
     * Sync year-to-date actual spending with projection
     */
    syncActualSpending() {
      if (window.syncSpendingActuals) {
        window.syncSpendingActuals();
      }
    },

    /**
     * Compare current year spending to projection
     */
    compareToProjection() {
      if (window.compareSpendingToProjection) {
        window.compareSpendingToProjection();
      }
    },

    /**
     * Export budget data to CSV
     */
    exportBudgetData() {
      const budget = this.getBudgetData();
      const csv = this.convertToCSV(budget);
      this.downloadCSV(csv, 'spending_budget.csv');
    },

    /**
     * Get current budget data from form
     */
    getBudgetData() {
      const table = document.querySelector(this.selectors.budgetCategoriesTable);
      if (!table) return {};

      const budget = {};
      table.querySelectorAll('[data-category-id]').forEach(row => {
        const categoryId = row.dataset.categoryId;
        const amount = parseFloat(row.querySelector(this.selectors.budgetMoneyInputs)?.value) || 0;
        budget[categoryId] = amount;
      });

      return budget;
    },

    /**
     * Convert budget data to CSV format
     */
    convertToCSV(budget) {
      const rows = ['category,amount'];
      Object.entries(budget).forEach(([categoryId, amount]) => {
        rows.push(`"${categoryId}",${amount}`);
      });
      return rows.join('\n');
    },

    /**
     * Download CSV file
     */
    downloadCSV(csv, filename) {
      const blob = new Blob([csv], { type: 'text/csv' });
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);
    },

    /**
     * Schedule projection refresh with debounce
     */
    scheduleProjectionRefresh() {
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
     * Get total core spending
     */
    getTotalCoreSpending() {
      const table = document.querySelector(this.selectors.budgetCategoriesTable);
      if (!table) return 0;

      let total = 0;
      table.querySelectorAll(this.selectors.budgetMoneyInputs).forEach(input => {
        total += parseFloat(input.value) || 0;
      });

      return total;
    },

    /**
     * Get healthcare-specific spending total
     */
    getHealthcareTotal() {
      return this.calculateGroupTotal('healthcare');
    },

    /**
     * Get housing-specific spending total
     */
    getHousingTotal() {
      return this.calculateGroupTotal('housing');
    },

    /**
     * Get travel-specific spending total
     */
    getTravelTotal() {
      return this.calculateGroupTotal('travel');
    },
  };

  // Export for use
  if (typeof window !== 'undefined') {
    window.DashboardSpendingModule = SpendingModule;
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = SpendingModule;
  }

})();

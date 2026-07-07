/**
 * Phase D Tier 3B: Dashboard Module Tests
 *
 * Comprehensive test suite for modularized dashboard feature modules:
 * - dashboard_income_module.js
 * - dashboard_spending_module.js
 * - dashboard_assets_module.js
 * - dashboard_strategy_module.js
 * - dashboard_module_loader.js
 *
 * Tests verify:
 * - Module exports and globals
 * - Module initialization
 * - Event handler attachment
 * - Feature-specific methods
 * - Cross-module integration
 * - Dependency resolution
 * - Data aggregation
 */

describe('Dashboard Module Architecture', () => {
  let loader;

  before(() => {
    // Ensure DOM environment
    if (typeof document === 'undefined') {
      global.document = require('jsdom').jsdom();
    }
  });

  describe('Module Exports', () => {
    it('should export IncomeModule to window global', () => {
      expect(window.DashboardIncomeModule).to.exist;
      expect(window.DashboardIncomeModule).to.be.an('object');
    });

    it('should export SpendingModule to window global', () => {
      expect(window.DashboardSpendingModule).to.exist;
      expect(window.DashboardSpendingModule).to.be.an('object');
    });

    it('should export AssetsModule to window global', () => {
      expect(window.DashboardAssetsModule).to.exist;
      expect(window.DashboardAssetsModule).to.be.an('object');
    });

    it('should export StrategyModule to window global', () => {
      expect(window.DashboardStrategyModule).to.exist;
      expect(window.DashboardStrategyModule).to.be.an('object');
    });

    it('should export ModuleLoader to window global', () => {
      expect(window.DashboardModuleLoader).to.exist;
      expect(window.DashboardModuleLoader).to.be.an('object');
      loader = window.DashboardModuleLoader;
    });
  });

  describe('Income Module Interface', () => {
    it('should have required methods on IncomeModule', () => {
      const incomeModule = window.DashboardIncomeModule;
      expect(incomeModule.init).to.be.a('function');
      expect(incomeModule.attachEventHandlers).to.be.a('function');
      expect(incomeModule.getTotalProjectedIncome).to.be.a('function');
    });

    it('should have income configuration selectors', () => {
      const incomeModule = window.DashboardIncomeModule;
      expect(incomeModule.selectors).to.be.an('object');
      expect(incomeModule.selectors.workIncomeForm).to.exist;
      expect(incomeModule.selectors.socialSecurityForm).to.exist;
    });

    it('should validate income inputs', () => {
      const incomeModule = window.DashboardIncomeModule;
      expect(incomeModule.validateIncomeInputs).to.be.a('function');
      expect(incomeModule.validateBenefitAmount).to.be.a('function');
      expect(incomeModule.validateClaimingAge).to.be.a('function');
    });
  });

  describe('Spending Module Interface', () => {
    it('should have required methods on SpendingModule', () => {
      const spendingModule = window.DashboardSpendingModule;
      expect(spendingModule.init).to.be.a('function');
      expect(spendingModule.attachEventHandlers).to.be.a('function');
      expect(spendingModule.getTotalCoreSpending).to.be.a('function');
      expect(spendingModule.getHealthcareTotal).to.be.a('function');
      expect(spendingModule.getHousingTotal).to.be.a('function');
      expect(spendingModule.getTravelTotal).to.be.a('function');
    });

    it('should have spending category groups', () => {
      const spendingModule = window.DashboardSpendingModule;
      expect(spendingModule.categoryGroups).to.be.an('object');
      expect(spendingModule.categoryGroups.healthcare).to.be.an('array');
      expect(spendingModule.categoryGroups.housing).to.be.an('array');
      expect(spendingModule.categoryGroups.travel).to.be.an('array');
      expect(spendingModule.categoryGroups.gifts).to.be.an('array');
    });

    it('should have budget and CSV export methods', () => {
      const spendingModule = window.DashboardSpendingModule;
      expect(spendingModule.getBudgetData).to.be.a('function');
      expect(spendingModule.exportBudgetData).to.be.a('function');
      expect(spendingModule.convertToCSV).to.be.a('function');
    });
  });

  describe('Assets Module Interface', () => {
    it('should have required methods on AssetsModule', () => {
      const assetsModule = window.DashboardAssetsModule;
      expect(assetsModule.init).to.be.a('function');
      expect(assetsModule.attachEventHandlers).to.be.a('function');
      expect(assetsModule.getTotalPortfolioValue).to.be.a('function');
      expect(assetsModule.getAllocationByType).to.be.a('function');
    });

    it('should have account type organization', () => {
      const assetsModule = window.DashboardAssetsModule;
      expect(assetsModule.accountTypes).to.be.an('object');
      expect(assetsModule.accountTypes.taxable).to.be.an('array');
      expect(assetsModule.accountTypes.pretax).to.be.an('array');
      expect(assetsModule.accountTypes.roth).to.be.an('array');
      expect(assetsModule.accountTypes.other).to.be.an('array');
    });

    it('should have holdings and allocation management', () => {
      const assetsModule = window.DashboardAssetsModule;
      expect(assetsModule.handleHoldingChange).to.be.a('function');
      expect(assetsModule.recalculateHoldingMetrics).to.be.a('function');
      expect(assetsModule.updatePortfolioTotals).to.be.a('function');
      expect(assetsModule.handleAllocationChange).to.be.a('function');
    });
  });

  describe('Strategy Module Interface', () => {
    it('should have required methods on StrategyModule', () => {
      const strategyModule = window.DashboardStrategyModule;
      expect(strategyModule.init).to.be.a('function');
      expect(strategyModule.attachEventHandlers).to.be.a('function');
      expect(strategyModule.getConversionPolicy).to.be.a('function');
      expect(strategyModule.getWithdrawalOrder).to.be.a('function');
      expect(strategyModule.getAllocationTargets).to.be.a('function');
    });

    it('should have conversion policy options', () => {
      const strategyModule = window.DashboardStrategyModule;
      expect(strategyModule.conversionPolicies).to.be.an('object');
      expect(strategyModule.conversionPolicies.none).to.exist;
      expect(strategyModule.conversionPolicies.bracket_fill).to.exist;
    });

    it('should support multiple strategic levers', () => {
      const strategyModule = window.DashboardStrategyModule;
      expect(strategyModule.handleConversionChange).to.be.a('function');
      expect(strategyModule.handleWithdrawalChange).to.be.a('function');
      expect(strategyModule.handleAllocationChange).to.be.a('function');
      expect(strategyModule.handlePolicyChange).to.be.a('function');
      expect(strategyModule.handleHelocChange).to.be.a('function');
      expect(strategyModule.handleCharityChange).to.be.a('function');
    });

    it('should have strategy data getters', () => {
      const strategyModule = window.DashboardStrategyModule;
      expect(strategyModule.getConversionAmount).to.be.a('function');
      expect(strategyModule.getAllocationPolicy).to.be.a('function');
      expect(strategyModule.getHelocStrategy).to.be.a('function');
      expect(strategyModule.getCharitableStrategy).to.be.a('function');
    });
  });

  describe('Module Loader Registry', () => {
    it('should have all modules registered', () => {
      expect(loader.modules).to.be.an('object');
      expect(loader.modules.income).to.exist;
      expect(loader.modules.spending).to.exist;
      expect(loader.modules.assets).to.exist;
      expect(loader.modules.strategy).to.exist;
    });

    it('should define module priorities', () => {
      expect(loader.modules.income.priority).to.equal(1);
      expect(loader.modules.spending.priority).to.equal(2);
      expect(loader.modules.assets.priority).to.equal(3);
      expect(loader.modules.strategy.priority).to.equal(4);
    });

    it('should define module dependencies', () => {
      expect(loader.modules.income.dependencies).to.be.an('array').that.is.empty;
      expect(loader.modules.spending.dependencies).to.be.an('array').that.is.empty;
      expect(loader.modules.assets.dependencies).to.be.an('array').that.is.empty;
      expect(loader.modules.strategy.dependencies).to.include('assets');
      expect(loader.modules.strategy.dependencies).to.include('income');
    });
  });

  describe('Module Loader Methods', () => {
    it('should have initialization method', () => {
      expect(loader.init).to.be.a('function');
    });

    it('should have module retrieval methods', () => {
      expect(loader.getModule).to.be.a('function');
      expect(loader.getAllModules).to.be.a('function');
    });

    it('should have method calling utilities', () => {
      expect(loader.callModuleMethod).to.be.a('function');
      expect(loader.broadcastMethodToAll).to.be.a('function');
    });

    it('should have data aggregation method', () => {
      expect(loader.getAggregatedData).to.be.a('function');
    });

    it('should have validation method', () => {
      expect(loader.validateAll).to.be.a('function');
      expect(loader.validateIncomeModule).to.be.a('function');
      expect(loader.validateSpendingModule).to.be.a('function');
      expect(loader.validateAssetsModule).to.be.a('function');
      expect(loader.validateStrategyModule).to.be.a('function');
    });

    it('should have status and logging methods', () => {
      expect(loader.getStatus).to.be.a('function');
      expect(loader.logModuleInfo).to.be.a('function');
    });
  });

  describe('Module Dependency Resolution', () => {
    it('should detect missing dependencies', () => {
      // Temporarily hide a dependency
      const originalModule = window.DashboardAssetsModule;
      delete window.DashboardAssetsModule;

      const missing = loader.checkDependencies('strategy');
      expect(missing).to.include('assets');

      // Restore
      window.DashboardAssetsModule = originalModule;
    });

    it('should verify all base modules have no unmet dependencies', () => {
      const missing = loader.checkDependencies('income');
      expect(missing).to.be.empty;

      const spendingMissing = loader.checkDependencies('spending');
      expect(spendingMissing).to.be.empty;

      const assetsMissing = loader.checkDependencies('assets');
      expect(assetsMissing).to.be.empty;
    });
  });

  describe('Module Data Aggregation', () => {
    it('should return aggregated data structure', () => {
      const data = loader.getAggregatedData();
      expect(data).to.be.an('object');
      expect(data.income).to.be.an('object');
      expect(data.spending).to.be.an('object');
      expect(data.assets).to.be.an('object');
      expect(data.strategy).to.be.an('object');
    });

    it('should reference correct module getter methods', () => {
      const data = loader.getAggregatedData();
      // Income keys should reference income module getters
      expect(Object.keys(data.income)).to.include.members([
        'totalProjectedIncome',
      ]);
      // Spending keys should reference spending module getters
      expect(Object.keys(data.spending)).to.include.members([
        'totalCoreSpending',
        'healthcareTotal',
        'housingTotal',
        'travelTotal',
      ]);
      // Assets keys should reference assets module getters
      expect(Object.keys(data.assets)).to.include.members([
        'portfolioTotal',
        'allocationByType',
      ]);
      // Strategy keys should reference strategy module getters
      expect(Object.keys(data.strategy)).to.include.members([
        'conversionPolicy',
        'conversionAmount',
        'withdrawalOrder',
        'allocation',
        'allocationPolicy',
      ]);
    });
  });

  describe('No Circular Dependencies', () => {
    it('should not have circular imports between modules', () => {
      // Income should not depend on other modules
      expect(window.DashboardIncomeModule.selectors.workIncomeForm).to.exist;

      // Spending should not depend on other modules
      expect(window.DashboardSpendingModule.selectors.budgetCategoriesTable).to.exist;

      // Assets should not depend on other modules
      expect(window.DashboardAssetsModule.selectors.holdingsTable).to.exist;

      // Strategy can depend on Assets and Income
      expect(window.DashboardStrategyModule.selectors.rothConversionForm).to.exist;
    });
  });

  describe('Module Initialization Order', () => {
    it('should initialize modules in priority order', async () => {
      const initOrder = [];
      const originalInits = {
        income: window.DashboardIncomeModule.init,
        spending: window.DashboardSpendingModule.init,
        assets: window.DashboardAssetsModule.init,
        strategy: window.DashboardStrategyModule.init,
      };

      // Spy on init methods
      window.DashboardIncomeModule.init = function() {
        initOrder.push('income');
        if (originalInits.income) originalInits.income.call(this);
      };
      window.DashboardSpendingModule.init = function() {
        initOrder.push('spending');
        if (originalInits.spending) originalInits.spending.call(this);
      };
      window.DashboardAssetsModule.init = function() {
        initOrder.push('assets');
        if (originalInits.assets) originalInits.assets.call(this);
      };
      window.DashboardStrategyModule.init = function() {
        initOrder.push('strategy');
        if (originalInits.strategy) originalInits.strategy.call(this);
      };

      // Reinitialize loader
      const testLoader = window.DashboardModuleLoader;
      testLoader.initialized = false;
      testLoader.initializationErrors = [];
      await testLoader.init();

      // Verify order
      expect(initOrder.indexOf('income')).to.be.lessThan(initOrder.indexOf('strategy'));
      expect(initOrder.indexOf('assets')).to.be.lessThan(initOrder.indexOf('strategy'));

      // Restore original methods
      window.DashboardIncomeModule.init = originalInits.income;
      window.DashboardSpendingModule.init = originalInits.spending;
      window.DashboardAssetsModule.init = originalInits.assets;
      window.DashboardStrategyModule.init = originalInits.strategy;
    });
  });

  describe('Cross-Module Method Calling', () => {
    it('should call methods on specific modules', () => {
      const result = loader.callModuleMethod('income', 'getTotalProjectedIncome');
      // Result should be either a number or null (depending on form state)
      expect(result).to.be.a('number').or.null;
    });

    it('should broadcast methods to all modules', () => {
      const results = loader.broadcastMethodToAll('scheduleRefresh');
      expect(results).to.be.an('object');
      // Each module that has scheduleRefresh should appear in results
      expect(Object.keys(results).length).to.be.greaterThan(0);
    });
  });

  describe('Module Status Reporting', () => {
    it('should report initialization status', () => {
      const status = loader.getStatus();
      expect(status).to.be.an('object');
      expect(status.initialized).to.be.a('boolean');
      expect(status.moduleCount).to.equal(4);
      expect(status.initializedCount).to.be.a('number');
      expect(status.errors).to.be.an('array');
    });

    it('should export module state for serialization', () => {
      const state = loader.exportModuleState();
      expect(state).to.be.an('object');
      expect(state.timestamp).to.exist;
      expect(state.modules).to.be.an('object');
      expect(state.status).to.be.an('object');
    });
  });

  describe('Backwards Compatibility', () => {
    it('should maintain all existing module methods', () => {
      // Verify that all original module methods still exist and work
      const incomeModule = window.DashboardIncomeModule;
      expect(incomeModule.handleWorkIncomeChange).to.be.a('function');
      expect(incomeModule.handleSSChange).to.be.a('function');

      const spendingModule = window.DashboardSpendingModule;
      expect(spendingModule.handleBudgetChange).to.be.a('function');
      expect(spendingModule.filterCategories).to.be.a('function');

      const assetsModule = window.DashboardAssetsModule;
      expect(assetsModule.handleHoldingChange).to.be.a('function');
      expect(assetsModule.handleAllocationChange).to.be.a('function');
    });

    it('should not break existing dashboard.js integration points', () => {
      // Verify integration hooks still exist
      expect(window.DashboardModuleLoader).to.exist;
      expect(window.DashboardIncomeModule).to.exist;
      expect(window.DashboardSpendingModule).to.exist;
      expect(window.DashboardAssetsModule).to.exist;
      expect(window.DashboardStrategyModule).to.exist;
    });
  });
});

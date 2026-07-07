/**
 * Dashboard Module Loader
 *
 * Manages initialization, dependency resolution, and lifecycle of all
 * modularized dashboard feature modules.
 *
 * Part of Phase D Tier 3B modularization.
 * Provides centralized module coordination and integration.
 */

(function() {
  'use strict';

  const ModuleLoader = {
    // Module registry with initialization order and dependencies
    modules: {
      income: {
        name: 'Income',
        instance: null,
        dependencies: [],
        priority: 1,
        getModule: () => window.DashboardIncomeModule,
      },
      spending: {
        name: 'Spending',
        instance: null,
        dependencies: [],
        priority: 2,
        getModule: () => window.DashboardSpendingModule,
      },
      assets: {
        name: 'Assets',
        instance: null,
        dependencies: [],
        priority: 3,
        getModule: () => window.DashboardAssetsModule,
      },
      strategy: {
        name: 'Strategy',
        instance: null,
        dependencies: ['assets', 'income'],
        priority: 4,
        getModule: () => window.DashboardStrategyModule,
      },
    },

    // Initialization state
    initialized: false,
    initializationErrors: [],

    /**
     * Initialize all modules in dependency order
     */
    async init() {
      if (this.initialized) {
        console.warn('Dashboard modules already initialized');
        return true;
      }

      console.log('Initializing dashboard modules...');

      try {
        // Sort modules by priority
        const sortedModules = Object.entries(this.modules)
          .sort((a, b) => a[1].priority - b[1].priority);

        // Initialize each module with dependency checking
        for (const [key, moduleConfig] of sortedModules) {
          try {
            await this.initializeModule(key, moduleConfig);
          } catch (error) {
            this.initializationErrors.push({
              module: key,
              error: error.message || error,
            });
            console.error(`Failed to initialize ${key} module:`, error);
          }
        }

        this.initialized = true;

        if (this.initializationErrors.length === 0) {
          console.log('All dashboard modules initialized successfully');
          return true;
        } else {
          console.warn(`${this.initializationErrors.length} module(s) failed to initialize`);
          return false;
        }
      } catch (error) {
        console.error('Module loader initialization failed:', error);
        this.initialized = false;
        return false;
      }
    },

    /**
     * Initialize a single module with dependency validation
     */
    async initializeModule(moduleKey, moduleConfig) {
      // Check dependencies
      const missingDeps = this.checkDependencies(moduleKey);
      if (missingDeps.length > 0) {
        throw new Error(`Missing dependencies: ${missingDeps.join(', ')}`);
      }

      // Get module instance
      const ModuleClass = moduleConfig.getModule();
      if (!ModuleClass) {
        throw new Error(`Module class not found for ${moduleKey}`);
      }

      // Store reference
      this.modules[moduleKey].instance = ModuleClass;

      // Call init method if it exists
      if (typeof ModuleClass.init === 'function') {
        ModuleClass.init();
      }

      console.log(`Initialized ${moduleConfig.name} module (${moduleKey})`);
    },

    /**
     * Check if all dependencies for a module are available
     */
    checkDependencies(moduleKey) {
      const moduleConfig = this.modules[moduleKey];
      if (!moduleConfig || !moduleConfig.dependencies) {
        return [];
      }

      const missing = [];
      for (const depKey of moduleConfig.dependencies) {
        const depConfig = this.modules[depKey];
        if (!depConfig) {
          missing.push(depKey);
          continue;
        }

        const depModule = depConfig.getModule();
        if (!depModule) {
          missing.push(depKey);
        }
      }

      return missing;
    },

    /**
     * Get a module instance by key
     */
    getModule(moduleKey) {
      const moduleConfig = this.modules[moduleKey];
      if (!moduleConfig) {
        console.warn(`Module ${moduleKey} not found in registry`);
        return null;
      }

      return moduleConfig.instance || moduleConfig.getModule();
    },

    /**
     * Get all initialized modules
     */
    getAllModules() {
      const result = {};
      Object.entries(this.modules).forEach(([key, config]) => {
        if (config.instance) {
          result[key] = config.instance;
        }
      });
      return result;
    },

    /**
     * Call a method on a specific module
     */
    callModuleMethod(moduleKey, methodName, ...args) {
      const module = this.getModule(moduleKey);
      if (!module) {
        console.warn(`Module ${moduleKey} not found`);
        return null;
      }

      if (typeof module[methodName] !== 'function') {
        console.warn(`Method ${methodName} not found on module ${moduleKey}`);
        return null;
      }

      return module[methodName](...args);
    },

    /**
     * Broadcast a method call to all modules that have it
     */
    broadcastMethodToAll(methodName, ...args) {
      const results = {};
      Object.entries(this.modules).forEach(([key, config]) => {
        const module = config.instance || config.getModule();
        if (module && typeof module[methodName] === 'function') {
          try {
            results[key] = module[methodName](...args);
          } catch (error) {
            console.error(`Error calling ${methodName} on ${key} module:`, error);
            results[key] = null;
          }
        }
      });
      return results;
    },

    /**
     * Get aggregated data from all modules
     */
    getAggregatedData() {
      const data = {
        income: {},
        spending: {},
        assets: {},
        strategy: {},
      };

      // Income data
      const incomeModule = this.getModule('income');
      if (incomeModule) {
        data.income.totalProjectedIncome = incomeModule.getTotalProjectedIncome?.();
      }

      // Spending data
      const spendingModule = this.getModule('spending');
      if (spendingModule) {
        data.spending.totalCoreSpending = spendingModule.getTotalCoreSpending?.();
        data.spending.healthcareTotal = spendingModule.getHealthcareTotal?.();
        data.spending.housingTotal = spendingModule.getHousingTotal?.();
        data.spending.travelTotal = spendingModule.getTravelTotal?.();
      }

      // Assets data
      const assetsModule = this.getModule('assets');
      if (assetsModule) {
        data.assets.portfolioTotal = assetsModule.getTotalPortfolioValue?.();
        data.assets.allocationByType = assetsModule.getAllocationByType?.();
      }

      // Strategy data
      const strategyModule = this.getModule('strategy');
      if (strategyModule) {
        data.strategy.conversionPolicy = strategyModule.getConversionPolicy?.();
        data.strategy.conversionAmount = strategyModule.getConversionAmount?.();
        data.strategy.withdrawalOrder = strategyModule.getWithdrawalOrder?.();
        data.strategy.allocation = strategyModule.getAllocationTargets?.();
        data.strategy.allocationPolicy = strategyModule.getAllocationPolicy?.();
      }

      return data;
    },

    /**
     * Refresh all modules (call refresh/update methods)
     */
    refreshAll() {
      console.log('Refreshing all dashboard modules...');
      const results = this.broadcastMethodToAll('scheduleRefresh');
      return results;
    },

    /**
     * Validate all modules' current state
     */
    validateAll() {
      const validation = {
        isValid: true,
        errors: [],
        warnings: [],
      };

      // Validate income
      const incomeModule = this.getModule('income');
      if (incomeModule) {
        const errors = this.validateIncomeModule();
        if (errors.length > 0) {
          validation.isValid = false;
          validation.errors.push(...errors);
        }
      }

      // Validate spending
      const spendingModule = this.getModule('spending');
      if (spendingModule) {
        const errors = this.validateSpendingModule();
        if (errors.length > 0) {
          validation.isValid = false;
          validation.errors.push(...errors);
        }
      }

      // Validate assets
      const assetsModule = this.getModule('assets');
      if (assetsModule) {
        const errors = this.validateAssetsModule();
        if (errors.length > 0) {
          validation.isValid = false;
          validation.errors.push(...errors);
        }
      }

      // Validate strategy
      const strategyModule = this.getModule('strategy');
      if (strategyModule) {
        const errors = this.validateStrategyModule();
        if (errors.length > 0) {
          validation.isValid = false;
          validation.errors.push(...errors);
        }
      }

      return validation;
    },

    /**
     * Validate income module state
     */
    validateIncomeModule() {
      const errors = [];
      const form = document.querySelector('[data-section="income_work"]');
      if (!form) return errors;

      const inputs = form.querySelectorAll('input[type="number"]');
      inputs.forEach(input => {
        if (isNaN(input.value)) {
          errors.push(`Invalid income value: ${input.name}`);
        }
      });

      return errors;
    },

    /**
     * Validate spending module state
     */
    validateSpendingModule() {
      const errors = [];
      const form = document.querySelector('[data-section="spending_core"]');
      if (!form) return errors;

      const inputs = form.querySelectorAll('input[type="number"]');
      inputs.forEach(input => {
        const value = parseFloat(input.value) || 0;
        if (value < 0) {
          errors.push(`Negative spending amount: ${input.name}`);
        }
      });

      return errors;
    },

    /**
     * Validate assets module state
     */
    validateAssetsModule() {
      const errors = [];
      const form = document.querySelector('[data-holdings-table]');
      if (!form) return errors;

      const rows = form.querySelectorAll('[data-holding-id]');
      rows.forEach(row => {
        const shares = parseFloat(row.querySelector('[data-field="shares"]')?.value) || 0;
        const price = parseFloat(row.querySelector('[data-field="price"]')?.value) || 0;
        if (shares < 0 || price < 0) {
          errors.push(`Invalid holding values in ${row.dataset.ticker || 'unknown'}`);
        }
      });

      return errors;
    },

    /**
     * Validate strategy module state
     */
    validateStrategyModule() {
      const errors = [];
      const form = document.querySelector('[data-section="allocation_assets"]');
      if (!form) return errors;

      let total = 0;
      const inputs = form.querySelectorAll('[data-asset-class]');
      inputs.forEach(input => {
        const value = parseFloat(input.value) || 0;
        if (value < 0 || value > 100) {
          errors.push(`Invalid allocation percentage: ${input.dataset.assetClass}`);
        }
        total += value;
      });

      // Warn if not 100% (but don't fail)
      if (Math.abs(total - 100) > 1) {
        console.warn(`Allocation total is ${total}%, expected ~100%`);
      }

      return errors;
    },

    /**
     * Get initialization status
     */
    getStatus() {
      return {
        initialized: this.initialized,
        moduleCount: Object.keys(this.modules).length,
        initializedCount: Object.values(this.modules).filter(m => m.instance).length,
        errors: this.initializationErrors,
      };
    },

    /**
     * Export module data for serialization
     */
    exportModuleState() {
      const state = {};
      const data = this.getAggregatedData();

      state.timestamp = new Date().toISOString();
      state.modules = data;
      state.status = this.getStatus();

      return state;
    },

    /**
     * Log module information for debugging
     */
    logModuleInfo() {
      console.group('Dashboard Module Loader Status');
      console.log('Initialized:', this.initialized);
      console.log('Modules:');
      Object.entries(this.modules).forEach(([key, config]) => {
        const loaded = !!config.instance;
        const deps = config.dependencies.length > 0 ? `(depends on: ${config.dependencies.join(', ')})` : '';
        console.log(`  - ${key} (${config.name}): ${loaded ? 'LOADED' : 'NOT LOADED'} ${deps}`);
      });
      if (this.initializationErrors.length > 0) {
        console.group('Initialization Errors');
        this.initializationErrors.forEach(e => {
          console.error(`${e.module}: ${e.error}`);
        });
        console.groupEnd();
      }
      console.groupEnd();
    },
  };

  // Export for use
  if (typeof window !== 'undefined') {
    window.DashboardModuleLoader = ModuleLoader;
  }

  if (typeof module !== 'undefined' && module.exports) {
    module.exports = ModuleLoader;
  }

})();

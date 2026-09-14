# Project File Inventory by Folder

**Generated:** 2026-09-09  
**Total Files:** 2,990 | **Total Lines of Code:** ~478,000 (text files)

---

## FOLDER SUMMARY TABLE

| Folder | Files | Size | Text Files | Lines | Purpose |
|--------|-------|------|-----------|-------|---------|
| saved_plans/ | 33 | 1.1 GB | 15 | 225 | User plan snapshots and cached results |
| local_state/ | 472 | 940 MB | 56 | 2.5K | SQLite databases and runtime state |
| output/ | 16 | 74 MB | 14 | 19.6K | Generated reports and snapshots |
| tests/ | 1,853 | 22 MB | 423 | 84.9K | Pytest test suite with fixtures |
| src/ | 567 | 12.5 MB | 163 | 60.8K | Python application core code |
| frontend/ | 44 | 1.6 MB | 41 | 30.7K | Browser UI assets and code |
| documentation/ | 63 | 1.5 MB | 61 | 16.9K | Project documentation and specs |
| input/ | 85 | 1.2 MB | 76 | 14K | Plan data files and configuration |
| tools/ | 81 | 0.7 MB | 55 | 14K | Build and maintenance scripts |
| reference_data/ | 11 | 190 KB | 11 | 2.4K | Static reference lookup data |
| .claude/ | 17 | 55 KB | 16 | 1K | Claude Code metadata and skills |
| financial_trends_reporter/ | 18 | 50 KB | 11 | 605 | Standalone trend analytics app |
| .github/ | 1 | 7 KB | 1 | 186 | CI/CD workflow definitions |
| launchers/ | 4 | 5 KB | 3 | 80 | Desktop entry point scripts |
| data/ | 1 | 0.03 KB | 1 | 3 | Runtime preferences |

---

## DETAILED FOLDER ANALYSIS

### 1. saved_plans/ (1.1 GB, 33 files)
**User Plan Snapshots & Cache**
- Stores persisted user plan calculations and snapshots
- 15 text files: CSV, JSON, log files with plan metadata
- 225 lines of configuration/metadata
- Largest user data directory - safe to clean old snapshots

### 2. local_state/ (940 MB, 472 files)
**SQLite Runtime Database & Session State**
- 56 text files: configuration and state logs
- 2,546 lines of state metadata
- Contains .db, .db-shm, .db-wal, and .ldb files
- Persistent local application state

### 3. output/ (74 MB, 16 files)
**Generated Reports & Build Artifacts**
- 14 text files: manifests, logs, metadata
- 19,592 lines: report package manifests and build snapshots
- build_snapshot.json - build fingerprints
- report_package.json - advisor package manifest

### 4. tests/ (22 MB, 1,853 files)
**Pytest Test Suite & Fixtures**
- 423 text files: Python tests, configurations, fixtures
- 84,967 lines of test code
- Subdirectories:
  - __pycache__/ - 1,404 compiled Python files (18 MB)
  - fixtures/ - 32 fixture files
  - e2e/ - 18 end-to-end tests
  - frontend/ - 26 browser tests
- Comprehensive test coverage for all modules

### 5. src/ (12.5 MB, 567 files)
**Python Application Core (60.8K lines)**

#### Subdirectories:
- **__pycache__/** (222 files, 5.2 MB) - Compiled Python bytecode
- **projection_stages/** (50 files, 777 KB) - Retirement projection stages
- **reporting/** (75 files, 2.9 MB) - Report generation module (largest)
- **server_services/** (62 files, 833 KB) - Server business logic
- **server/** (47 files, 893 KB) - HTTP server implementation
- **parsing/** (17 files, 105 KB) - Data parsing utilities
- **http_runtime/** (11 files, 147 KB) - HTTP runtime handler
- **dashboard_ui/** (7 files, 8.4 KB) - Dashboard UI logic

#### Key Files (by line count):
- reporting/\*.py - Report generation (largest component)
- projection_stages/\*.py - Stage calculations
- server_services/\*.py - Business logic
- server/\*.py - HTTP server

### 6. frontend/ (1.6 MB, 44 files)
**Browser User Interface (30.7K lines)**

#### Subdirectories:
- **js/** (37 files, 1.48 MB) - JavaScript/React components
- **css/** (2 files, 105 KB) - Stylesheets
- **assets/** (3 files, 12.8 KB) - Images and icons
- **node_modules/** - NPM dependencies (not detailed)

#### File Types:
- JavaScript/TypeScript components
- React application code
- CSS stylesheets
- Static assets

### 7. documentation/ (1.5 MB, 63 files)
**Project Documentation & Specifications (16.9K lines)**

#### Subdirectories:
- **reports/** (16 files, 718 KB) - Report templates and specs
- **archive/** (13 files, 208 KB) - Superseded plans (historical)
- **readme/** (2 files, 2.6 KB) - Release READMEs
- **release_notes/** (1 file, 775 B) - Version history

#### Content:
- API contracts and specifications
- System design documentation
- Release notes and changelogs
- Runbooks and procedures
- Design validation documents

### 8. input/ (1.2 MB, 85 files)
**Plan Data Files & Configuration (14K lines)**

- 76 text files: plan data, CSV, JSON
- 14,006 lines: plan configurations and metadata
- plan_data_manifest.json - data registry
- User plan data and reference files

### 9. tools/ (690 KB, 81 files)
**Build & Maintenance Scripts (14K lines)**

- 55 text files: Python, PowerShell, Bash
- 14,041 lines of build and automation code
- Key scripts:
  - build_workbook.py - Report generation
  - run_regression.py - Test harness
  - check_plan_data_sync.py - Data validation
  - launchers/ - Desktop entry scripts

### 10. reference_data/ (190 KB, 11 files)
**Static Reference Data (2.4K lines)**

- 11 text files: CSV, JSON, configuration
- Reference assumptions and lookup tables
- Static data for calculations

### 11. .claude/ (55 KB, 17 files)
**Claude Code Metadata & Skills (1K lines)**

#### Subdirectories:
- **skills/system-review/** - Custom system review skill
- **workflows/** - Multi-agent workflows
- **agents/** - Custom agent definitions
- **hooks/** - Harness lifecycle hooks

- Configuration for Claude Code assistance
- Custom skills and workflows
- Agent definitions and triage logic

### 12. financial_trends_reporter/ (50 KB, 18 files)
**Standalone Trend Analytics App (605 lines)**

- 11 text files: Python, JavaScript, config
- Separate application with own entry point
- Weekday-5pm trend report generation
- Imports src/ modules as library
- Own runtime log (gitignored)

### 13. .github/ (7 KB, 1 file)
**CI/CD Workflows (186 lines)**

- GitHub Actions workflow definitions
- 1 text file: workflow configuration

### 14. launchers/ (5 KB, 4 files)
**Desktop Entry Scripts (80 lines)**

- 3 text files: entry point scripts
- Delegates to tools/launchers/
- Windows application launchers

### 15. data/ (0.03 KB, 1 file)
**Desktop Runtime Preferences (3 lines)**

- Minimal configuration directory
- Desktop app profile data

---

## STATISTICS SUMMARY

**Total by Category:**
- **Python (.py):** 1,097 files | 289.6K lines | 13.2 MB
- **JavaScript (.js):** 1,684 files | 205.9K lines | 30.1 MB  
- **Data/Config (.json, .csv):** 322 files | 94.3K lines | 4.1 MB
- **Documentation (.md):** 257 files | 28.4K lines | 2.9 MB
- **TypeScript (.ts):** 124 files | 48.7K lines | 5.5 MB
- **Binaries/Compiled:** 1,092 files | - | 256 MB
- **Other Text:** 214 files | 11.4K lines | 0.6 MB

**Largest Components:**
1. Tests (84.9K lines) - Comprehensive coverage
2. Application (60.8K lines) - Core calculation engine
3. Reports (30.7K lines) - Frontend UI
4. Documentation (16.9K lines) - Project specs
5. Tools (14K lines) - Build automation

**Data Breakdown:**
- User Data: 2.1 GB (saved_plans + local_state)
- Generated: 74 MB (output, build, dist)
- Source Code: 26 MB (src + tests + frontend)
- Configuration: 3 MB (input, reference_data, docs)

---


# Mault - AI Coder Guide

> **READ THIS FIRST**: This document helps AI coding assistants (Cursor, Copilot, ChatGPT, Claude) understand and maintain `mault.yaml` — the project's architectural rulebook — and navigate Mault's enforcement features.

---

## What is Mault?

**Mault automates architectural discipline for AI-assisted development.** It's a VS Code extension that:

1. **Detects** architectural violations in real-time (wrong file locations, deprecated patterns, naming chaos)
2. **Advises** with context-rich prompts explaining why something is wrong and how to fix it
3. **Enforces** project conventions defined in `docs/mault.yaml`

**Why it matters for AI coders**: AI coding tools are fast but lack architectural memory. They write messy code if they see messy code. Mault gives you the rulebook so you can **maintain consistency** across the codebase.

The **Mault Panel** (sidebar) is the primary interface — it groups findings by category, shows counts, and lets you copy AI-ready prompts with one click.

### Product Tiers

| Tier | Price | What's Included |
|------|-------|-----------------|
| **Core** | **FREE** | All 16 detectors, AI prompts, Mault Panel (detection only) |
| **Mault Pro** | $99 + $7.99/mo | Everything in Core + automated governance, Production Readiness Kit, early access |

---

## CRITICAL: Rules Are NOT Optional

> **This is the most important section for AI coders to understand.**

When Mault detects an issue, you have exactly **TWO choices**:

1. **FIX IT** — Resolve the issue according to the recommended action
2. **EXCLUDE IT** — Add the file/pattern to `.vscode/settings.json` exclusions

**You may NOT**:
- Ignore the issue and continue working
- Argue that the issue is "not important"
- Suggest the user "can fix it later"
- Skip the fix because "it's just a warning"

### The "Physics, Not Policy" Principle

Mault operates on **physics, not policy**:
- **Policy** (docs, guidelines) = AI can ignore
- **Physics** (errors, blocks) = AI cannot bypass

**Core (Free)** = Policy (recommendations, can continue)
**Pro (Paid)** = Physics (enforcement, commits blocked)

### Handling Every Detection

For every Mault finding:

```
1. READ the issue message and understand WHY
2. ASSESS severity:
   - Severe: Security risk, data loss, production break -> FIX NOW
   - Medium: Tech debt, maintainability -> FIX SOON
   - Minimal: Style, minor inconsistency -> FIX OR EXCLUDE

3. If legitimate issue -> FIX IT
4. If false positive -> ADD EXCLUSION:
   // .vscode/settings.json
   {
     "mault.excludePatterns": ["path/to/false-positive.ts"]
   }

5. NEVER leave issues unresolved
```

### Why This Matters

AI coders without Mault create **architectural drift**:
- Files in wrong places
- Inconsistent naming
- Deprecated patterns spreading
- Config chaos

**Every unresolved issue compounds.** Fix them as you encounter them.

---

## Handling Mault Prompts

When you receive a Mault prompt (via "Copy Universal Prompt" from the Mault Panel sidebar), it includes a **triage workflow** to help you make informed decisions.

### Prompt Structure

Every Mault Universal Prompt follows this structure:

```markdown
## Mault: [Category] (N issues)

### Issues
- `file.ts:42` -- Description [Severity]

### Your Task                          <-- START HERE

For each issue, ask: **[Triage Question]**

**Legitimate issue -> Fix it:**
- Signal 1
- Signal 2

**False positive -> Exclude it:**
- Signal 1
- Signal 2

### Fix Actions                        <-- IF LEGITIMATE
1. Action 1
2. Action 2

### Exclusions                         <-- IF FALSE POSITIVE
{ "mault.excludePatterns": [...] }
```

### How to Interpret Triage Questions

The **triage question** helps you determine if an issue is real or a false positive:

1. **Read the triage question** — e.g., "Is this config file expected for this project type?"
2. **Check legitimate signals** — Does the issue match any of these patterns? Fix it
3. **Check false positive signals** — Does the issue match any of these? Exclude it
4. **Never skip** — Every issue must result in either a fix or an exclusion

### Example Workflow

**Prompt**: "Is this file a versioned duplicate that should be archived?"

**Issue**: `config_backup_v2.ts`

**Analysis**:
- Legitimate: File has `_v2` suffix. This IS a versioned duplicate
- **Action**: Archive to `.memory-layer/archive/` and keep only current version

**Issue**: `api/v2/routes.ts`

**Analysis**:
- False Positive: File is in `/api/v2/`. This is intentional API versioning
- **Action**: Add `**/api/v*/**` to `mault.excludePatterns`

---

## Quick Setup (New Projects)

> **CRITICAL**: The mault.yaml configuration MUST match your actual project structure. Generic templates won't work. You MUST scan the codebase first and adapt mault.yaml accordingly.

### Step 1: Detect Language

Look for indicator files:

| If you find... | Language | Test Pattern | Function Naming |
|----------------|----------|--------------|-----------------|
| `tsconfig.json`, `*.ts` files | **TypeScript** | `*.test.ts`, `*.spec.ts` | `camelCase` |
| `package.json` (no tsconfig) | **JavaScript** | `*.test.js`, `*.spec.js` | `camelCase` |
| `pyproject.toml`, `requirements.txt`, `setup.py` | **Python** | `test_*.py`, `*_test.py` | `snake_case` |
| `go.mod`, `*.go` files | **Go** | `*_test.go` | `camelCase` |
| `pom.xml`, `build.gradle` | **Java** | `*Test.java` | `camelCase` |
| `Cargo.toml`, `*.rs` files | **Rust** | `#[test]` annotations | `snake_case` |
| `*.csproj`, `*.sln` | **C#/.NET** | `*Tests.cs` | `PascalCase` |
| `Package.swift`, `*.swift` | **Swift** | `*Tests.swift` | `camelCase` |
| `CMakeLists.txt`, `*.cpp` | **C++** | Framework-dependent | `snake_case` |

> **Monorepo detection**: Mault checks one level deep for package manifests (`package.json`, `pyproject.toml`, `go.mod`, etc.) to detect monorepo structures automatically.

### Step 2: Map Directory Structure

Run `ls -la` or `tree -L 2` to discover:

```bash
# What is the source directory?
#   src/          <-- TypeScript standard
#   lib/          <-- Some Node.js projects
#   app/          <-- Python Flask/Django
#   <package>/    <-- Python with package name
#   cmd/          <-- Go standard
#   (flat)        <-- All code in root

# Where are services/business logic?
#   src/services/, lib/services/, app/services/, or none

# Where are utilities?
#   src/utils/, src/helpers/, lib/utils/, common/, or none

# Where are tests?
#   tests/, __tests__/, test/, or colocated (src/**/*.test.ts)
```

### Step 3: Record What You Found

Before writing mault.yaml, note:

- **Source directory**: \_\_\_ (e.g., `src`, `lib`, `app`, or root)
- **Services location**: \_\_\_ (e.g., `src/services`, or none)
- **Utils location**: \_\_\_ (e.g., `src/utils`, `helpers`, or none)
- **Models location**: \_\_\_ (e.g., `src/models`, or none)
- **Tests location**: \_\_\_ (e.g., `tests`, `__tests__`, or colocated)
- **Config files present**: \_\_\_ (e.g., `.gitignore`, `package.json`)

### Step 4: Create docs/mault.yaml

Create the file using the template below, **replacing ALL paths with what you discovered**.

```
your-project/
+-- docs/
|   +-- mault.yaml    <-- CREATE THIS FILE
+-- [source-dir]/     <-- Whatever you discovered
+-- [config-files]
```

---

## TypeScript/JavaScript Template

> **WARNING**: Replace all `src/` paths with YOUR actual source directory.

```yaml
version: 1

environment:
  apiPort: 3000
  shell: 'bash' # or "powershell" for Windows

# Note: conventions.naming is for documentation only (not enforced by detectors)
# Use Detectors.directoryReinforcement.rules for file placement enforcement
conventions:
  naming:
    - filePattern: '*.ts'
      className: 'PascalCase'
      functionName: 'camelCase'
      constantName: 'SCREAMING_SNAKE_CASE'

deprecatedPatterns:
  - id: dep-moment
    import: moment
    message: 'Use date-fns or dayjs instead of moment.'
    languages: [typescript, javascript]

  - id: dep-request
    import: request
    message: 'Use axios or node-fetch instead of request.'
    languages: [typescript, javascript]

  # Add project-specific deprecated patterns here

Detectors:
  # UC01: Directory Reinforcement
  directoryReinforcement:
    enabled: true
    rules:
      - pattern: '**/*Service.{ts,js}'
        expectedDir: 'src/services'       # ← REPLACE with your services location
        reason: 'Service files should be in src/services/'
      - pattern: '**/*util*.{ts,js}'
        expectedDir: 'src/utils'          # ← REPLACE with your utils location
        reason: 'Utility files should be in src/utils/'
      - pattern: '**/*.test.{ts,js}'
        expectedDir: 'tests'              # ← REPLACE with your tests location
        reason: 'Test files should be in tests/'

  # UC03/UC10: Naming Convention
  namingConvention:
    enabled: true
    fileNaming: 'kebab-case'
    variableNaming: 'camelCase'
    functionNaming: 'camelCase'
    classNaming: 'PascalCase'
    constantNaming: 'SCREAMING_SNAKE_CASE'
    excludePatterns:
      - '**/[A-Z]*.ts'
      - '**/*.test.{ts,js}'
      - '**/*.d.ts'
      - '**/*.config.*'

  # UC04: Environment Reinforcement
  environmentReinforcement:
    enabled: true
    checkPaths: true
    checkCommands: true

  # UC06: Temporary Files
  tempFiles:
    enabled: true
    patterns:
      - '**/*.tmp'
      - '**/temp_*'
      - '**/scratch_*'
      - '**/*.bak'
      - '**/debug_*'

  # UC07: Flat Architecture
  flatArchitecture:
    enabled: true
    targets:
      - path: 'src'                       # ← REPLACE with your source directory
        maxRootFiles: 10
        minSubdirs: 2
        excludePatterns: ['dist/**', 'node_modules/**']

  # UC08: Configuration Chaos
  configChaos:
    enabled: true
    requiredConfigs:
      - '.gitignore'
      - 'package.json'
      - 'tsconfig.json'

  # UC09: File Proliferation
  fileProliferation:
    enabled: true
    threshold: 3

  # UC11: Overcrowded Folders
  overcrowdedFolders:
    enabled: true
    targets:
      - path: 'src'                       # ← REPLACE with your source directory
        maxFiles: 20

  # UC12: Misplaced Utilities
  misplacedUtilities:
    enabled: true
    centralLocation: 'src/utils'          # ← REPLACE with your central utils path

  # UC16: Dependency Health (Pro)
  dependencyHealth:
    enabled: true
    severityThreshold: 'moderate'

  # UC17: Production Readiness (Pro)
  productionReadiness:
    enabled: true

  # Project Scaffolding
  projectScaffolding:
    enabled: true
    rootMaxFiles: 15

  # Dead End Directories
  deadEnds:
    enabled: true
    ignoreGlobs: []
    maxFiles: 500
    timeBudgetMs: 5000
```

---

## Python Template

> **WARNING**: Python projects vary widely. Replace ALL paths with your actual structure.

```yaml
version: 1

environment:
  apiPort: 8000
  shell: 'bash' # or "powershell" for Windows

# Note: conventions.naming is for documentation only (not enforced by detectors)
# Use Detectors.directoryReinforcement.rules for file placement enforcement
conventions:
  naming:
    - filePattern: '*.py'
      className: 'PascalCase'
      functionName: 'snake_case'
      variableName: 'snake_case'
      constantName: 'SCREAMING_SNAKE_CASE'

deprecatedPatterns:
  - id: dep-optparse
    import: optparse
    message: 'Use argparse instead of optparse.'
    languages: [python]

  - id: dep-urllib2
    import: urllib2
    message: 'Use urllib.request instead (Python 3).'
    languages: [python]

  - id: dep-imp
    import: imp
    message: 'Use importlib instead of imp.'
    languages: [python]

  # Add project-specific deprecated patterns here

Detectors:
  # UC01: Directory Reinforcement
  directoryReinforcement:
    enabled: true
    rules:
      - pattern: '**/*_service.py'
        expectedDir: 'app/services'        # ← REPLACE with your services location
        reason: 'Service files should be in app/services/'
      - pattern: '**/*_util*.py'
        expectedDir: 'app/common'           # ← REPLACE with your utils location
        reason: 'Utility files should be in app/common/'
      - pattern: '**/test_*.py'
        expectedDir: 'tests'               # ← REPLACE with your tests location
        reason: 'Test files should be in tests/'

  # UC03/UC10: Naming Convention
  namingConvention:
    enabled: true
    fileNaming: 'snake_case'
    variableNaming: 'snake_case'
    functionNaming: 'snake_case'
    classNaming: 'PascalCase'
    constantNaming: 'SCREAMING_SNAKE_CASE'
    excludePatterns:
      - '**/test_*.py'
      - '**/__init__.py'
      - '**/conftest.py'

  # UC04: Environment Reinforcement
  environmentReinforcement:
    enabled: true
    checkPaths: true
    checkCommands: true

  # UC06: Temporary Files
  tempFiles:
    enabled: true
    patterns:
      - '**/*.tmp'
      - '**/temp_*'
      - '**/scratch_*'
      - '**/*.bak'

  # UC07: Flat Architecture
  flatArchitecture:
    enabled: true
    targets:
      - path: 'app'                        # ← REPLACE with your source directory
        maxRootFiles: 8
        minSubdirs: 2
        excludePatterns: ['**/__pycache__/**']

  # UC08: Configuration Chaos
  configChaos:
    enabled: true
    requiredConfigs:
      - '.gitignore'
      - 'pyproject.toml'                   # ← or requirements.txt

  # UC09: File Proliferation
  fileProliferation:
    enabled: true
    threshold: 3

  # UC11: Overcrowded Folders
  overcrowdedFolders:
    enabled: true
    targets:
      - path: 'app'                        # ← REPLACE with your source directory
        maxFiles: 20

  # UC12: Misplaced Utilities
  misplacedUtilities:
    enabled: true
    centralLocation: 'app/common'          # ← REPLACE with your central utils path

  # UC16: Dependency Health (Pro)
  dependencyHealth:
    enabled: true
    severityThreshold: 'moderate'

  # UC17: Production Readiness (Pro)
  productionReadiness:
    enabled: true

  # Project Scaffolding
  projectScaffolding:
    enabled: true
    rootMaxFiles: 10

  # Dead End Directories
  deadEnds:
    enabled: true
    ignoreGlobs: ['**/__pycache__/**']
    maxFiles: 500
    timeBudgetMs: 5000
```

---

## If a Directory Doesn't Exist

If your project has no `services/` folder, you have two choices:

1. **Skip the rule** — Don't include `directoryReinforcement` rules for it
2. **Establish the convention** — Keep the rule to guide future file placement

---

## After Setup: The Mault Panel

Once `docs/mault.yaml` exists, **reload VS Code** (`Ctrl+Shift+P` > "Developer: Reload Window") to activate Mault's detectors.

### The Mault Panel (Primary Interface)

The **Mault Panel** is a sidebar tree view that groups all findings by category:

```
MAULT PANEL
+-- Directory Reinforcement (3)
|   +-- src/UserService.ts -> should be in src/services/
|   +-- src/formatDate.ts -> should be in src/utils/
|   +-- test/api.test.ts -> should be in tests/
+-- Naming Conventions (2)
|   +-- src/services/user_service.ts -> camelCase expected
|   +-- src/utils/DateHelper.ts -> should match folder convention
+-- Configuration Chaos (1)
    +-- Missing: tsconfig.json
```

**How to use the Mault Panel**:
1. **Click a category header** to expand and see individual findings
2. **Right-click a category** > **Copy Universal Prompt** — copies an AI-ready prompt with full context, triage guidance, and fix actions for ALL issues in that category
3. **Paste the prompt** into your AI coding assistant (Cursor, Copilot, Claude, ChatGPT)
4. **Click a finding** to jump to the file location
5. **Dismiss findings** you've resolved or excluded

### Problems Panel (Also Works)

Mault also publishes diagnostics to the standard VS Code Problems Panel (`Ctrl+Shift+M` / `Cmd+Shift+M`). You can use Quick Fix (`Ctrl+.` / `Cmd+.`) on any finding for one-click remediation.

---

## When to Update mault.yaml

Update the rulebook when you:

| Action | Update Section |
|--------|----------------|
| Create a new directory structure | `Detectors.directoryReinforcement.rules` |
| Establish a naming convention | `conventions.naming` (documentation only) |
| Deprecate an old library/pattern | `deprecatedPatterns` |
| Create a new business flow | `applicationFlows` |
| Add required configuration files | `Detectors.configChaos.requiredConfigs` |

### Example: Adding a New Directory Rule

If you create a new `src/adapters/` directory for external API adapters:

```yaml
Detectors:
  directoryReinforcement:
    rules:
      # ... existing rules ...
      - pattern: '**/*Adapter.ts'
        expectedDir: 'src/adapters'
        reason: 'Adapter files should be in src/adapters/'
```

### Example: Deprecating a Pattern

If you're migrating from `axios` to `fetch`:

```yaml
deprecatedPatterns:
  - id: axios-deprecated
    import: axios
    message: 'Use native fetch API. See docs/migration/axios-to-fetch.md'
    languages: [typescript, javascript]
```

---

## Detection Levels

Mault uses **progressive detection levels** to avoid overwhelming new users. Detectors unlock over time:

| Level | Name | When Active | Detectors |
|-------|------|-------------|-----------|
| **1** | Gentle | Day 0+ (immediate) | UC02 Legacy Paths, UC04 Environment, UC13 App Flows, UC16 Dependency Health |
| **2** | Balanced | Day 7+ (auto-upgrade) | + UC01 Directory, UC03 Conventions, UC06 Temp Files, UC08 Config Chaos, UC18 Structural Governance |
| **3** | Full | Day 14+ (auto-upgrade) | + UC07 Flat Architecture, UC09 File Proliferation, UC10 Naming Chaos, UC11 Overcrowded Folders, UC12 Scattered Utils, UC15 Test Pyramid |

**Manual override**: Run `Mault: Set Detection Level` from the Command Palette to change levels immediately.

> **AI Coder Note**: If the user has been using Mault for less than 7 days, only Level 1 detectors are active. You won't see directory reinforcement or config chaos findings yet. You can advise the user to run `Mault: Set Detection Level` > "Full (3)" to enable all detectors immediately.

---

## How Detection Works

All 16 detectors follow the same pattern. Here's a worked example using **Directory Reinforcement** (UC01):

### Example: Detecting a Misplaced File

```
1. TRIGGER
   File saved: src/UserService.ts
   Rule in mault.yaml: **/*Service.ts -> src/services/

2. DETECTION
   DirectoryDetector evaluates file path against rules
   Confidence score: 0.95 (high - file matches *Service.ts pattern)
   Result: Misplaced file detected

3. MAULT PANEL
   Category: "Directory Reinforcement (1)"
   Finding: "src/UserService.ts -> should be in src/services/"

4. USER ACTION
   Right-click category > "Copy Universal Prompt"
   Prompt includes: triage question, fix actions, exclusion patterns

5. RESOLUTION
   AI coder moves file to src/services/UserService.ts
   Updates imports in dependent files
   Mault Panel clears the finding
```

### All 16 Detectors Reference

| # | UC | Detector | YAML Config | Level | What It Catches |
|---|-----|----------|-------------|-------|-----------------|
| 1 | UC01 | **Directory Reinforcement** | `Detectors.directoryReinforcement` | 2 | Files in wrong directories |
| 2 | UC02 | **Legacy Path Prevention** | `deprecatedPatterns` (top-level) | 1 | Deprecated imports/patterns |
| 3 | UC03/10 | **Naming Convention** | `Detectors.namingConvention` | 2 | File and symbol naming violations |
| 4 | UC04 | **Environment Reinforcement** | `Detectors.environmentReinforcement` | 1 | OS-specific paths/commands |
| 5 | UC06 | **Temporary Files** | `Detectors.tempFiles` | 2 | .tmp, .bak, scratch files |
| 6 | UC07 | **Flat Architecture** | `Detectors.flatArchitecture` | 3 | Too many root files, missing layers |
| 7 | UC08 | **Configuration Chaos** | `Detectors.configChaos` | 2 | Missing config files |
| 8 | UC09 | **File Proliferation** | `Detectors.fileProliferation` | 3 | Versioned duplicates (_v1, _v2) |
| 9 | UC11 | **Overcrowded Folders** | `Detectors.overcrowdedFolders` | 3 | Too many mixed files in one folder |
| 10 | UC12 | **Misplaced Utilities** | `Detectors.misplacedUtilities` | 3 | Utilities not centralized |
| 11 | UC13 | **Application Flows** | `applicationFlows` (top-level) | 1 | High-impact file changes |
| 12 | UC16 | **Dependency Health** (Pro) | `Detectors.dependencyHealth` | 1 | Vulnerable packages |
| 13 | UC17 | **Production Readiness** (Pro) | `Detectors.productionReadiness` | -- | Production readiness journey |
| 14 | UC18 | **Structural Governance** (Pro) | `rules` (top-level) | 2 | AST pattern enforcement |
| 15 | -- | **Project Scaffolding** | `Detectors.projectScaffolding` | 2 | Root file clutter |
| 16 | -- | **Dead-End Directories** | `Detectors.deadEnds` | 3 | Unreferenced folders (JS/TS) |

**Language Support Key:**
- **Polyglot**: UC01-UC09, UC11 work with any language via file/folder pattern matching
- **JS/TS**: UC12 (dead ends), UC16 (npm audit) require JavaScript/TypeScript
- **JS/TS + Python**: UC18 uses AST analysis for both JS/TS and Python

> **Important**: `conventions.directories` is NOT a valid config key. Use `Detectors.directoryReinforcement.rules` for file placement rules.
> **Important**: `governance.rules` is NOT valid. Use `rules` (top-level key).
> **Note**: Some detectors (`misplacedUtilities`, `dependencyHealth`, `productionReadiness`, `projectScaffolding`) use built-in defaults and don't read all YAML fields yet. Their sections are included for completeness and forward compatibility — the `enabled: true` flag is read by the RulebookHealthDetector to verify your rulebook is complete.

---

## Available Commands

Access via Command Palette (`Ctrl+Shift+P` / `Cmd+Shift+P`).

### Setup & Configuration

| Command | Description |
|---------|-------------|
| `Mault: Initialize` | Initialize Mault in the workspace |
| `Mault: Open AI Coder Guide` | Open this setup guide |
| `Mault: Audit Configuration` | Check mault.yaml validity |
| `Mault: Set Detection Level` | Choose Gentle (1), Balanced (2), or Full (3) |

### Mault Panel Actions

| Command | Description |
|---------|-------------|
| `Mault: Copy Universal Prompt` | Copy AI-ready prompt for selected category (primary workflow) |
| `Mault: Dismiss Finding` | Remove a finding from the Mault Panel |
| `Mault: Refresh Panel` | Re-run all detectors and refresh the panel |

### AI Prompt Generation

| Command | Description |
|---------|-------------|
| `Mault: Copy findings report (JSON)` | Full JSON report of all issues |
| `Mault: Copy remediation prompt` | AI-optimized prompt for a specific issue |
| `Mault: Copy naming convention fix prompt` | Naming violation fix prompt |
| `Mault: Copy Setup Prompt` | Copy the Pro setup prompt for AI coders |

### Analysis Triggers

| Command | Description |
|---------|-------------|
| `Mault: Analyze naming conventions` | Check naming violations across project |
| `Mault: Analyze file proliferation` | Find duplicate/versioned files |
| `Mault: Analyze flat architecture` | Check for overcrowded directories |
| `Mault: Analyze dead-end directories` | Find unreferenced folders (JS/TS) |
| `Mault: Find Scattered Utils` | Locate misplaced utility files (JS/TS) |
| `Mault: Analyze dependency health` | Check for vulnerable packages |
| `Mault: Analyze structural compliance` | AST-based pattern analysis |
| `Mault: Full Environment Scan` | Comprehensive environment check |

### File Operations

| Command | Description |
|---------|-------------|
| `Mault: Move file to expected location` | Quick Fix to move misplaced file |
| `Mault: Archive temporary files` | Move temp files to archive |
| `Mault: Quick rename file` | Single file rename |
| `Mault: Batch rename all files` | Batch rename all flagged files |

### Pro Commands

| Command | Description |
|---------|-------------|
| `Mault: Open Production Readiness Kit (Pro)` | Open the 9-step production readiness journey |
| `Mault: Generate Architecture Diagram` | Visualize dependency graph |
| `Mault: Reset Steps 1-3` | Reset infrastructure steps (local) |
| `Mault: Open Analytics Dashboard` | Admin-only analytics view |

---

## Best Practices

### 1. Scan Before Writing
Always run `ls -la` or `tree -L 2` before creating mault.yaml. Never assume `src/` exists.

### 2. Replace ALL Template Paths
Every `src/services`, `src/utils`, `tests/` in the template must be replaced with your actual paths.

### 3. Use the Mault Panel
The Mault Panel sidebar is the primary interface. Right-click a category header to copy AI-ready prompts with full context — this is more effective than copying individual findings.

### 4. Update Rules When Creating Patterns
When you establish a new pattern (e.g., "all adapters go in `src/adapters/`"), add it to mault.yaml.

### 5. Check Diagnostics After Changes
Run `Mault: Refresh Panel` to see if your changes introduced new violations.

---

## File Locations

| Purpose | Path |
|---------|------|
| Project rulebook | `docs/mault.yaml` |
| Extension logs | `.memory-layer/logs/` |
| Cached rules | `.memory-layer/cache/` |
| Exported reports | `.memory-layer/reports/` |
| Archived files | `.memory-layer/archive/` |
| Step proof files (Pro) | `.mault/verify-stepN.proof` |

---

## Pro: Production Readiness Kit

> **Tier**: Pro-only ($99 activation + $7.99/month)

The Production Readiness Kit is a structured **9-step journey** that takes your project from "runs locally" to "production-ready." It provides battle-tested setup guides that any AI coder can follow to create production infrastructure.

### Getting Started

**Step 1: Purchase Pro** via the extension or [mault.ai/billing](https://mault.ai/billing)

**Step 2: Copy Setup Prompt** into your AI coding assistant:

```
Run command "Mault: Open Production Readiness Kit (Pro)" and set up my project.

1. Read the Production Readiness Kit that opens
2. Follow the 9-step journey to make my project production-ready
3. Check progress in the Production Readiness tree view when each step is complete
```

**Step 3: Watch Progress** in the Production Readiness tree view in the Mault sidebar. Each step shows its completion status and provides a "Copy Prompt" action to guide your AI coder.

### Production Readiness Levels

| Level | Name | What It Means | Artifacts Created |
|-------|------|---------------|-------------------|
| 0 | Runs locally | Code exists, no infrastructure | Just code |
| 1 | Reproducible | Someone else can run it | requirements.txt, .env.example |
| 2 | Portable | Runs in a container | Dockerfile, docker-compose.yml |
| 3 | Deployed | Runs in the cloud | CI/CD pipeline, cloud config |
| 4 | Reliable | Stays running | Health checks, logging, rollback |

**The Kit takes you from Level 0 to Level 4.**

### The 9-Step Journey

| Step | Category | Name | What It Creates |
|------|----------|------|-----------------|
| 1 | Infrastructure | **Git Repository Setup** | .git, .gitignore, branch conventions |
| 2 | Infrastructure | **Environment Configuration** | .env.example, secrets management, .gitignore rules |
| 3 | Infrastructure | **Containerization (Docker)** | Dockerfile, docker-compose.yml, .dockerignore |
| 4 | Infrastructure | **CI/CD Pipeline** | GitHub Actions workflow, branch protection |
| 5 | Testing | **TDD Framework** | Test directories, coverage config, TIA setup |
| 6 | Hooks | **Pre-commit Framework** | Pre-commit hooks (up to 9 layers) |
| 7 | Enforcement | **Mault Enforcement** | docs/mault.yaml with UC01-UC18 rules |
| 8 | Governance | **Governance Testing** | Governance scripts, baselines, ratchets |
| 9 | AI Rules | **AI Coder Testing Rules** | .cursorrules, copilot-instructions.md, .windsurfrules |

> **Steps 1-3 and 9**: Available to all users (FREE tier included).
> **Steps 4-8**: Pro content delivered from server with bundled fallback.

### AGENT-INSTRUCTIONS Format

Steps 4-9 use the **AGENT-INSTRUCTIONS format** — imperative instructions addressed directly to the AI coder:

```
# AGENT-INSTRUCTIONS: [Step Name] (Step N of 9)

> **YOU ARE THE AGENT.** Execute these commands IN ORDER.
> **PHYSICS, NOT POLICY:** Create the verification script FIRST.
> **PREREQUISITE:** Step N-1 must be complete.
> **DO NOT** declare Step N complete unless verification exits 0 with all CHECKs PASS.
```

Each step includes:
- **Anti-patterns block** — Common mistakes to avoid
- **Numbered phases** — Sequential setup instructions
- **CHECK blocks** — Verification criteria (e.g., CHECK 1: Git initialized, CHECK 2: .gitignore exists)
- **Verification script** — Bash script that validates real state (not just file existence)

### Ralph Loop (Verification Protocol)

Every step includes a **verification script** (`mault-verify-stepN.sh`) that implements the **Ralph Loop** — a proof-of-completion mechanism:

```
1. AI creates verification script FIRST (before any other work)
2. AI executes setup commands for the step
3. AI runs verification script: ./mault-verify-stepN.sh
4. Script checks REAL STATE:
   - Does the config file exist AND contain correct values?
   - Do tests actually pass?
   - Does CI actually run?
5. All CHECKs PASS -> Proof file created: .mault/verify-stepN.proof
6. Any CHECK FAIL -> AI fixes and re-runs (loop)
7. Handshake issue created on GitHub as tamper-evident completion record
```

**Why this matters**: The verification script checks actual configuration and behavior, not just file existence. AI coders cannot fake completion — the script exits 1 if any check fails.

### Server-Side Content Delivery

Pro content for Steps 4-9 is fetched from the Mault server with a bundled fallback for offline use. Newly published content has a **48-hour IP protection window** before the bundled fallback is updated.

### Split Reset Commands

| Command | Scope | Who Can Run |
|---------|-------|-------------|
| `Mault: Reset Steps 1-3` | Local infrastructure reset | All users |
| Admin Reset Steps 4-9 | Server-side content reset | Admin only |

### Philosophy Guides

These guides explain the **WHY** behind enforcement. AI coders read them and generate language-specific scripts.

#### Rising Tide (Mock Tax)

**The 2x Rule**: If a unit test is more than 2x the size of the source code, delete the unit test and write an integration test instead.

```
Test : Source Ratio    Interpretation        Action
< 1.0x                 Under-tested          Add more test cases
1.0x - 2.0x            Healthy               Maintain
2.0x - 3.0x            Mock Tax Warning      Consider integration test
> 3.0x                 Excessive             Delete, rewrite as integration
```

**Why**: Tests larger than their source code indicate tight coupling and excessive mocking. These tests are brittle and don't catch real bugs.

#### Iron Dome (Type Safety)

**The Ratchet Rule**: Type-safety holes (`any`, `type: ignore`, `eslint-disable`) can only decrease, never increase.

```
NEW holes BLOCKED           OLD holes GRANDFATHERED
Cannot add new `any`        Existing `any` allowed
Cannot add new `ignore`     Existing `ignore` allowed
Cannot disable more rules   Existing disables allowed

Result: Quality can only IMPROVE over time.
```

**Type Safety Holes by Language**:

| Language | Holes to Track |
|----------|----------------|
| TypeScript | `any`, `as any`, `@ts-ignore`, `@ts-expect-error`, `!` |
| Python | `type: ignore`, `Any`, `cast()`, `# noqa` |
| Go | `interface{}`, `any`, type assertions, `//nolint` |
| Java | Raw types, `@SuppressWarnings("unchecked")`, unchecked casts |

#### TDD Guide

**Test Pyramid**: Unit tests (fast, isolated) at the base, Integration tests (real I/O) in the middle, Behavioral tests (user-visible) at the top.

**The Pure Core Pattern**: Business logic with no I/O imports (easy to test). Adapters are thin wrappers for I/O (tested via integration tests).

#### Ratchet Strategy

**Baseline + Improvement**: Count current violations, set as baseline, block any increase.

```
Day 0:  Generate baseline -> 127 type holes
Day 5:  Developer adds 2 -> BLOCKED (129 > 127)
Day 10: Developer fixes 5 -> New baseline: 122
Day 30: Overall: 127 -> 98 (23% reduction)
```

### Pre-commit Layers (Language-Specific)

The Kit sets up pre-commit hooks with up to 9 layers of protection. These are **language-specific governance patterns** that AI generates for your stack:

**TypeScript Reference (9 Layers)**:

| Layer | Name | Purpose |
|-------|------|---------|
| 1 | Compilation & Static Analysis | Catch type errors Jest might mask |
| 2 | Rising Tide (Mock Tax) | Block oversized unit tests (2x rule) |
| 3 | Test Impact Analysis (TIA) | Run only affected tests locally |
| 4 | Adversarial Mock Scan | Prevent mocking reality |
| 5 | Precision Coverage Ratchet | Enforce 80% on new files |
| 6 | Security Gate | npm audit for vulnerabilities |
| 7 | Integration Test Pairing | Buddy System enforcement |
| 8 | Type Safety Gate (any Ratchet) | Block new `any` usage |
| 9 | Dead Code Gate | Detect silent catches |

These patterns apply to any language — AI adapts them to your stack (pytest for Python, go test for Go, JUnit for Java, etc.).

### Polyglot Detectors (Step 7)

In addition to language-specific hooks, Mault provides **polyglot detectors** that work with ANY language:

| Detector | What It Blocks |
|----------|----------------|
| Directory Reinforcement | Files in wrong directories |
| Legacy Prevention | Files in deprecated paths |
| Environment Reinforcement | Missing/malformed .env |
| Temp File Cleanup | Temp files in commits |
| Flat Architecture | Too many files in root |
| Config Chaos | Config files misplaced |
| File Proliferation | Duplicate files |
| Overcrowded Folders | Too many files per folder |
| Application Flows | High-impact file warnings |

### Language-Specific Pro Detectors

| Detector | Language Support | What It Blocks |
|----------|------------------|----------------|
| Dependency Health | JS/TS (npm audit) | Vulnerable packages, outdated deps |
| Structural Governance | JS/TS (AST), Python (AST) | Missing exports, forbidden patterns, DI violations |

### Language Support Matrix

The Kit is **language-agnostic**. AI generates appropriate scripts for your stack:

| Component | TypeScript/JS | Python | Go | Java |
|-----------|---------------|--------|-----|------|
| Test Framework | Jest, Vitest | pytest | go test | JUnit 5 |
| Type Checking | TypeScript | mypy | Go compiler | Java compiler |
| Linting | ESLint | ruff, flake8 | golangci-lint | Checkstyle |
| Pre-commit | pre-commit | pre-commit | pre-commit | pre-commit |

**Additionally supported** (stack detection included): Rust, C#/.NET, C++, Swift, Julia.

### Files Created

After running the Production Readiness Kit, your project will have:

```
your-project/
+-- .git/                           # Step 1
+-- .gitignore                      # Step 1
+-- .env.example                    # Step 2
+-- Dockerfile                      # Step 3
+-- docker-compose.yml              # Step 3
+-- .dockerignore                   # Step 3
+-- .github/
|   +-- workflows/
|       +-- ci.yml                  # Step 4
+-- tests/
|   +-- unit/                       # Step 5
|   +-- integration/                # Step 5
|   +-- behavioral/                 # Step 5 (optional)
+-- .pre-commit-config.yaml         # Steps 6, 7, 8
+-- docs/
|   +-- mault.yaml                  # Step 7
+-- scripts/
|   +-- governance/                 # Step 8
|       +-- check-mock-tax.{js,py}
|       +-- check-type-safety.{js,py}
|       +-- check-coverage-ratchet.{js,py}
+-- .memory-layer/
|   +-- baselines/                  # Step 8
|       +-- coverage.json
|       +-- type-safety.json
|       +-- mock-tax.json
+-- .mault/
|   +-- verify-step1.proof          # Ralph Loop proof files
|   +-- verify-step2.proof
|   +-- ...
+-- .cursorrules                    # Step 9
+-- .github/copilot-instructions.md # Step 9
```

### Core Principle: Physics, Not Policy

> **"Agents obey Physics, not Policy"**

- **Policy**: Documentation, guidelines, best practices = AI ignores these
- **Physics**: Errors, blocked commits, failed CI = AI cannot bypass these

Every rule in the Production Readiness Kit is enforced as **physics**:
- `warn` is policy (AI ignores)
- `error` is physics (AI cannot proceed)

### For Existing Projects

Same setup process, but AI detects what already exists:
- Has Git? Skip Step 1
- Has Dockerfile? Skip Step 3
- Has pre-commit? Skip Step 6

**Rising Tide for Legacy**: Existing issues are grandfathered, new issues are blocked. Quality only improves.

---

## Data & Privacy Disclosure

Mault performs core analysis **locally** within VS Code. Certain features may perform network requests.

**What connects to the internet:**
- **Authentication**: Email/OAuth for account creation
- **Payments**: Processed securely via Stripe (we never store card details)
- **Entitlement checks**: Subscription validation
- **Pro content delivery**: Step content fetched from server (bundled fallback available)
- **Error reporting**: Crash diagnostics, no code content
- **Usage analytics**: Feature metrics, opt-out via `mault.usage.enabled` setting

**What we don't do:**
- No user code is stored on external servers
- No data is used for AI model training
- No payment card details are stored by Mault

For full details, see our [Privacy Policy](https://mault.ai/privacy/).

---

**Document version: v0.7.0 | Last updated: February 2026**

**Remember**: Mault is your architectural memory. The configuration MUST match your actual project structure — scan first, then customize.

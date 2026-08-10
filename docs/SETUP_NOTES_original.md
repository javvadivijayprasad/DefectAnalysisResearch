# Paper F Rebuild - Setup Notes

Companion notes for `setup_defects4j_bugsinpy.ps1`. Read this before running the script for the first time.

## What is Defects4J?

**Defects4J** (Just, Jalali, and Ernst, ISSTA 2014) is a curated, reproducible database of real Java defects extracted from open-source projects. Each defect comes with:
- A "buggy" and a "fixed" version of the codebase (checkoutable by version tag).
- A minimal patch that isolates the fault.
- A trigger test (or set of tests) that fails on the buggy version and passes on the fixed one.
- Ancillary metadata (class-level fault locations, relevant classes, modified sources).

Defects4J currently ships **~835 real bugs across 17 open-source Java projects**: Chart, Cli, Closure, Codec, Collections, Compress, Csv, Gson, JacksonCore, JacksonDatabind, JacksonXml, Jsoup, JxPath, Lang, Math, Mockito, and Time. Bug counts per project range from ~26 (Cli) to ~174 (Closure).

The `defects4j` CLI provides `checkout`, `compile`, `test`, `mutation`, `coverage`, `export`, and `info` subcommands. All work with buggy version tag `<n>b` and fixed version tag `<n>f`.

## What is BugsInPy?

**BugsInPy** (Widyasari et al., ESEC/FSE 2020) is the Python analogue of Defects4J. It provides **~493 real bugs across 17 open-source Python projects**: ansible, black, cookiecutter, fastapi, httpie, keras, luigi, matplotlib, pandas, PySnooper, sanic, scrapy, spacy, thefuck, tornado, tqdm, and youtube-dl. Each bug ships with a buggy and fixed commit, a failing test, and a `bug.info` metadata file.

Unlike Defects4J, BugsInPy is *not* a shipped test-run environment: each bug requires its own Python interpreter version and pip dependencies. The `bugsinpy-*` scripts wrap `virtualenv` creation and pinned-dependency install per bug.

## Total experiment scale

For Paper F we plan **4 defect-attribution methods** on **all 1,328 bugs** (835 Defects4J + 493 BugsInPy):

    1,328 bugs x 4 methods = 5,312 method-invocations

Add >=3 seeds per method for variance and the effective execution count is ~15,936. Plan the orchestrator around resumable, per-bug per-method checkpoints; do not attempt a monolithic run.

## Disk space and runtime budget

| Item | Approx. size |
|---|---|
| Defects4J framework + all subject checkouts (cached) | ~4 GB |
| BugsInPy framework + per-bug virtualenvs (cached across a full run) | ~5 GB |
| Aggregate logs, coverage traces, per-run artifacts (est.) | ~1 GB |
| **Total working set** | **~10 GB** |

Plan for **~10 GB** of free space on `E:\`. If disk is tight, prune per-bug virtualenvs between runs (`bugsinpy-cleanup`) at the cost of re-install time.

Wall-clock: a *single* Defects4J bug typically compiles + tests in 30-120 s on a modern laptop; some Closure bugs run for 5-10 minutes. A single BugsInPy bug can be much slower on the first checkout because of virtualenv creation and pandas/keras compilation. Budget conservatively **>=24 hours of wall-clock** for a full sweep of 4 methods x 1,328 bugs on a single machine; consider sharding by project.

## Known Windows quirks

### 1. `.sh` scripts require Git Bash
Both `defects4j/init.sh` and every `bugsinpy-*` script are Bourne shell. PowerShell cannot execute them directly. The bootstrap script invokes Git Bash (`C:\Program Files\Git\bin\bash.exe`) explicitly. If Git Bash is not installed, install **Git for Windows** from <https://git-scm.com/download/win>.

For interactive use, prefer working inside Git Bash rather than PowerShell once the frameworks are installed.

### 2. Perl on Windows: Strawberry Perl, not ActivePerl
Defects4J's `init.sh` calls `cpanm` to install Perl modules (`DBI`, `DBD::CSV`, `JSON`, `URI::Escape`). ActivePerl's package manager is incompatible with `cpanm` in the way `init.sh` expects; use **Strawberry Perl**. Chocolatey: `choco install strawberryperl`.

If `cpanm` is missing after Strawberry install:

    cpan App::cpanminus

### 3. Perl / Git line-ending encoding
CRLF-normalisation on `git clone` can corrupt Perl modules and generated patch files. Set globally before cloning subject projects:

    git config --global core.autocrlf false

### 4. `JAVA_HOME` must point to a **JDK**, not a JRE
Defects4J requires JDK 8 for full compatibility (JDK 11 works for most projects but breaks a handful of Closure and JacksonDatabind bugs due to compiler-flag changes). Set:

    setx JAVA_HOME "C:\Program Files\Eclipse Adoptium\jdk-8.0.xxx-hotspot"

Verify with `echo $env:JAVA_HOME` in a fresh PowerShell.

### 5. Path length limit
Windows' default MAX_PATH of 260 characters is easily exceeded by nested Defects4J checkouts under `E:\EB1A_Research\EB1_Master\06_Authorship\Research\PaperF_rebuild\defects4j\...`. Enable long paths:

    # ELEVATED PowerShell:
    New-ItemProperty -Path "HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem" `
      -Name "LongPathsEnabled" -Value 1 -PropertyType DWORD -Force

And in git:

    git config --global core.longpaths true

### 6. Antivirus scanning slows compile/test loops
Windows Defender aggressively scans newly-written `.class`, `.jar`, and `.pyc` files, which dramatically slows Defects4J/BugsInPy loops. Add exclusions:

    Add-MpPreference -ExclusionPath "E:\EB1A_Research\EB1_Master\06_Authorship\Research\PaperF_rebuild"

### 7. Python venv activation is script-signed
If `Activate.ps1` refuses to run, set the per-user execution policy once:

    Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned

### 8. BugsInPy pandas / keras bugs need historical Python
Some BugsInPy bugs pin Python 3.6 or 3.7 and old versions of numpy/scipy that no longer build wheels on modern Windows. For those, use `pyenv-win` to install the exact interpreter version listed in each `bug.info`, or run BugsInPy inside WSL2 for smoother reproduction.

## Next steps after this script succeeds

1. Verify: `defects4j info -p Lang` prints project metadata.
2. Verify: `bugsinpy-info projects` prints the list of 17 subjects.
3. Smoke-test a single bug end-to-end (Defects4J Lang #1, BugsInPy pandas #1) - commands are printed by the bootstrap script.
4. Design the orchestrator: per-bug, per-method, resumable checkpoints, aggregated CSV output.
5. Begin the Paper F draft using `paperF_STVR.tex` in this directory.

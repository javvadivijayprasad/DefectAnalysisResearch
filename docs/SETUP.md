# SETUP — Defects4J + BugsInPy install (WSL2 Ubuntu, primary)

The Paper F corpus is built from Defects4J v2.0.1 and BugsInPy. Both
frameworks work best on Linux — we install into **WSL2 Ubuntu 22.04**. Native
Windows works but requires several workarounds; see `SETUP_NOTES_original.md`
in this directory and the reference PowerShell installer
`setup_defects4j_bugsinpy.ps1` for the Windows path.

## Prerequisites

| Tool               | Version                    | Notes                                   |
| ------------------ | -------------------------- | --------------------------------------- |
| WSL2 Ubuntu        | 22.04 LTS                  | `wsl --install Ubuntu-22.04`            |
| JDK                | **OpenJDK 11**             | Defects4J v2.0.1 requires JDK 11        |
| Python             | 3.10 or 3.11               | BugsInPy per-bug interpreters via pyenv |
| Git                | any recent (>= 2.30)       | LFS not required                        |
| Perl               | native perl 5.30+          | for Defects4J's `init.sh`               |
| `cpanm` + modules  | `DBI`, `DBD::CSV`, `JSON`, `URI::Escape` | installed by `init.sh` |

## Step 1 — Install Defects4J v2.0.1

```bash
sudo apt-get update
sudo apt-get install -y openjdk-11-jdk perl cpanminus git build-essential
cd ~
git clone https://github.com/rjust/defects4j.git
cd defects4j
git checkout v2.0.1                # pin the release
./init.sh                          # ~10-20 min: downloads Major, subject repos
echo 'export PATH=$HOME/defects4j/framework/bin:$PATH' >> ~/.bashrc
source ~/.bashrc
defects4j info -p Lang             # verify: prints project metadata
```

Verify a smoke test:
```bash
defects4j checkout -p Lang -v 1b -w /tmp/lang_1_buggy
cd /tmp/lang_1_buggy && defects4j compile && defects4j test
# Expect: 1 failing test.
```

## Step 2 — Install BugsInPy

```bash
sudo apt-get install -y python3-venv
cd ~
git clone https://github.com/soarsmu/BugsInPy.git
echo 'export PATH=$HOME/BugsInPy/framework/bin:$PATH' >> ~/.bashrc
source ~/.bashrc
bugsinpy-info projects             # prints 17 subjects
```

Some BugsInPy bugs pin Python 3.6/3.7 and old numpy/scipy. Install
`pyenv` to switch interpreters per-bug:

```bash
curl https://pyenv.run | bash
# add pyenv shell init to ~/.bashrc per the printed instructions
pyenv install 3.6.15 3.7.17 3.8.18 3.9.18 3.10.13
```

## Step 3 — Prepare the Paper F workspace

```bash
mkdir -p ~/paperF/{datasets,results,logs}
```

The build script (`scripts/build_real_events.py`) writes parquet files into
`~/paperF/datasets/`. The experiment (`scripts/run_real_experiment.py`) writes
`summary_real.json`, `per_event_metrics_real.csv`, and
`per_row_scores_real.csv` into `~/paperF/results/`.

## Windows quirks we hit during install (native-Windows path)

Preserved for reference; **WSL2 is strongly preferred**.

1. **Git Bash required**: `defects4j/init.sh` and every `bugsinpy-*` script is
   a Bourne shell script. Install *Git for Windows* and invoke via
   `C:\Program Files\Git\bin\bash.exe`.
2. **Strawberry Perl, not ActivePerl**: `cpanm` behaves as `init.sh` expects
   only with Strawberry. `choco install strawberryperl`.
3. **Git line endings**: set `git config --global core.autocrlf false` before
   cloning subject projects, or Perl modules corrupt on checkout.
4. **JDK 11 is mandatory** for Defects4J v2.0.1 — v2.0.0 wanted JDK 8; the
   0.0.1 patch bump changed compiler flags. Point `JAVA_HOME` at a JDK, not a
   JRE.
5. **`MAX_PATH = 260`**: enable long paths in the registry and `git config
   --global core.longpaths true` before cloning under nested research folders.
6. **Windows Defender**: exclude the repo path — real-time scanning of freshly
   written `.class`/`.jar`/`.pyc` files slows Defects4J runs ~5x.
7. **PowerShell execution policy**: `Set-ExecutionPolicy -Scope CurrentUser
   -ExecutionPolicy RemoteSigned` so Python venv `Activate.ps1` runs.
8. **BugsInPy pandas/keras bugs on Windows**: use `pyenv-win` for the exact
   interpreter version pinned in each `bug.info`, or (recommended) run under
   WSL2 instead.

## Disk + wall-clock budget

- ~4 GB Defects4J framework + subject checkouts
- ~5 GB BugsInPy framework + per-bug virtualenvs
- ~1 GB logs / intermediate artifacts
- **Total working set: ~10 GB**
- **Full corpus build: ~90 min on a modern laptop.**
- **Full LOPO experiment: ~5 min once parquet is cached.**

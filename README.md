# bap_play

# Dependencies

You will need to install opam and bap. Run the following as root:

```bash
sudo apt-get install opam
```

Followed by:

```bash
opam init --comp=4.02.3    # install the compiler
opam repo add bap git://github.com/BinaryAnalysisPlatform/opam-repository
eval `opam config env`               # activate opam environment
opam depext --install bap-server     # install bap-server
```

Afterwards cd into your repo directory and run:

```bash
./setup.sh <python-env-dir>
```

setup.sh will create a new Python virtual environment under <python-env-dir> and
also clone and build z3 and its python bindings.

To start using it run

```bash
source <python-env-dir>/bin/activate
```

You can try it out by running test.py

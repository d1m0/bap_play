# bap_play

# Dependencies

You will need to install bap:


```bash
opam init --comp=4.02.3    # install the compiler
opam repo add bap git://github.com/BinaryAnalysisPlatform/opam-repository
eval `opam config env`               # activate opam environment
opam depext --install bap-server     # install bap-server
```

And the python bindings for bap:

```bash
pip install bap
```

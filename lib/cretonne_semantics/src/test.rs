extern crate cretonne;
extern crate cton_reader;
extern crate docopt;
extern crate rustc_serialize;
#[macro_use]
extern crate log;
extern crate env_logger;
extern crate z3;

use docopt::Docopt;
use std::fs::File;
use std::io::Read;
use cretonne::ir::{Cursor, Function};
use cretonne::flowgraph;
use z3::{Config, Context};

pub mod lib;
use lib::Z3State;

const USAGE: &str = "
Semantic Playground

Usage:
    test <file>

Option:
    -h, --help     print this help message
";

#[derive(RustcDecodable, Debug)]
struct Args {
    arg_file:   String,
}

fn main() {
    env_logger::init().unwrap();
    debug!("Starting..");

    let args: Args = Docopt::new(USAGE)
        .and_then(|d| {
                        d.help(true)
                         .decode()
                  })
        .unwrap_or_else(|e| e.exit());

    let mut f: File = File::open(args.arg_file).expect("Error opening file");
    let mut contents: String = String::new();
    f.read_to_string(&mut contents).expect("Error reading from file");
    let t:Vec<Function> = cton_reader::parse_functions(contents.as_str()).expect("Error parsing");
    let z3_cfg = Config::new();
    let z3_ctx = Context::new(&z3_cfg);
    for mut fun in t {
        // Basic datastructures:
        let cfg = flowgraph::ControlFlowGraph::with_function(&fun);

        // Walk over ebbs
        let mut postorder = cfg.postorder_ebbs();
        let mut pos = Cursor::new(&mut fun.layout);

        while let Some(ebb) = postorder.pop() {
            pos.goto_top(ebb);
            let mut state = Z3State::new(&z3_ctx);
            while let Some(inst) = pos.next_inst() {
                state.add_instr(&fun.dfg, inst);
            }
        }
        // Walk over instructions
    }
}

extern crate cretonne;
extern crate cton_reader;
extern crate docopt;
extern crate rustc_serialize;
extern crate z3;

use std::collections::HashMap;
use cretonne::ir::{Opcode, InstructionData, Type,
                   DataFlowGraph, Value, Inst};
use self::z3::{Context, Ast, Sort};

fn to_z3_sort<'ctx>(ctx: &'ctx Context, typ: &Type) -> Sort<'ctx> {
    ctx.bitvector_sort(typ.bits() as u32)
}

pub struct Z3State<'ctx> {
    ctx:    &'ctx Context,
    defs:   HashMap<Value, Ast<'ctx>>,
    sorts:  HashMap<Value, Sort<'ctx>>,
    def_order:   Vec<Value>,
    val_to_ssa_name:   HashMap<Value, String>,
}

enum Z3BinOps {
    BVAdd,
    BVSub,
    BVAnd,
    BVOr,
    BVXor,
    BVShl,
    BVLshr,
    BVAshr,
}

impl<'ctx> Z3State<'ctx> {
    pub fn new(ctx: &'ctx Context) -> Z3State<'ctx> {
        Z3State{ ctx:ctx,
                 defs:HashMap::new(),
                 sorts:HashMap::new(),
                 def_order:vec!(),
                 val_to_ssa_name: HashMap::new() }
    }

    fn lookup(&self, cval: Value, sort: &Sort<'ctx>) -> Ast<'ctx> {
        match self.val_to_ssa_name.get(&cval) {
            Some(name) => {
                let defined_sort = self.sorts.get(&cval)
                    .expect("Definition without sort in Z3State");
                if defined_sort != sort {
                    panic!("Lookup of {} returned type {}, expected {}.",
                           name, defined_sort, sort);
                }
                Ast::new_const(&self.ctx.str_sym(name.as_str()), sort)
            },
            None => panic!("Looking up non-existend C-ton Val {}", cval)
        }
    }

    fn define(&mut self, cval: Value, val: Ast<'ctx>, sort: Sort<'ctx>) -> () {
        if let Some(old_name) = self.val_to_ssa_name.get(&cval) {
            panic!("Redefining existing name {}. SSA Violated.", old_name);
        }

        let num_defs;
        {
            num_defs = self.defs.len();
        }

        let ssa_name = "ssa_".to_string() + num_defs.to_string().as_str();
        println!("Defining {}:={}", ssa_name, &val);

        self.defs.insert(cval, val);
        self.sorts.insert(cval, sort);
        self.def_order.push(cval);
        self.val_to_ssa_name.insert(cval, ssa_name);
    }

    fn bin_opcode_to_z3op(op:  Opcode) -> Option<Z3BinOps> {
        match op {
            Opcode::Iadd => Some(Z3BinOps::BVAdd),
            Opcode::Isub => Some(Z3BinOps::BVSub),
            Opcode::Band => Some(Z3BinOps::BVAnd),
            Opcode::Bor => Some(Z3BinOps::BVOr),
            Opcode::Bxor => Some(Z3BinOps::BVXor),
            Opcode::Ishl => Some(Z3BinOps::BVShl),
            Opcode::Ushr => Some(Z3BinOps::BVLshr),
            Opcode::Sshr => Some(Z3BinOps::BVAshr),
            _ => None
        }
    }

    fn z3_lanewise_binop(ctx: &'ctx Context,
                           lhs: Ast<'ctx>,
                           rhs: Ast<'ctx>,
                           op: &Z3BinOps,
                           sort: &Sort,
                           nlanes: u32,
                           lane_bits: u32) -> Ast<'ctx> {
        // Assert nlanes*lane_bits = width(sort)
        if ctx.bitvector_sort(nlanes * lane_bits) != *sort {
            panic!("Mismatch between expected z3 sort and nlanes*lane_bits");
        }
        // If nlanes == 1 return basic op
        if nlanes == 1 {
            match *op {
                Z3BinOps::BVAdd => lhs.bvadd(&rhs),
                Z3BinOps::BVSub => lhs.bvsub(&rhs),
                Z3BinOps::BVAnd => lhs.bvand(&rhs),
                Z3BinOps::BVOr => lhs.bvor(&rhs),
                Z3BinOps::BVXor => lhs.bvxor(&rhs),
                Z3BinOps::BVShl => lhs.bvshl(&rhs),
                Z3BinOps::BVLshr => lhs.bvlshr(&rhs),
                Z3BinOps::BVAshr => lhs.bvashr(&rhs),
            }
        } else {
        // Else apply op recursively to each lane, and concat results
            let mut lane_res : Vec<Ast<'ctx>> = vec!();
            let lane_sort : Sort<'ctx> = ctx.bitvector_sort(lane_bits);

            for i in 0..nlanes {
                let lhs1: Ast<'ctx> = lhs.extract((i+1)*8-1, i*8);
                let rhs1: Ast<'ctx> = rhs.extract((i+1)*8-1, i*8);
                lane_res.push(Z3State::z3_lanewise_binop(ctx,
                                                     lhs1,
                                                     rhs1,
                                                     &op,
                                                     &lane_sort,
                                                     1,
                                                     lane_bits));
            }

            lane_res.reverse();
            let mut res = lane_res[0].concat(&lane_res[1]);
            for i in 2..lane_res.len() {
                res = res.concat(&lane_res[i]);
            }
            res
        }
    }

    pub fn add_instr(&mut self, dfg: &DataFlowGraph, insn: Inst) -> () {
        match dfg[insn] {
            InstructionData::UnaryImm { opcode, imm } => {
                let r_value: Value = dfg.first_result(insn);
                let v_type: Type = dfg.value_type(r_value);

                let nbits = v_type.bits() as u32;
                let sort = Sort::bitvector(self.ctx, nbits as u32);

                match opcode {
                    /// `a = iconst N`. (UnaryImm)
                    Opcode::Iconst => {
                        let z3_val = Ast::from_bv(self.ctx, imm.into(), nbits);
                        self.define(r_value, z3_val, sort);
                    }
                    _ => {
                        panic!("Unknown instruction opcode {}", opcode);
                    }
                };
            }
            InstructionData::Binary { opcode, args } => {
                let r_value = dfg.first_result(insn);
                let v_type: Type = dfg.value_type(r_value);

                let z3_sort = to_z3_sort(self.ctx, &v_type);
                let lhs = self.lookup(args[0], &z3_sort);
                let rhs = self.lookup(args[1], &z3_sort);
                let z3_op = Z3State::bin_opcode_to_z3op(opcode)
                    .expect(format!("Unknown instruction opcode {}", opcode).as_str());

                let res = Z3State::z3_lanewise_binop(&self.ctx, lhs, rhs, &z3_op, &z3_sort,
                                v_type.lane_count() as u32,
                                v_type.lane_bits() as u32);
                self.define(r_value, res, z3_sort);
            }
            InstructionData::MultiAry { .. } => {
                // TODO
            }
            _ => {
                panic!("Unknown instruction format");
            }
        };
    }
}
